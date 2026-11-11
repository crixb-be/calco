from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from .contract import parse_task
from .core.cleanup import shutdown_cleanup, startup_cleanup
from .errors import EngineError
from .registry import EngineRegistry
from .storage.history_manager import get_history_manager


MAX_FRAME_BYTES = 16 * 1024 * 1024
MAX_PENDING_RPCS = 64


class Sidecar:
    def __init__(self):
        startup_cleanup()
        self.registry = EngineRegistry()
        self.history = get_history_manager()
        # Private handle for the NDJSON channel; serve() points sys.stdout at stderr so stray
        # print() calls from third-party libraries cannot corrupt protocol lines.
        self._out = sys.stdout
        self.write_lock = threading.Lock()
        self.cancel_events: dict[str, threading.Event] = {}
        self.cancel_lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="docforge")
        self.docling_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="docforge-docling")
        self.docling_lock = threading.Lock()
        self.docling_active = 0
        # RPC queries (thumbnails, file reads) never wait behind long-running tasks.
        self.rpc_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="docforge-rpc")
        self.rpc_lock = threading.Lock()
        self.pending_rpcs: dict[str, Future | None] = {}
        self.running_rpcs: set[str] = set()
        self.cancelled_rpcs: set[str] = set()
        threading.Thread(target=self._cleanup_thumbnail_cache, daemon=True).start()

    @staticmethod
    def _cleanup_thumbnail_cache():
        try:
            from .util.thumbnail_generator import get_service

            removed = get_service().cleanup()
            if removed:
                print(f"[engine] caché de miniaturas: {removed} carpetas antiguas eliminadas", file=sys.stderr, flush=True)
        except Exception as exc:  # best effort
            print(f"[engine] limpieza de caché falló: {exc}", file=sys.stderr, flush=True)

    def _rpc_result(self, rpc_id: str, event: dict):
        with self.rpc_lock:
            if rpc_id in self.cancelled_rpcs:
                return
        self.emit(event)

    def _rpc(self, rpc_id: str, method: str, params):
        from . import rpc

        with self.rpc_lock:
            self.running_rpcs.add(rpc_id)
        try:
            result = rpc.dispatch(method, params)
            self._rpc_result(rpc_id, {"type": "rpc_result", "rpcId": rpc_id, "ok": True, "result": result})
        except EngineError as exc:
            self._rpc_result(rpc_id, {"type": "rpc_result", "rpcId": rpc_id, "ok": False,
                                      "error": {"code": exc.code, "message": exc.message, "details": exc.details}})
        except Exception as exc:  # never let one query kill the sidecar
            self._rpc_result(rpc_id, {"type": "rpc_result", "rpcId": rpc_id, "ok": False,
                                      "error": {"code": "INTERNAL", "message": str(exc), "details": type(exc).__name__}})

    def _rpc_finished(self, rpc_id: str, future: Future) -> None:
        del future
        with self.rpc_lock:
            self.pending_rpcs.pop(rpc_id, None)
            self.running_rpcs.discard(rpc_id)
            self.cancelled_rpcs.discard(rpc_id)

    def submit_rpc(self, rpc_id: str, method: str, params) -> None:
        with self.rpc_lock:
            if len(self.pending_rpcs) >= MAX_PENDING_RPCS or rpc_id in self.pending_rpcs:
                busy = True
            else:
                busy = False
                # Reserve the slot before submitting so a concurrent cancel cannot miss it.
                self.pending_rpcs[rpc_id] = None
        if busy:
            self.emit({"type": "rpc_result", "rpcId": rpc_id, "ok": False,
                       "error": {"code": "BUSY", "message": "Too many pending RPCs"}})
            return
        future = self.rpc_pool.submit(self._rpc, rpc_id, method, params)
        with self.rpc_lock:
            missing = rpc_id not in self.pending_rpcs
            if not missing:
                self.pending_rpcs[rpc_id] = future
        if missing:
            future.cancel()
            future.add_done_callback(lambda completed, id_=rpc_id: self._rpc_finished(id_, completed))
            return
        future.add_done_callback(lambda completed, id_=rpc_id: self._rpc_finished(id_, completed))

    def cancel_rpc(self, rpc_id: str) -> None:
        with self.rpc_lock:
            future = self.pending_rpcs.get(rpc_id)
            if future is None:
                if rpc_id not in self.pending_rpcs:
                    return
                if rpc_id in self.running_rpcs:
                    self.cancelled_rpcs.add(rpc_id)
                    queued = False
                else:
                    self.pending_rpcs.pop(rpc_id, None)
                    self.cancelled_rpcs.add(rpc_id)
                    queued = True
            else:
                queued = False

        # Future.cancel() may invoke its done callback synchronously. Never call it while
        # holding rpc_lock, or the callback would wait forever for the same lock.
        if future is not None and future.cancel():
            with self.rpc_lock:
                self.pending_rpcs.pop(rpc_id, None)
            queued = True
        elif future is not None:
            # A running RPC cannot be interrupted safely; suppress its eventual result.
            with self.rpc_lock:
                if rpc_id in self.pending_rpcs:
                    self.cancelled_rpcs.add(rpc_id)
            queued = False
        if queued:
            self.emit({"type": "rpc_result", "rpcId": rpc_id, "ok": False,
                       "error": {"code": "CANCELLED", "message": "RPC cancelled"}})

    def emit(self, event: dict):
        # ensure_ascii=True: the NDJSON channel is pure ASCII (non-ASCII -> \uXXXX), so paths like
        # "MAESTRÍA GESTIÓN" survive any pipe encoding and Rust never drops a line as invalid UTF-8.
        with self.write_lock:
            self._out.write(json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n")
            self._out.flush()

    def submit(self, task):
        cancel = threading.Event()
        with self.cancel_lock:
            self.cancel_events[task.id] = cancel
        if task.engine == "docling_core":
            # Docling runs one job at a time (models are heavy): tell the UI it is waiting
            # instead of leaving it at 0 % with no feedback.
            with self.docling_lock:
                waiting = self.docling_active
                self.docling_active += 1
            if waiting:
                self.emit({"type": "progress", "id": task.id, "percent": 0,
                           "message": f"En espera: {waiting} tarea(s) de Docling por delante..."})
            self.docling_pool.submit(self._run_docling, task, cancel)
        else:
            self.pool.submit(self._run, task, cancel)

    def _run_docling(self, task, cancel):
        try:
            self._run(task, cancel)
        finally:
            with self.docling_lock:
                self.docling_active -= 1

    def _run(self, task, cancel):
        started = time.perf_counter()
        status = "success"
        output_files: list[str] = []
        try:
            if cancel.is_set():
                raise EngineError("CANCELLED", "Task cancelled")
            outputs, meta = self.registry.execute(task, self.emit, cancel)
            output_files = outputs
            self.emit({"type": "result", "id": task.id, "status": "success", "outputFiles": outputs, "meta": meta or None})
        except EngineError as exc:
            status = "cancelled" if exc.code == "CANCELLED" else "error"
            self.emit({"type": "error", "id": task.id, "code": exc.code, "message": exc.message, "details": exc.details})
        except Exception as exc:  # the sidecar must never die because of one task
            status = "error"
            trace = traceback.format_exc()
            print(f"[{task.id}] ERROR {trace}", file=sys.stderr, flush=True)
            self.emit({"type": "error", "id": task.id, "code": "INTERNAL",
                       "message": f"{type(exc).__name__}: {exc}", "details": trace})
        finally:
            try:
                self.history.record(
                    task_id=task.id,
                    task_type=task.action,
                    source_name=Path(task.inputFiles[0]).name if task.inputFiles else "",
                    target_path=output_files[0] if output_files else "",
                    status=status,
                    duration_ms=round((time.perf_counter() - started) * 1000),
                )
            except Exception as history_error:
                print(f"[{task.id}] history write failed: {history_error}", file=sys.stderr, flush=True)
            with self.cancel_lock:
                self.cancel_events.pop(task.id, None)

    def cancel(self, task_id: str):
        with self.cancel_lock:
            event = self.cancel_events.get(task_id)
        if event:
            event.set()

    def serve(self):
        print(f"[engine] serve listo pid={__import__('os').getpid()} stdin={sys.stdin.encoding} stdout={sys.stdout.encoding}",
              file=sys.stderr, flush=True)
        sys.stdout = sys.stderr
        for line in _detach_stdin():
            if len(line) > MAX_FRAME_BYTES:
                self.emit({"type": "error", "id": "", "code": "INVALID_TASK", "message": "Frame too large"})
                continue
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                self.emit({"type": "error", "id": "", "code": "INVALID_TASK", "message": "Invalid JSON", "details": str(exc)})
                continue
            if isinstance(raw, dict) and raw.get("type") == "health":
                self.emit({"type": "health", "engines": self.registry.health()})
                continue
            if isinstance(raw, dict) and raw.get("type") == "cancel":
                self.cancel(str(raw.get("id", "")))
                continue
            if isinstance(raw, dict) and raw.get("type") == "rpc":
                self.submit_rpc(str(raw.get("rpcId", "")), str(raw.get("method", "")), raw.get("params"))
                continue
            if isinstance(raw, dict) and raw.get("type") == "rpc_cancel":
                self.cancel_rpc(str(raw.get("rpcId", "")))
                continue
            task_id = str(raw.get("id", "")) if isinstance(raw, dict) else ""
            try:
                task = parse_task(raw)
                self.submit(task)
            except ValueError as exc:
                self.emit({"type": "error", "id": task_id, "code": "INVALID_TASK", "message": "Invalid task", "details": str(exc)})
        self.pool.shutdown(wait=True)
        self.docling_pool.shutdown(wait=True)
        self.rpc_pool.shutdown(wait=True)
        shutdown_cleanup()


def _detach_stdin():
    """Return a private reader for the stdin pipe and point fd 0 / STD_INPUT_HANDLE at NUL.

    Windows serializes synchronous I/O per file object: while the main thread is blocked
    reading the pipe, any other thread that queries the standard input handle (native DLL
    initialization does, e.g. numpy's ``_multiarray_umath`` imported by Docling) blocks until
    the next line arrives. That froze ``docling_parse`` at 5 % forever. Reading from a private
    duplicate and leaving NUL as the process' standard input removes the contention."""
    if os.name != "nt":
        return sys.stdin
    try:
        private_fd = os.dup(sys.stdin.fileno())
        null_fd = os.open(os.devnull, os.O_RDONLY)
        os.dup2(null_fd, 0)  # the UCRT also updates STD_INPUT_HANDLE for fds 0-2
        os.close(null_fd)
    except OSError as exc:
        print(f"[engine] no se pudo aislar stdin ({exc}); se usa el original", file=sys.stderr, flush=True)
        return sys.stdin
    reader = open(private_fd, "r", encoding="utf-8", errors="strict", closefd=True)
    sys.stdin = open(os.devnull, "r", encoding="utf-8")
    return reader


def run_one(task_path: str) -> int:
    sidecar = Sidecar()
    try:
        raw = json.loads(Path(task_path).read_text(encoding="utf-8"))
        task = parse_task(raw)
        cancel = threading.Event()
        sidecar._run(task, cancel)
        return 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        sidecar.emit({"type": "error", "id": "", "code": "INVALID_TASK", "message": "Invalid task file", "details": str(exc)})
        return 2


def _force_utf8_stdio() -> None:
    """On Windows, piped stdio defaults to the ANSI code page (cp1252), which corrupts or rejects
    UTF-8 paths sent by Tauri (e.g. 'MAESTRÍA'). Force UTF-8 on every stream."""
    for name, errors in (("stdin", "strict"), ("stdout", "strict"), ("stderr", "backslashreplace")):
        stream = getattr(sys, name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors=errors, newline="\n" if name != "stdin" else None)
            except (ValueError, OSError):
                pass


def main(argv=None) -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(prog="docforge-engine")
    subparsers = parser.add_subparsers(dest="mode", required=True)
    subparsers.add_parser("serve", help="run the persistent NDJSON sidecar")
    run_parser = subparsers.add_parser("run", help="run one task JSON file")
    run_parser.add_argument("task_json")
    args = parser.parse_args(argv)
    if args.mode == "serve":
        Sidecar().serve()
        return 0
    return run_one(args.task_json)


if __name__ == "__main__":
    raise SystemExit(main())
