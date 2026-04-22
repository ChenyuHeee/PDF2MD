"""段落整理：
1. merge_paragraph_blocks — 把跨 block 的续行合并为一个段落 TextBlock。
2. merge_lines            — 把 TextBlock 内部的多行拼接成一段文本。
"""

from __future__ import annotations

import re
from collections import Counter
from typing import List

from ..extractors.formulas import wrap_math_in_text
from ..types import Line, TextBlock


_HYPHEN_END = re.compile(r"([A-Za-z])-$")
# 西文（英文等）单词字符
_LATIN_WORD = re.compile(r"[A-Za-z]")
# 形如 "1 " / "1. " / "(a) " 这类独立编号行（极短且以数字/字母编号开头）
_ENUM_START = re.compile(r"^\s*(\d{1,3}|[a-zA-Z])\s*[\.\)]\s+|^\s*\(([a-zA-Z]|\d{1,3})\)\s+")


# ---------------------------------------------------------------------------
# 阶段一：跨 block 段落合并
# ---------------------------------------------------------------------------

def _merge_two_blocks(a: TextBlock, b: TextBlock) -> TextBlock:
    new_bbox = (
        min(a.bbox[0], b.bbox[0]),
        a.bbox[1],
        max(a.bbox[2], b.bbox[2]),
        b.bbox[3],
    )
    return TextBlock(lines=a.lines + b.lines, bbox=new_bbox, column=a.column)


def _estimate_body_x0(blocks: List[TextBlock]) -> float:
    """最小的高频 x0 = 该页正文左边距（非缩进的续行）。

    注意：用"最小"而非"众数"，因为首行缩进和续行出现次数可能相同。
    """
    counter: Counter = Counter()
    for b in blocks:
        counter[round(b.bbox[0], 0)] += 1
    # 只考虑出现 ≥2 次的 x0
    frequent = [x for x, c in counter.items() if c >= 2]
    if not frequent:
        return float(min(counter.keys())) if counter else 0.0
    return float(min(frequent))


def _estimate_col_width(blocks: List[TextBlock], body_x0: float) -> float:
    """估算文本栏宽（用于计算行填充率）。

    取所有 block 中最后一行的 x1 的 90 百分位值，减去 body_x0。
    90 百分位可以避免居中标题、短公式等异常值的干扰。
    """
    x1_vals: List[float] = []
    for b in blocks:
        if not b.lines:
            continue
        last_ln = b.lines[-1]
        if not last_ln.spans:
            continue
        x1 = max(s.bbox[2] for s in last_ln.spans)
        x1_vals.append(x1)
    if not x1_vals:
        return 400.0
    x1_vals.sort()
    p90 = x1_vals[int(len(x1_vals) * 0.90)]
    width = p90 - body_x0
    return max(width, 50.0)


def _last_line_fill(block: TextBlock, body_x0: float, col_width: float) -> float:
    """上一个 block 最后一行占栏宽的比例。接近 1.0 = 满行 = 段落未结束。"""
    if not block.lines or not block.lines[-1].spans:
        return 0.0
    last_ln = block.lines[-1]
    x1 = max(s.bbox[2] for s in last_ln.spans)
    return (x1 - body_x0) / col_width


def merge_paragraph_blocks(blocks: List[TextBlock]) -> List[TextBlock]:
    """把因 PDF 排版产生的"同一段落多个 block"合并。

    核心判断：前一个 block 的最后一行是否是"满行"。
    ─────────────────────────────────────────────────
    • fill ≥ 0.85（满行）→ 段落还没结束 → 合并后续 block
    • fill < 0.85（短行）→ 段落自然结束 → 下一 block 独立成段

    关键：栏宽 **按列分别估算**。
    双栏论文每栏约 240pt，若用全页所有块的 x1 估算会得到 ~560pt，
    导致左栏每行 fill ≈ 0.44，全部误判为"短行/新段落"。

    补充硬规则：
    • 相邻 block 跨列          → 强制新段落
    • y 间距 > 2.5×行高       → 强制新段落（图表、节标题之后）
    • y 坐标倒退（乱序）       → 强制新段落
    """
    if len(blocks) <= 1:
        return blocks

    # ── 按列分组，各自估算 body_x0 和 col_width ──────────────────────────
    from collections import defaultdict as _dd
    col_groups: dict = _dd(list)
    for b in blocks:
        col_groups[b.column].append(b)

    col_body_x0: dict = {}
    col_widths: dict = {}
    for col, col_b in col_groups.items():
        bx0 = _estimate_body_x0(col_b)
        col_body_x0[col] = bx0
        col_widths[col] = _estimate_col_width(col_b, bx0)

    heights = [b.bbox[3] - b.bbox[1] for b in blocks if b.bbox[3] - b.bbox[1] > 1]
    avg_h = sum(heights) / len(heights) if heights else 14.0
    max_gap = max(2.5 * avg_h, avg_h + 8.0)

    merged: List[TextBlock] = []
    for block in blocks:
        if not merged:
            merged.append(block)
            continue

        prev = merged[-1]
        y_gap = block.bbox[1] - prev.bbox[3]
        same_col = prev.column == block.column

        # 硬分割规则
        if not same_col or y_gap < -2 or y_gap > max_gap:
            merged.append(block)
            continue

        # 使用前块所在列的栏宽
        bx0 = col_body_x0.get(prev.column, col_body_x0.get(0, 36.0))
        cw = col_widths.get(prev.column, col_widths.get(0, 400.0))
        fill = _last_line_fill(prev, bx0, cw)

        if fill >= 0.85:
            merged[-1] = _merge_two_blocks(prev, block)
        else:
            merged.append(block)

    return merged


# ---------------------------------------------------------------------------
# 阶段二：block 内行合并
# ---------------------------------------------------------------------------


def _line_to_text(line: Line) -> str:
    return wrap_math_in_text(line.text, line.spans)


def _is_enum_start(text: str) -> bool:
    """判断一行是否像题目/子项的编号起始（不应拼接到上一行）。"""
    return bool(_ENUM_START.match(text))


def merge_lines(lines: List[Line]) -> str:
    """把同一块里的若干行合并成一段。"""

    if not lines:
        return ""
    out = _line_to_text(lines[0]).rstrip()
    for ln in lines[1:]:
        cur = _line_to_text(ln).strip()
        if not cur:
            continue

        # 如果当前行像独立的编号项（1. / (a) 等），换行而非追加
        if _is_enum_start(cur) and not _is_enum_start(out):
            out += "\n" + cur
            continue

        m = _HYPHEN_END.search(out)
        if m:
            # 行尾连字符 + 下一行小写字母 → 拼接去掉连字符
            if cur and cur[0].islower():
                out = out[:-1] + cur
                continue

        # 决定衔接符：CJK 之间不加空格，否则加空格
        last_char = out[-1] if out else ""
        first_char = cur[0]
        if _is_cjk(last_char) and _is_cjk(first_char):
            out += cur
        elif _is_cjk(last_char) or _is_cjk(first_char):
            # 中英文混排：也不加空格（CJK 与拉丁之间通常排版已处理）
            out += cur
        elif _LATIN_WORD.match(last_char) and _LATIN_WORD.match(first_char):
            out += " " + cur
        else:
            out += cur if last_char in "([" or first_char in ".,;:?!)]" else " " + cur
    return out.strip()


def _is_cjk(ch: str) -> bool:
    if not ch:
        return False
    o = ord(ch)
    return (
        0x4E00 <= o <= 0x9FFF
        or 0x3400 <= o <= 0x4DBF
        or 0x3000 <= o <= 0x303F
        or 0xFF00 <= o <= 0xFFEF
    )
