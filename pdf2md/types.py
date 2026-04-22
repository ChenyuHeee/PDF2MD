"""共享数据结构。所有提取模块都产出这些类型，由 writer 统一渲染。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal, Optional, Tuple

BBox = Tuple[float, float, float, float]  # (x0, y0, x1, y1)，PDF 坐标，y 向下


@dataclass
class Span:
    """一个排版片段（同字体、同字号的连续文本）。"""

    text: str
    bbox: BBox
    size: float
    font: str
    flags: int  # PyMuPDF 的字体 flags（bit4=bold, bit1=italic, ...）

    @property
    def is_bold(self) -> bool:
        return bool(self.flags & 16) or "Bold" in self.font

    @property
    def is_italic(self) -> bool:
        return bool(self.flags & 2) or "Italic" in self.font or "Oblique" in self.font

    @property
    def is_mathlike(self) -> bool:
        from .extractors.formulas import is_math_font

        return is_math_font(self.font)


@dataclass
class Line:
    spans: List[Span]
    bbox: BBox

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.spans)


@dataclass
class TextBlock:
    lines: List[Line]
    bbox: BBox
    column: int = 0  # 由 layout 推断


@dataclass
class TableBlock:
    bbox: BBox
    rows: List[List[str]]


@dataclass
class ImageBlock:
    bbox: BBox
    rel_path: str  # 相对 markdown 输出文件的路径
    caption: Optional[str] = None


PageElement = Tuple[Literal["text", "table", "image"], object]


@dataclass
class Page:
    number: int  # 1-based
    width: float
    height: float
    elements: List[PageElement] = field(default_factory=list)
