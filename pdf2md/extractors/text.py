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


def filter_headers_footers(
    blocks: List[TextBlock], page_height: float, page_number: int
) -> List[TextBlock]:
    """去除页眉（y < 7% 页高）和页脚（y > 93% 页高）的文本块。

    页眉页脚判定条件（AND 关系，均满足才过滤）：
    - 位于页面顶部 7% 或底部 7% 区域内
    - 块内文字不超过 200 字符（避免误删第一页较长的合法内容）
    - 非第一页的顶部块（第一页标题不应被删除）

    适用于双栏论文的 "ASPLOS '25 …" / "Author et al." 类页眉，
    以及书籍的页码行。
    """
    top_threshold = page_height * 0.09   # ~71pt on Letter/A4 — covers 49~57pt headers
    bot_threshold = page_height * 0.93

    result = []
    for b in blocks:
        y0, y1 = b.bbox[1], b.bbox[3]
        text = "".join(sp.text for ln in b.lines for sp in ln.spans)

        # 用块的顶部坐标判定（y0），而非底部（y1），避免边界块漏判
        in_top = y0 < top_threshold
        in_bot = y1 > bot_threshold
        is_short = len(text.strip()) <= 200

        # 第1页顶部可能是正文标题，不过滤
        if in_top and is_short and page_number > 1:
            continue
        if in_bot and is_short:
            continue
        result.append(b)
    return result


# 仅含数字、标点、百分号等"坐标轴标签"字符
_AXIS_LABEL_RE = re.compile(r"^[\s\d\.\-\+\%\,×xk]+$", re.IGNORECASE)


def filter_figure_fragments(
    blocks: List[TextBlock], image_bboxes: List[BBox]
) -> List[TextBlock]:
    """过滤矢量图内嵌的坐标轴标签碎片。

    满足以下**全部**条件时过滤：
    1. 块的中心点在某张图片的 bounding box 内（宽松：上下各扩展 4pt）
    2. 块高度 ≤ 14pt（单行小字体标签）
    3. 块内文字 ≤ 12 字符且匹配纯数字/标点/单位模式

    调用方在有图片 bbox 信息时才传入，无图片时返回原列表。
    """
    if not image_bboxes:
        return blocks

    result = []
    for b in blocks:
        bx0, by0, bx1, by1 = b.bbox
        cx = (bx0 + bx1) / 2
        cy = (by0 + by1) / 2
        height = by1 - by0

        text = "".join(sp.text for ln in b.lines for sp in ln.spans).strip()

        # 条件 2 + 3：先快速判断
        if height > 14 or len(text) > 12 or not _AXIS_LABEL_RE.match(text):
            result.append(b)
            continue

        # 条件 1：块中心落在图片 bbox 内（容忍 4pt 误差）
        in_figure = any(
            ix0 - 4 <= cx <= ix1 + 4 and iy0 - 4 <= cy <= iy1 + 4
            for ix0, iy0, ix1, iy1 in image_bboxes
        )
        if not in_figure:
            result.append(b)

    return result
