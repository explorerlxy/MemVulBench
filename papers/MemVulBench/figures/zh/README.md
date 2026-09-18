# 中文论文图的数据与核对记录

图 1 和图 2 使用最终准入快照 `data/measure/admission/2026-09-18.json` 确定 20 个单元及其数量。19 个保留项目的指纹来自 `papers/MemVulBench/evidence/rereplay_fingerprint_ledger.json`；新准入的 arrow 来自 `data/measure/rereplay/2026-09-18/arrow.json`。以“项目＋最终首错指纹键”去重，并逐项目核对准入快照中的目录关联、目录外和总计数。构图过程仅读取现有记录，不执行编译或 PoC。

- 图 1：20 个单元，目录关联指纹 287 个、经审计的目录外指纹 5 个，共 292 个；每单元 8–35 个。
- 图 2：同一批 292 个唯一指纹的 12 种首错类型及读／写方向；堆缓冲区越界 183 个。准入记录的 300 条输入级错误类型观测含重复见证，不能当作唯一漏洞类型分布。
- 绘图脚本：`papers/MemVulBench/scripts/make_figures_zh.py`；随图保存 `figure_fingerprints.csv` 和 `figure_unit_counts.csv` 以便核对。每张图提供 SVG、PDF、600 dpi PNG 和 LZW TIFF。
- 静态图检查：19 项通过、0 项失败；160 mm 宽度提示为常见默认宽度之外，已按本稿 A4 双栏页面的 172 mm 文字区检查。两张 PDF 的最小文字均为 8 pt；Word 第 11–12 页的实际排版已目视检查。
