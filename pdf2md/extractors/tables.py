"""使用 pdfplumber 检测并抽取表格。"""

from __future__ import annotations

from typing import List

from ..types import TableBlock


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
        out.append(TableBlock(bbox=tuple(tbl.bbox), rows=rows))
    return out
