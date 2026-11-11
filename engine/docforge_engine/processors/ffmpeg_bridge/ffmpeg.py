from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ...base import BaseProcessor, action
from ...errors import EngineError
from ...util.binaries import locate_binary
from ...util.paths import output_path, release_output_path, require_inputs, safe_stem
from ...util.proc import no_window_kwargs


def _kill_process_tree(process: subprocess.Popen) -> None:
    """Stop ffmpeg and any children without leaving inherited handles behind."""
    if sys.platform == "win32":
        try:
            process.terminate()
            process.wait(timeout=1)
        except Exception:
            pass
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
                **no_window_kwargs(),
            )
        except Exception:
            pass
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except Exception:
            try:
                process.terminate()
            except Exception:
                pass
        try:
            process.wait(timeout=1)
        except Exception:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except Exception:
                pass
    try:
        process.kill()
    except Exception:
        pass
    try:
        process.wait(timeout=5)
    except Exception:
        pass


def _stderr_tail(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-4000:].strip()
    except OSError:
        return ""


class FfmpegProcessor(BaseProcessor):
    engine_name = "ffmpeg_bridge"

    def health(self):
        binary = locate_binary("ffmpeg", {})
        return {"available": binary is not None, "binary": binary, "reason": None if binary else "ffmpeg not found"}

    def _run(self, task, source: Path, extension: str, args: list[str], reporter):
        binary = locate_binary("ffmpeg", task.options)
        if not binary:
            raise EngineError("BINARY_NOT_FOUND", "ffmpeg was not found")
        out = output_path(task, safe_stem(source), task.action, f".{extension}")
        try:
            with tempfile.TemporaryDirectory(dir=task.outputDir) as temp_dir:
                temp_out = Path(temp_dir) / f"output.{extension}"
                stderr_path = Path(temp_dir) / "stderr.log"
                command = [binary, "-y", "-i", str(source), *args, str(temp_out)]
                popen_kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL}
                if sys.platform == "win32":
                    popen_kwargs.update(no_window_kwargs(extra_creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)))
                else:
                    popen_kwargs["start_new_session"] = True
                with stderr_path.open("w", encoding="utf-8", errors="replace") as stderr:
                    process = subprocess.Popen(command, stderr=stderr, **popen_kwargs)
                    started = time.monotonic()
                    while process.poll() is None:
                        try:
                            reporter.check_cancelled()
                        except EngineError as exc:
                            _kill_process_tree(process)
                            raise EngineError("CANCELLED", exc.message, _stderr_tail(stderr_path)) from exc
                        elapsed = time.monotonic() - started
                        if elapsed >= 600:
                            _kill_process_tree(process)
                            raise EngineError(
                                "TIMEOUT",
                                f"ffmpeg super\u00f3 el tiempo l\u00edmite de 600s convirtiendo {source.name}",
                                _stderr_tail(stderr_path),
                            )
                        time.sleep(0.1)
                    returncode = process.returncode
                try:
                    reporter.check_cancelled()
                except EngineError as exc:
                    raise EngineError(exc.code, exc.message, _stderr_tail(stderr_path)) from exc
                stderr_tail = _stderr_tail(stderr_path)
                if returncode != 0 or not temp_out.exists():
                    raise EngineError("INTERNAL", f"ffmpeg failed for {source.name}", stderr_tail)
                # The temporary directory is under outputDir, so this is an atomic
                # same-volume move and avoids loading the whole video into Python RAM.
                os.replace(temp_out, out)
                release_output_path(out, remove_placeholder=False)
        except Exception:
            release_output_path(out)
            raise
        reporter.report(100, f"Converted {source.name}")
        return [str(out)], {}

    @action()
    def to_audio(self, task, reporter):
        inputs = require_inputs(task)
        extension = str(task.options.get("format", "mp3")).lower()
        if extension not in ("mp3", "wav", "aac"):
            raise EngineError("INVALID_TASK", "to_audio.format must be mp3, wav, or aac")
        args = []
        if task.options.get("bitrate"):
            args += ["-b:a", str(task.options["bitrate"])]
        outputs = []
        for source in inputs:
            outputs += self._run(task, source, extension, args, reporter)[0]
        return outputs, {}

    @action()
    def compress_video(self, task, reporter):
        inputs = require_inputs(task)
        args = ["-c:v", "libx264", "-crf", str(task.options.get("crf", 28)), "-preset", str(task.options.get("preset", "medium"))]
        if task.options.get("maxHeight"):
            args += ["-vf", f"scale=-2:min(ih,{int(task.options['maxHeight'])})"]
        outputs = []
        for source in inputs:
            outputs += self._run(task, source, str(task.options.get("container", source.suffix.lstrip(".") or "mp4")), args, reporter)[0]
        return outputs, {}

    @action()
    def convert(self, task, reporter):
        inputs = require_inputs(task)
        extension = str(task.options.get("container", task.options.get("format", "mp4"))).lower()
        if extension not in ("mp4", "mkv", "webm"):
            raise EngineError("INVALID_TASK", "convert.container must be mp4, mkv, or webm")
        outputs = []
        for source in inputs:
            outputs += self._run(task, source, extension, [], reporter)[0]
        return outputs, {}
