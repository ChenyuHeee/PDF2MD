"""分栏检测的纯函数测试，不依赖 PDF 文件。"""

from pdf2md.extractors.layout import detect_column_split, reading_order
from pdf2md.types import Line, Span, TextBlock


def _block(x0, y0, x1, y1):
    span = Span(text="x", bbox=(x0, y0, x1, y1), size=10, font="Helvetica", flags=0)
    line = Line(spans=[span], bbox=(x0, y0, x1, y1))
    return TextBlock(lines=[line], bbox=(x0, y0, x1, y1))


def test_single_column_returns_none():
    blocks = [_block(50, 100 + i * 20, 550, 115 + i * 20) for i in range(10)]
    assert detect_column_split(blocks, width=600) is None


def test_two_columns_detected_and_ordered():
    # 左栏 x=50~280，右栏 x=320~550，中间 280~320 完全没文字
    left = [_block(50, 100 + i * 20, 280, 115 + i * 20) for i in range(8)]
    right = [_block(320, 100 + i * 20, 550, 115 + i * 20) for i in range(8)]
    blocks = left + right

    split = detect_column_split(blocks, width=600)
    assert split is not None
    assert 280 < split < 320

    ordered, _ = reading_order(blocks, width=600)
    # 左栏整体应排在右栏前面
    midpoint = len(ordered) // 2
    assert all(b.column == 0 for b in ordered[:midpoint])
    assert all(b.column == 1 for b in ordered[midpoint:])
