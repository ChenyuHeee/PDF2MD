from pdf2md.postprocess.lists import to_list_item
from pdf2md.postprocess.paragraphs import merge_lines
from pdf2md.types import Line, Span


def _line(text, font="Helvetica"):
    sp = Span(text=text, bbox=(0, 0, 10, 10), size=10, font=font, flags=0)
    return Line(spans=[sp], bbox=(0, 0, 10, 10))


def test_hyphenation_join():
    out = merge_lines([_line("inter-"), _line("national policy")])
    assert "international policy" in out


def test_cjk_no_extra_space():
    out = merge_lines([_line("机器学"), _line("习方法")])
    assert out == "机器学习方法"


def test_latin_space_inserted():
    out = merge_lines([_line("hello"), _line("world")])
    assert out == "hello world"


def test_bullet_recognized():
    marker, body = to_list_item("• first item")
    assert marker == "-"
    assert body == "first item"


def test_numbered_recognized():
    marker, body = to_list_item("1. introduction")
    assert marker == "1."
    assert body == "introduction"


def test_plain_text_not_a_list():
    marker, body = to_list_item("just a sentence.")
    assert marker is None
