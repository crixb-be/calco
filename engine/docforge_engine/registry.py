from __future__ import annotations

import threading
from typing import Any

from .base import BaseProcessor, ProgressReporter
from .contract import ProcessorTask
from .errors import EngineError
from .processors.docling.docling_parser import DoclingParser
from .processors.ffmpeg_bridge.ffmpeg import FfmpegProcessor
from .processors.office_bridge.soffice import OfficeProcessor
from .processors.stirling_core.convert_pdf import PdfConvertProcessor
from .processors.stirling_core.compress_pdf import PdfCompressionProcessor
from .processors.stirling_core.edit import PdfEditProcessor
from .processors.stirling_core.organize import PdfOrganizeProcessor
from .processors.stirling_core.page_plan import PdfPagePlanProcessor
from .processors.stirling_core.page_organizer import PdfPageOrganizerProcessor
from .processors.stirling_core.security import PdfSecurityProcessor
from .processors.universal.image_converter import ImageConvertProcessor
from .processors.universal.pdf_to_images import PdfToImagesProcessor

_STIRLING_PROCESSORS = (
    PdfOrganizeProcessor,
    PdfSecurityProcessor,
    PdfEditProcessor,
    PdfConvertProcessor,
    PdfCompressionProcessor,
    PdfPagePlanProcessor,
    PdfPageOrganizerProcessor,
    ImageConvertProcessor,
    PdfToImagesProcessor,
)


class CompositePdfProcessor(BaseProcessor):
    engine_name = "stirling_core"

    def __init__(self):
        self._processors = [processor_type() for processor_type in _STIRLING_PROCESSORS]

    @classmethod
    def actions(cls):
        handlers = {}
        for processor_type in _STIRLING_PROCESSORS:
            handlers.update(processor_type.actions())
        return handlers

    def execute(self, action_name, task, reporter):
        for processor in self._processors:
            if action_name in processor.actions():
                return processor.execute(action_name, task, reporter)
        raise EngineError("UNKNOWN_ACTION", f"Unknown action 'stirling_core.{action_name}'")

    def health(self):
        return {"available": True, "version": "PyMuPDF/pikepdf"}


class EngineRegistry:
    def __init__(self):
        self.processors: dict[str, BaseProcessor] = {
            "stirling_core": CompositePdfProcessor(),
            "docling_core": DoclingParser(),
            "office_bridge": OfficeProcessor(),
            "ffmpeg_bridge": FfmpegProcessor(),
        }

    def execute(self, task: ProcessorTask, emit, cancel: threading.Event):
        processor = self.processors.get(task.engine)
        if processor is None:
            raise EngineError("INVALID_TASK", f"Unknown engine '{task.engine}'")
        return processor.execute(task.action, task, ProgressReporter(task.id, emit, cancel))

    def health(self) -> dict[str, Any]:
        return {name: processor.health() if hasattr(processor, "health") else {"available": True} for name, processor in self.processors.items()}
