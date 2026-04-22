"""阅读顺序重建：检测分栏，然后在每栏里按 y 排序。

学术论文双栏是最大痛点，这里用一个轻量的"竖向投影 + 间隙检测"方法：
1. 把所有文本块的 x 区间投影到一维数组；
2. 在中间区域 (40%~60%) 里找连续的 0 投影长度，作为列间空隙；
3. 找到则按 x 中心点把块二分到两栏，否则视为单栏。

对于绝大多数论文与电子书，这个启发式已经够用，复杂三栏/边注可在
roadmap 中扩展为递归 XY-Cut。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from ..types import TextBlock


def _projection(blocks: List[TextBlock], width: float, bins: int = 200) -> List[int]:
    proj = [0] * bins
    if width <= 0:
        return proj
    for b in blocks:
        x0, _, x1, _ = b.bbox
        i0 = max(0, int(x0 / width * bins))
        i1 = min(bins - 1, int(x1 / width * bins))
        for i in range(i0, i1 + 1):
            proj[i] += 1
    return proj


def detect_column_split(
    blocks: List[TextBlock], width: float, *, min_gap_ratio: float = 0.04
) -> Optional[float]:
    """返回分栏 x 坐标；若是单栏返回 None。"""

    if len(blocks) < 6 or width <= 0:
        return None

    bins = 200
    proj = _projection(blocks, width, bins=bins)

    lo = int(bins * 0.35)
    hi = int(bins * 0.65)
    # 在中间区域找最长的零投影段
    best_len = 0
    best_center = -1
    cur_start = None
    for i in range(lo, hi + 1):
        if proj[i] == 0:
            if cur_start is None:
                cur_start = i
        else:
            if cur_start is not None:
                length = i - cur_start
                if length > best_len:
                    best_len = length
                    best_center = (cur_start + i - 1) / 2
                cur_start = None
    if cur_start is not None:
        length = hi + 1 - cur_start
        if length > best_len:
            best_len = length
            best_center = (cur_start + hi) / 2

    if best_len / bins < min_gap_ratio:
        return None
    return best_center / bins * width


def assign_columns(blocks: List[TextBlock], split_x: Optional[float]) -> None:
    """就地给每个 TextBlock 写入 column 编号。"""

    if split_x is None:
        for b in blocks:
            b.column = 0
        return
    for b in blocks:
        cx = (b.bbox[0] + b.bbox[2]) / 2
        b.column = 0 if cx < split_x else 1


def reading_order(
    blocks: List[TextBlock], width: float
) -> Tuple[List[TextBlock], Optional[float]]:
    """按阅读顺序排序文本块；同时返回检测到的 split_x（用于 debug）。"""

    split_x = detect_column_split(blocks, width)
    assign_columns(blocks, split_x)
    # 同栏内按 y0 升序，再按 x0 升序
    blocks_sorted = sorted(blocks, key=lambda b: (b.column, round(b.bbox[1], 1), b.bbox[0]))
    return blocks_sorted, split_x
