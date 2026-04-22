"""使用 pdfplumber 检测并抽取表格。"""

from __future__ import annotations

import re
from typing import List

from ..types import TableBlock

# 连续重复字符（如 "TThh" "ssnn"），出现多次说明是图形渲染产物
_DBL_CHAR_RE = re.compile(r"(.)\1{1,}", re.UNICODE)
# 连词拼接（≥12 字母不含空格），通常来自旋转/缩放文本渲染失败
_CONCAT_WORD_RE = re.compile(r"[A-Za-z]{12,}")


def _is_figure_garbage(rows: List[List[str]]) -> bool:
    """判断一张"表格"实际上是矢量图被误识别产物。

    条件（任意一条成立即丢弃）：
    1. 任意单元格内连续重复字符序列 ≥ 3 对（高度可靠的乱码信号）
    2. 整张表格只有 1 行 1 列且单元格文字超过 200 字符
    3. 表格行数 ≤ 3 且非空单元格 ≤ 3，且存在 ≥12 字母连续（连词拼接）
    4. 单元格总数 ≥ 6，空白率 ≥ 60%，且所有非空单元格内容极短（< 20字符）
       —— 对应矢量图方块标签被误识别为稀疏表格的情形
    """
    all_text = " ".join(cell for row in rows for cell in row)
    non_empty = [cell for row in rows for cell in row if cell.strip()]

    # 条件 1：连续重复字符
    if len(_DBL_CHAR_RE.findall(all_text)) >= 3:
        return True

    # 条件 2：单行单列超长
    if len(rows) == 1 and len(rows[0]) == 1 and len(all_text) > 200:
        return True

    # 条件 3：非空单元格极少 + 含连词拼接文本
    if len(rows) <= 3 and len(non_empty) <= 3:
        for cell in non_empty:
            if _CONCAT_WORD_RE.search(cell):
                return True

    # 条件 4：高空白率 + 所有非空单元格为极短碎片
    total_cells = sum(len(row) for row in rows)
    if total_cells >= 6 and non_empty:
        empty_ratio = (total_cells - len(non_empty)) / total_cells
        if empty_ratio >= 0.6 and all(len(c) < 20 for c in non_empty):
            return True

    return False


def extract_tables(plumber_page) -> List[TableBlock]:
    """plumber_page 是 pdfplumber.page.Page。"""

    out: List[TableBlock] = []
    try:
        finder = plumber_page.find_tables()
    except Exception:
        return out

    for tbl in finder:
        try:
            data = tbl.extract()
        except Exception:
            continue
        if not data:
            continue
        # 规范化空单元格
        rows = [[(c or "").strip().replace("\n", " ") for c in row] for row in data]
        # 过滤完全空白的表
        if not any(any(cell for cell in row) for row in rows):
            continue
        # 过滤图形误识别的"假表格"
        if _is_figure_garbage(rows):
            continue
        out.append(TableBlock(bbox=tuple(tbl.bbox), rows=rows))
    return out
