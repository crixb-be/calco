from __future__ import annotations

import re

from ..errors import EngineError


def page_ranges(value, total: int) -> list[int]:
    """Parse the public 1-based page syntax into unique 0-based indexes."""
    if total <= 0:
        return []
    if value is None or value == "":
        return list(range(total))
    if isinstance(value, int):
        value = [value]
    if isinstance(value, (list, tuple)):
        raw = []
        for item in value:
            if isinstance(item, int):
                raw.append(item)
            else:
                raw.extend(page_ranges(str(item), total))
        result = [x - 1 if x > 0 else x for x in raw]
        if all(0 <= x < total for x in result):
            return list(dict.fromkeys(result))
        raise EngineError("INVALID_TASK", "Page number is outside the document")
    result: list[int] = []
    for token in re.split(r"[,;]", str(value)):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            left, right = token.split("-", 1)
            left_text, right_text = left.strip().lower(), right.strip().lower()
            start = int(left_text) if left_text and left_text != "start" else 1
            end = total if not right_text or right_text == "end" else int(right_text)
            if start > end:
                start, end = end, start
            result.extend(range(start - 1, end))
        else:
            result.append(int(token) - 1)
    if not result or any(x < 0 or x >= total for x in result):
        raise EngineError("INVALID_TASK", "Page range is outside the document")
    return list(dict.fromkeys(result))
