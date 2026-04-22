"""通过 PyMuPDF 抽取页面里的所有 span/line/block。"""

from __future__ import annotations

import re
from typing import List

import fitz  # PyMuPDF

from ..types import BBox, Line, Span, TextBlock

# 过滤 CID 无法解码的控制字符（来自未嵌入 ToUnicode 的数学字体）
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def extract_blocks(page: "fitz.Page") -> List[TextBlock]:
    """提取一页中的文本块（仅文本，图片块忽略）。"""

    raw = page.get_text("dict")
    blocks: List[TextBlock] = []

    for b in raw.get("blocks", []):
        if b.get("type", 0) != 0:  # 0=text, 1=image
            continue

        lines: List[Line] = []
        for ln in b.get("lines", []):
            spans: List[Span] = []
            for sp in ln.get("spans", []):
                text = _CTRL_RE.sub("", sp.get("text", ""))
                if not text:
                    continue
                spans.append(
                    Span(
                        text=text,
                        bbox=tuple(sp["bbox"]),
                        size=float(sp.get("size", 0.0)),
                        font=sp.get("font", ""),
                        flags=int(sp.get("flags", 0)),
                    )
                )
            if not spans:
                continue
            lines.append(Line(spans=spans, bbox=tuple(ln["bbox"])))

        if not lines:
            continue
        blocks.append(TextBlock(lines=lines, bbox=tuple(b["bbox"])))

    return blocks


def filter_outside(blocks: List[TextBlock], excluded: List[BBox]) -> List[TextBlock]:
    """过滤掉中心点落在 excluded 区域（如表格、图片）内的文本块。"""

    if not excluded:
        return blocks

    def inside(bbox: BBox) -> bool:
        cx = (bbox[0] + bbox[2]) / 2
        cy = (bbox[1] + bbox[3]) / 2
        for x0, y0, x1, y1 in excluded:
            if x0 <= cx <= x1 and y0 <= cy <= y1:
                return True
        return False

    return [b for b in blocks if not inside(b.bbox)]
