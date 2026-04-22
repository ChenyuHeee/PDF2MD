"""命令行入口：``pdf2md input.pdf -o output.md``。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Tuple

import click

from . import __version__
from .converter import ConvertOptions, Converter


def _parse_pages(value: Optional[str]) -> Optional[Tuple[int, int]]:
    if not value:
        return None
    try:
        if "-" in value:
            a, b = value.split("-", 1)
            return int(a), int(b)
        n = int(value)
        return n, n
    except ValueError as e:
        raise click.BadParameter(f"--pages 期望 'N' 或 'N-M' 格式，得到 {value!r}") from e


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("input_pdf", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "-o",
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="输出 .md 文件路径（默认与 PDF 同名）。",
)
@click.option("--no-images", is_flag=True, help="不抽取图片。")
@click.option("--no-tables", is_flag=True, help="不抽取表格。")
@click.option(
    "--table-format",
    type=click.Choice(["gfm", "html"]),
    default="gfm",
    show_default=True,
    help="表格输出格式：GFM Markdown 或 HTML。",
)
@click.option("--pages", default=None, help="只转换指定页码，例如 '1-10' 或 '5'。")
@click.option(
    "--asset-dir",
    default="assets",
    show_default=True,
    help="图片相对子目录名（相对输出 .md）。",
)
@click.version_option(__version__, "-V", "--version")
def main(
    input_pdf: Path,
    output: Optional[Path],
    no_images: bool,
    no_tables: bool,
    table_format: str,
    pages: Optional[str],
    asset_dir: str,
):
    """把文本型 PDF（论文/电子书）转换为干净的 Markdown。"""

    if output is None:
        output = input_pdf.with_suffix(".md")

    opts = ConvertOptions(
        extract_images=not no_images,
        extract_tables=not no_tables,
        table_format=table_format,  # type: ignore[arg-type]
        page_range=_parse_pages(pages),
        asset_subdir=asset_dir,
    )
    try:
        out = Converter(opts).convert(input_pdf, output)
    except Exception as e:  # noqa: BLE001
        click.echo(f"[pdf2md] 转换失败: {e}", err=True)
        sys.exit(1)

    click.echo(f"[pdf2md] 已写出: {out}")


if __name__ == "__main__":
    main()
