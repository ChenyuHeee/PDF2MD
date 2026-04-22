"""列表识别。"""

from __future__ import annotations

import re

_BULLET_RE = re.compile(r"^\s*[\u2022\u25CF\u25E6•·\-\*]\s+(.*)$")
_NUMBER_RE = re.compile(r"^\s*(\d{1,3}|[a-zA-Z])[\.\)]\s+(.*)$")


def to_list_item(text: str):
    """若是列表项返回 ('-', body)/('1.', body)，否则返回 (None, text)。"""

    m = _BULLET_RE.match(text)
    if m:
        return "-", m.group(1).strip()
    m = _NUMBER_RE.match(text)
    if m:
        return f"{m.group(1)}.", m.group(2).strip()
    return None, text
