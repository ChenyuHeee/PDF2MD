# Benchmark

放一些 PDF 样本到 `samples/`，将来用脚本批量跑 `pdf2md` 并与 ground-truth Markdown 对比：

- 编辑距离 / Levenshtein → 文本准确率
- TEDS → 表格结构准确率

建议样本类别：
- easy: 单栏电子书 / 报告
- paper: 双栏论文（含公式、图表）
- hard: 复杂财报 / 三栏排版 / 边注

未来可对比对象：marker、nougat、MinerU、Mathpix。
