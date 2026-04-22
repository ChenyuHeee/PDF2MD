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


def detect_vector_figure_bboxes(
    fpage: "fitz.Page",
    min_paths: int = 20,
    min_size: float = 55.0,
) -> List[BBox]:
    """通过 PyMuPDF 绘图路径聚类，检测页面上矢量图（图表、架构图等）的边界框。

    算法：
    1. 收集所有非全页的绘图路径 rect
    2. 用迭代合并将相邻/重叠的 rect 合并为区域（margin=8pt）
    3. 路径数 >= min_paths 且宽/高均 >= min_size 的区域视为矢量图

    min_paths=20 可避免把普通数据表格的边框线（通常 10~15 条路径）误判为图形；
    min_size=55 可过滤掉装饰性横线、分隔符等。

    返回：加了少量 padding 的图形边界框列表，供调用方过滤文字块/表格。
    """
    drawings = fpage.get_drawings()
    if not drawings:
        return []

    page_w = fpage.rect.width
    page_h = fpage.rect.height

    # 收集有意义的绘图 rect，跳过全页边框/极细微路径
    rects: List[List[float]] = []  # [x0, y0, x1, y1, count]
    for d in drawings:
        r = d.get("rect")
        if r is None or r.is_empty:
            continue
        x0, y0, x1, y1 = r.x0, r.y0, r.x1, r.y1
        w, h = x1 - x0, y1 - y0
        if w > page_w * 0.8 or h > page_h * 0.8:
            continue  # 跳过全页横/竖线/边框
        if w < 0.5 and h < 0.5:
            continue  # 跳过退化路径
        rects.append([x0, y0, x1, y1, 1])

    if len(rects) < min_paths:
        return []

    # 迭代合并：只要两个 rect 间距 <= margin，就合并
    margin = 8.0
    changed = True
    while changed:
        changed = False
        i = 0
        while i < len(rects):
            j = i + 1
            while j < len(rects):
                a, b = rects[i], rects[j]
                if (
                    a[0] - margin <= b[2]
                    and a[2] + margin >= b[0]
                    and a[1] - margin <= b[3]
                    and a[3] + margin >= b[1]
                ):
                    rects[i] = [
                        min(a[0], b[0]),
                        min(a[1], b[1]),
                        max(a[2], b[2]),
                        max(a[3], b[3]),
                        a[4] + b[4],
                    ]
                    rects.pop(j)
                    changed = True
                else:
                    j += 1
            i += 1

    # 筛选出足够大且有足够路径数的区域
    result: List[BBox] = []
    pad = 4.0
    for x0, y0, x1, y1, count in rects:
        if count >= min_paths and (x1 - x0) >= min_size and (y1 - y0) >= min_size:
            result.append((x0 - pad, y0 - pad, x1 + pad, y1 + pad))
    return result


def filter_vector_figure_fragments(
    blocks: List[TextBlock],
    figure_bboxes: List[BBox] | None = None,
) -> List[TextBlock]:
    """过滤矢量图内的孤立文本碎片（坐标轴标签、图例、架构图标注等）。

    优先策略（当 figure_bboxes 可用时）：
      若文本块中心落在已检测到的矢量图区域内，则过滤。
      这覆盖所有尺寸的图内文字，无论文字长短宽窄。

    回退策略（figure_bboxes 为空时）：
      对"小块"（高≤18pt、宽≤120pt、文字≤50字）做密度聚类：
      若周围 150pt 范围内有 ≥3 个其他小块，则视为图内碎片过滤。
      阈值比旧版更宽松，以覆盖更长的轴标签和图例文字。
    """
    if figure_bboxes:
        result = []
        for b in blocks:
            cx = (b.bbox[0] + b.bbox[2]) / 2
            cy = (b.bbox[1] + b.bbox[3]) / 2
            in_figure = any(
                fx0 <= cx <= fx1 and fy0 <= cy <= fy1
                for fx0, fy0, fx1, fy1 in figure_bboxes
            )
            if not in_figure:
                result.append(b)
        return result

    # ---- 回退：密度聚类（无 drawing 信息时使用）----
    def _is_small(b: TextBlock) -> bool:
        w = b.bbox[2] - b.bbox[0]
        h = b.bbox[3] - b.bbox[1]
        text = "".join(sp.text for ln in b.lines for sp in ln.spans).strip()
        return h <= 18 and w <= 120 and len(text) <= 50

    small_blocks = [b for b in blocks if _is_small(b)]
    if len(small_blocks) < 4:
        return blocks

    centers = [
        ((b.bbox[0] + b.bbox[2]) / 2, (b.bbox[1] + b.bbox[3]) / 2)
        for b in small_blocks
    ]
    to_remove: set = set()
    threshold = 150.0
    for i, (cx, cy) in enumerate(centers):
        neighbors = sum(
            1
            for j, (ox, oy) in enumerate(centers)
            if i != j and (cx - ox) ** 2 + (cy - oy) ** 2 <= threshold**2
        )
        if neighbors >= 3:
            to_remove.add(id(small_blocks[i]))

    return [b for b in blocks if id(b) not in to_remove]
