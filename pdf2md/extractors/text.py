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


def filter_margin_blocks(blocks: List[TextBlock], page_width: float) -> List[TextBlock]:
    """过滤左/右边距外的文本块（如 arXiv 旋转水印印章）。

    arXiv 给论文添加的旋转水印 bbox 通常是 x0≈5~15, x1≈40（非常窄，在边距内）。
    判定条件：块整体在左边距（x1 < 45）或右边距（x0 > page_width - 20）内，
    或者块的宽 / 高 < 0.05（极细竖向旋转文字）。
    """
    result = []
    for b in blocks:
        x0, y0, x1, y1 = b.bbox
        w, h = x1 - x0, y1 - y0
        # 在页面左/右边距外
        if x1 < 45 or x0 > page_width - 20:
            continue
        # 极度窄高比（旋转文字侧印）：宽/高 < 0.12 且宽 < 30pt
        if h > 0 and w / h < 0.12 and w < 30:
            continue
        result.append(b)
    return result


def filter_vector_figure_fragments(blocks: List[TextBlock]) -> List[TextBlock]:
    """聚类检测并过滤向量图内的孤立文本碎片（坐标轴标签、架构图标注等）。

    向量图内的文字标注特征：
    - 块高度 ≤ 18pt（单行小字体）且宽度 ≤ 80pt
    - 文本长度 ≤ 25 字符

    核心思路：这些块呈"簇状"聚集——若某块与 ≥ 3 个其他小块的 2D 距离 ≤ 100pt，
    则判定为图内孤立碎片，过滤掉。
    正文段落标题（如"2 Motivation"）是孤立的大块，不会被误过滤。
    """
    # 找出所有"候选小块"
    def _is_small(b: TextBlock) -> bool:
        w = b.bbox[2] - b.bbox[0]
        h = b.bbox[3] - b.bbox[1]
        text = "".join(sp.text for ln in b.lines for sp in ln.spans).strip()
        return h <= 18 and w <= 80 and len(text) <= 25

    small_blocks = [b for b in blocks if _is_small(b)]
    if len(small_blocks) < 4:
        # 页面上几乎没有小块，不做过滤
        return blocks

    # 预计算中心点
    centers = [((b.bbox[0] + b.bbox[2]) / 2, (b.bbox[1] + b.bbox[3]) / 2) for b in small_blocks]

    # 对每个小块，统计在 100pt 2D 距离内的其他小块数量
    to_remove: set = set()
    threshold = 100.0
    for i, (cx, cy) in enumerate(centers):
        neighbor_count = 0
        for j, (ox, oy) in enumerate(centers):
            if i != j and (cx - ox) ** 2 + (cy - oy) ** 2 <= threshold ** 2:
                neighbor_count += 1
        if neighbor_count >= 3:
            to_remove.add(id(small_blocks[i]))

    return [b for b in blocks if id(b) not in to_remove]
