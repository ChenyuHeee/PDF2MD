"""可选 Gradio WebUI：``python -m pdf2md.webui``。

需要安装额外依赖：``pip install pdf2md[webui]``。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

try:
    import gradio as gr  # type: ignore
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "需要安装 gradio：pip install 'pdf2md[webui]' 或 pip install gradio"
    ) from e

from .converter import ConvertOptions, Converter


def _convert(file, extract_images: bool, extract_tables: bool, table_fmt: str):
    if file is None:
        return "请先上传 PDF。", None
    src = Path(file.name if hasattr(file, "name") else file)
    out_dir = Path(tempfile.mkdtemp(prefix="pdf2md_"))
    out_md = out_dir / (src.stem + ".md")
    opts = ConvertOptions(
        extract_images=extract_images,
        extract_tables=extract_tables,
        table_format=table_fmt,  # type: ignore[arg-type]
    )
    Converter(opts).convert(src, out_md)
    return out_md.read_text(encoding="utf-8"), str(out_md)


def build_app():
    with gr.Blocks(title="PDF2MD") as demo:
        gr.Markdown("# PDF2MD\n把文本型 PDF（论文 / 电子书）转换为干净的 Markdown。")
        with gr.Row():
            pdf = gr.File(label="PDF 文件", file_types=[".pdf"])
            with gr.Column():
                imgs = gr.Checkbox(value=True, label="抽取图片")
                tbls = gr.Checkbox(value=True, label="抽取表格")
                fmt = gr.Radio(["gfm", "html"], value="gfm", label="表格格式")
                btn = gr.Button("转换", variant="primary")
        md_view = gr.Code(label="Markdown 预览", language="markdown")
        md_file = gr.File(label="下载 .md")
        btn.click(_convert, inputs=[pdf, imgs, tbls, fmt], outputs=[md_view, md_file])
    return demo


def main():  # pragma: no cover
    build_app().launch()


if __name__ == "__main__":  # pragma: no cover
    main()
