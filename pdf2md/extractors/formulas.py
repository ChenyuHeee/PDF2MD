"""公式探测（启发式）。

目标：把数学型 span 包成 `$...$`（行内）或 `$$...$$`（独立行）。
我们不做真正的 OCR/LaTeX 还原（那是 nougat/marker 的活儿），
只确保不把数学符号当成乱码丢出去：
- 字体名包含 Math/CMSY/CMMI/CMEX/MTSY/MTMI/MathJax/STIX 等 → 视为数学；
- 行里出现大量希腊字母/数学符号且与上下文字号差异较大 → 视为公式行。
"""

from __future__ import annotations

import re
from typing import List

from ..types import Line, TextBlock

_MATH_FONT_KEYWORDS = (
    "math",
    "cmsy",
    "cmmi",
    "cmex",
    "cmr",  # Computer Modern 经常被用于公式
    "mtsy",
    "mtmi",
    "mathjax",
    "stix",
    "esint",
    "msam",
    "msbm",
    "wasy",
    # TX/NewTX 字体族（LaTeX txfonts / newtx 宏包，极常见于学术论文）
    "newtxmi",  # NewTXMI, NewTXMI7, NewTXMI5
    "txsys",    # 数学符号
    "txmia",    # txmiaX 等
    "txex",     # txexs, txexas 等（大括号/定界符）
    "txbup",
    # AMS 字体
    "euex",
    "eufm",
    "eurm",
    "lasy",
    # CMEX / 其他常用数学字体
    "cmex10",
    "msam10",
    "msbm10",
)

_MATH_CHAR_RE = re.compile(
    r"[\u0370-\u03FF\u2200-\u22FF\u27C0-\u27EF\u2A00-\u2AFF\u2100-\u214F\u2190-\u21FF≤≥≠≈±×÷∑∏∫√∞∂∇·]"
)


def is_math_font(font: str) -> bool:
    f = font.lower()
    return any(k in f for k in _MATH_FONT_KEYWORDS)


def line_is_formula(line: Line) -> bool:
    text = line.text
    if not text.strip():
        return False
    math_chars = len(_MATH_CHAR_RE.findall(text))
    if math_chars >= 2 and math_chars / max(len(text), 1) > 0.1:
        return True
    # 全是数学字体的 span
    if all(s.is_mathlike for s in line.spans):
        return True
    return False


def block_is_display_formula(block: TextBlock) -> bool:
    """是否整块都像独立成段的公式。"""
    if not block.lines:
        return False
    return sum(1 for ln in block.lines if line_is_formula(ln)) == len(block.lines)


def wrap_math_in_text(text: str, spans: List) -> str:
    """在拼接行文本时，对数学型 span 用 `$...$` 包裹。

    连续的数学 span 合并到同一个 `$...$` 内，避免产生 `$a$$b$` 碎片。
    """
    # 先把 spans 按数学/非数学分组（游程编码）
    groups: list[tuple[bool, list]] = []
    for s in spans:
        t = s.text
        if not t:
            continue
        is_math = s.is_mathlike or bool(_MATH_CHAR_RE.search(t))
        if groups and groups[-1][0] == is_math:
            groups[-1][1].append(s)
        else:
            groups.append((is_math, [s]))

    parts = []
    for is_math, grp in groups:
        combined = "".join(s.text for s in grp).strip()
        if not combined:
            continue
        if is_math:
            parts.append(f"${combined}$")
        else:
            parts.append(combined)
    return "".join(parts)
