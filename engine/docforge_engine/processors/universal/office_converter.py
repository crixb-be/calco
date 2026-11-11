"""Universal Office-to-PDF conversion facade."""
from __future__ import annotations

from ...base import BaseProcessor, action
from ...util.binaries import locate_binary
from ...util.office_engines import SUPPORTED_OFFICE_EXTENSIONS, convert_office_to_pdf


def detect_libreoffice(options: dict | None = None) -> str | None:
    """Find soffice.exe in options, PATH, or standard Windows install locations."""
    return locate_binary("soffice", options or {})


class OfficeConverterProcessor(BaseProcessor):
    """Standalone universal action; the registry keeps the richer OfficeProcessor."""

    engine_name = "office_bridge"

    @action()
    def office_to_pdf(self, task, reporter):
        return convert_office_to_pdf(task, reporter)
