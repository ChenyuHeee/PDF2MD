"""主流程：协调各 extractor / postprocess / writer。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import fitz  # PyMuPDF
import pdfplumber

from .extractors.images import ImageWriter
from .extractors.layout import reading_order
from .extractors.tables import extract_tables
from .extractors.text import extract_blocks, filter_outside
from .postprocess.paragraphs import merge_paragraph_blocks
from .types import Page
from .writers.markdown import TableFormat, render


@dataclass
class ConvertOptions:
    extract_images: bool = True
    extract_tables: bool = True
    table_format: TableFormat = "gfm"
    page_range: Optional[tuple] = None  # (start, end), 1-based inclusive
    asset_subdir: str = "assets"


class Converter:
    def __init__(self, options: Optional[ConvertOptions] = None):
        self.options = options or ConvertOptions()

    def convert(self, pdf_path: str | Path, output_path: str | Path) -> Path:
        pdf_path = Path(pdf_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        asset_dir = output_path.parent / self.options.asset_subdir
        img_writer = (
            ImageWriter(asset_dir, rel_prefix=self.options.asset_subdir)
            if self.options.extract_images
            else None
        )

        pages: List[Page] = []
        with fitz.open(pdf_path) as doc, pdfplumber.open(pdf_path) as plumber_doc:
            n_pages = doc.page_count
            start, end = self._page_bounds(n_pages)

            for idx in range(start, end):
                fpage = doc.load_page(idx)
                ppage = plumber_doc.pages[idx]

                tables = extract_tables(ppage) if self.options.extract_tables else []
                excluded = [t.bbox for t in tables]

                images = img_writer.extract_page(doc, fpage) if img_writer else []
                # 图片占位区域也排除文本，避免重复
                excluded.extend(img.bbox for img in images)

                blocks = extract_blocks(fpage)
                blocks = filter_outside(blocks, excluded)

                blocks_sorted, _ = reading_order(blocks, fpage.rect.width)
                # 合并同段落的跨-block 续行（解决 PDF 每行一个 block 的问题）
                blocks_sorted = merge_paragraph_blocks(blocks_sorted)

                # 把 tables / images 按 y0 插入到合适的位置
                rect = fpage.rect
                page = Page(number=idx + 1, width=rect.width, height=rect.height)
                page.elements = self._merge_elements(blocks_sorted, tables, images)
                pages.append(page)

        markdown = render(pages, table_format=self.options.table_format)
        output_path.write_text(markdown, encoding="utf-8")
        return output_path

    # ----- helpers -----

    def _page_bounds(self, n_pages: int):
        if not self.options.page_range:
            return 0, n_pages
        s, e = self.options.page_range
        s = max(1, s) - 1
        e = min(n_pages, e)
        if e <= s:
            return 0, n_pages
        return s, e

    @staticmethod
    def _merge_elements(text_blocks, tables, images):
        """把 (text, table, image) 三类按"页面阅读顺序"的近似顺序穿插。

        策略：对 text_blocks 已按 (column, y, x) 排好；表格/图片各自带 bbox，
        我们按 y0 把它们插到第一个 y0 大于自身的文本块之前。
        """
        out = []
        text_iter = list(text_blocks)
        # 把 table/image 转成可排序条目
        extras = [("table", t, t.bbox[1]) for t in tables] + [
            ("image", i, i.bbox[1]) for i in images
        ]
        extras.sort(key=lambda x: x[2])

        i = 0
        for kind, el, y0 in extras:
            while i < len(text_iter) and text_iter[i].bbox[1] <= y0:
                out.append(("text", text_iter[i]))
                i += 1
            out.append((kind, el))
        while i < len(text_iter):
            out.append(("text", text_iter[i]))
            i += 1
        return out


def convert(
    pdf_path: str | Path,
    output_path: str | Path,
    *,
    options: Optional[ConvertOptions] = None,
) -> Path:
    return Converter(options).convert(pdf_path, output_path)
