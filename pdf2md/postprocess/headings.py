"""标题识别：基于"全局正文字号 vs. 块平均字号"的差异分级。"""

from __future__ import annotations

from collections import Counter
from typing import Dict, List

from ..types import TextBlock


def estimate_body_size(blocks_per_page: List[List[TextBlock]]) -> float:
    """全局正文字号 = 所有 span 字号的众数（按字符数加权）。"""

    counter: Counter = Counter()
    for blocks in blocks_per_page:
        for b in blocks:
            for ln in b.lines:
                for s in ln.spans:
                    if s.size > 0 and s.text.strip():
                        counter[round(s.size, 1)] += len(s.text)
    if not counter:
        return 10.0
    return counter.most_common(1)[0][0]


def block_avg_size(block: TextBlock) -> float:
    total = 0.0
    n = 0
    for ln in block.lines:
        for s in ln.spans:
            if s.text.strip():
                total += s.size * len(s.text)
                n += len(s.text)
    return total / n if n else 0.0


def heading_level(block: TextBlock, body_size: float) -> int:
    """0 表示不是标题；1~6 是 Markdown 标题级别。

    判定规则（保守）：
    - 块只有 1~3 行；
    - 平均字号 > body_size * 1.15 或者整块加粗；
    - 字号越大级别越小（# 一号最大）。
    """

    if not block.lines or len(block.lines) > 3:
        return 0

    avg = block_avg_size(block)
    is_bold = all(s.is_bold for ln in block.lines for s in ln.spans if s.text.strip())

    ratio = avg / body_size if body_size else 1.0
    if ratio >= 1.6:
        return 1
    if ratio >= 1.35:
        return 2
    if ratio >= 1.2:
        return 3
    if ratio >= 1.1 and is_bold:
        return 4
    if is_bold and len(block.lines) == 1 and len(block.lines[0].text.strip()) < 80:
        # 加粗短行：很可能是小节标题
        return 5
    return 0
