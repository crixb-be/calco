from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from ...base import BaseProcessor, action
from ...errors import EngineError
from ...util.binaries import locate_binary
from ...util.paths import atomic_write_bytes, output_path, require_inputs, safe_stem


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
        with tempfile.TemporaryDirectory(dir=task.outputDir) as temp_dir:
            temp_out = Path(temp_dir) / f"output.{extension}"
            command = [binary, "-y", "-i", str(source), *args, str(temp_out)]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=600)
            if completed.returncode != 0 or not temp_out.exists():
                raise EngineError("INTERNAL", f"ffmpeg failed for {source.name}", completed.stderr[-4000:])
            atomic_write_bytes(out, temp_out.read_bytes())
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
