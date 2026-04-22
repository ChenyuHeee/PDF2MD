# PDF2MD

把**文本型 PDF**（学术论文 / 电子书 / 电子版报告）转换为干净的 Markdown。

> 不是 OCR 工具：本项目假定 PDF 内嵌真实文本流。若你的 PDF 是扫描件，请先用
> [ocrmypdf](https://github.com/ocrmypdf/OCRmyPDF) 之类把文字层补上，再交给 `pdf2md`。

## 特性

- 双栏论文 **阅读顺序重建**（投影法检测列间空隙）
- **标题 / 段落 / 列表** 自动识别（基于全局正文字号 + 块级字体属性）
- **表格** 抽取（pdfplumber，支持 GFM / HTML 输出）
- **图片** 抽取并跨页**去重**（SHA1 hash），自动写入 `assets/`
- **公式**：数学字体 / 数学符号包成 `$...$` / `$$...$$`，不丢失
- 软换行合并：处理 `行尾连字符-` 与 CJK / 拉丁混排
- 提供 `pdf2md` CLI、Python API、可选 Gradio WebUI

## 安装

```bash
git clone https://github.com/ChenyuHeee/PDF2MD.git
cd PDF2MD
pip install -e .

# 想用 WebUI 的话：
pip install -e '.[webui]'
```

## Quick Start

```bash
pdf2md paper.pdf                       # 输出 paper.md（图片到 ./assets/）
pdf2md paper.pdf -o out/paper.md       # 指定输出
pdf2md paper.pdf --pages 1-5           # 只转前 5 页
pdf2md report.pdf --table-format html  # 复杂表格用 HTML 嵌入
pdf2md ebook.pdf --no-images           # 纯文本输出
```

Python API：

```python
from pdf2md import convert, ConvertOptions

convert(
    "paper.pdf",
    "paper.md",
    options=ConvertOptions(table_format="gfm", extract_images=True),
)
```

WebUI：

```bash
python -m pdf2md.webui
```

## 项目结构

```
pdf2md/
├── converter.py          # 主流程 pipeline
├── cli.py                # CLI 入口
├── webui.py              # Gradio WebUI（可选）
├── types.py              # 共享数据结构
├── extractors/
│   ├── text.py           # PyMuPDF 文本块抽取
│   ├── layout.py         # 阅读顺序 / 分栏检测
│   ├── tables.py         # pdfplumber 表格
│   ├── images.py         # 图片抽取 + 去重
│   └── formulas.py       # 公式启发式
├── postprocess/
│   ├── headings.py       # 标题分级
│   ├── paragraphs.py     # 段落合并 / 连字符
│   └── lists.py          # 列表识别
└── writers/
    └── markdown.py       # Markdown 渲染
```

## Roadmap

- [ ] 递归 XY-Cut，处理三栏 / 边注
- [ ] `--force-ocr` 选项（集成 ocrmypdf 兜底）
- [ ] 公式深度还原（接入 nougat / pix2tex）
- [ ] 表格跨页合并、合并单元格
- [ ] 基准测试套件（编辑距离 + TEDS），对比 marker / nougat / MinerU

## 已知坑

- 自定义字体编码（CID 没有 ToUnicode 映射）的 PDF 复制出来本来就是乱码，本项目无能为力，需先 OCR。
- 行间公式编号 `(1)`、`(2.3)` 当前会被并入正文，未单独处理。
- 1000+ 页电子书建议用 `--pages` 分段处理，避免一次性加载占用过大。

## License

MIT — 见 [LICENSE](LICENSE)。
