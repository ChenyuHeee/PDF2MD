"""把 Page 序列渲染为 Markdown。"""

from __future__ import annotations

from typing import List, Literal

from ..extractors.formulas import block_is_display_formula
from ..postprocess.headings import estimate_body_size, heading_level
from ..postprocess.lists import to_list_item
from ..postprocess.paragraphs import merge_lines
from ..types import ImageBlock, Page, TableBlock, TextBlock

TableFormat = Literal["gfm", "html"]


def _render_table_gfm(tbl: TableBlock) -> str:
    if not tbl.rows:
        return ""
    header = tbl.rows[0]
    body = tbl.rows[1:] if len(tbl.rows) > 1 else []
    width = max(len(header), max((len(r) for r in body), default=0))
    header = (header + [""] * width)[:width]

    def fmt_row(cells):
        cells = (cells + [""] * width)[:width]
        return "| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |"

    sep = "| " + " | ".join(["---"] * width) + " |"
    out = [fmt_row(header), sep]
    for r in body:
        out.append(fmt_row(r))
    return "\n".join(out)


def _render_table_html(tbl: TableBlock) -> str:
    if not tbl.rows:
        return ""
    lines = ["<table>"]
    for i, row in enumerate(tbl.rows):
        tag = "th" if i == 0 else "td"
        cells = "".join(f"<{tag}>{(c or '').strip()}</{tag}>" for c in row)
        lines.append(f"  <tr>{cells}</tr>")
    lines.append("</table>")
    return "\n".join(lines)


def _render_image(img: ImageBlock) -> str:
    cap = img.caption or ""
    return f"![{cap}]({img.rel_path})"


def _render_text_block(block: TextBlock, body_size: float) -> str:
    if block_is_display_formula(block):
        body = " ".join(ln.text.strip() for ln in block.lines if ln.text.strip())
        return f"$$\n{body}\n$$"

    text = merge_lines(block.lines)
    if not text:
        return ""

    level = heading_level(block, body_size)
    if level:
        return "#" * min(level, 6) + " " + text

    marker, body = to_list_item(text)
    if marker:
        return f"{marker} {body}"
    return text


def render(pages: List[Page], *, table_format: TableFormat = "gfm") -> str:
    body_size = estimate_body_size(
        [
            [el for kind, el in p.elements if kind == "text"]  # type: ignore[misc]
            for p in pages
        ]
    )

    parts: List[str] = []
    for page in pages:
        for kind, el in page.elements:
            if kind == "text":
                s = _render_text_block(el, body_size)  # type: ignore[arg-type]
                if s:
                    parts.append(s)
            elif kind == "table":
                if table_format == "html":
                    parts.append(_render_table_html(el))  # type: ignore[arg-type]
                else:
                    parts.append(_render_table_gfm(el))  # type: ignore[arg-type]
            elif kind == "image":
                parts.append(_render_image(el))  # type: ignore[arg-type]

    # 用空行分隔；并合并连续列表项之间的空行
    md = "\n\n".join(p for p in parts if p)
    return _tighten_lists(md) + "\n"


def _tighten_lists(md: str) -> str:
    """把连续的列表项之间的空行去掉，让 GFM 认为是同一个列表。"""

    out_lines = []
    lines = md.split("\n")
    for i, line in enumerate(lines):
        if (
            line == ""
            and i > 0
            and i + 1 < len(lines)
            and _is_list_line(lines[i - 1])
            and _is_list_line(lines[i + 1])
        ):
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


def _is_list_line(s: str) -> bool:
    s = s.lstrip()
    if s.startswith("- "):
        return True
    if len(s) > 2 and s[0].isdigit() and s[1:3] in (". ", ") "):
        return True
    return False
