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
    blocks: List[TextBlock], width: float, *, min_gap_ratio: float = 0.025
) -> Optional[float]:
    """返回分栏 x 坐标；若是单栏返回 None。

    只用"中等宽度"文本块做投影（排除全幅标题和窄作者名/图注碎片），
    避免它们把列间空隙遮蔽，并降低最小空隙比例阈值。
    """

    if len(blocks) < 4 or width <= 0:
        return None

    # 只保留宽度在 [20%, 80%] 页宽区间的块，以排除：
    #   < 20%: 作者短名、坐标轴标签等窄块
    #   > 80%: 全幅标题、大型表格、图片注释等满栏块
    body_width_min = width * 0.20
    body_width_max = width * 0.80
    proj_blocks = [
        b for b in blocks
        if body_width_min < (b.bbox[2] - b.bbox[0]) < body_width_max
    ]
    if len(proj_blocks) < 4:
        # 候选块太少，回退到全部块
        proj_blocks = blocks

    bins = 200
    proj = _projection(proj_blocks, width, bins=bins)

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


def assign_columns(blocks: List[TextBlock], split_x: Optional[float], width: float = 0.0) -> None:
    """就地给每个 TextBlock 写入 column 编号。

    column = -1：全幅块（如论文标题），排序时放在所有分栏块之前。
    column =  0：左栏（或单栏模式下所有块）。
    column =  1：右栏。
    """

    if split_x is None:
        for b in blocks:
            b.column = 0
        return
    for b in blocks:
        w = b.bbox[2] - b.bbox[0]
        if width > 0 and w > width * 0.70:
            # 全幅块（标题、分隔线等）：column=-1，排序时总在最前
            b.column = -1
        else:
            cx = (b.bbox[0] + b.bbox[2]) / 2
            b.column = 0 if cx < split_x else 1


def reading_order(
    blocks: List[TextBlock], width: float
) -> Tuple[List[TextBlock], Optional[float]]:
    """按阅读顺序排序文本块；同时返回检测到的 split_x（用于 debug）。

    column=-1（全幅块如标题）总排在最前；同栏内按 y0 升序排列。
    """

    split_x = detect_column_split(blocks, width)
    assign_columns(blocks, split_x, width)
    # column=-1 最前，同栏按 y 升序，再按 x 升序
    blocks_sorted = sorted(blocks, key=lambda b: (b.column, round(b.bbox[1], 1), b.bbox[0]))
    return blocks_sorted, split_x
