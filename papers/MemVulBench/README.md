# MemVulBench 论文材料

现行工作稿为 `manuscript.md`（内部修订稿，2026-09-18），配套补充材料为 `supplement.md`。
20 个测试单元已按最终入口五元组准入，共 292 个计分项（预期 287、额外 5）；
2026-09-18 arrow 替换 librawspeed，现行决定见仓库根目录 `data/measure/admission/2026-09-18.json`。
这一数量不等同于逐项证明的独立根因数。

## 阅读入口

| 文件 | 内容 |
|---|---|
| `manuscript.md` | 现行工作稿（4 张主表、2 张主图） |
| `supplement.md` | 补充材料 S1：统计契约、37 项目录去向、配置实例与五元组契约 |
| `revision-checklist.md` | 投稿前补证清单（含 2026-09-18 替换更新） |
| `revision-v4/gap-assessment.md` | 四项标准下的证据与剩余限制（历史审查） |
| `revision-v4/material-chain.md` | 记录层材料链与准入数字（v4 时代） |
| `revision-v4/change-summary.md` | 作者共识到实际修改的对应表（v4 时代） |
| `evidence/rereplay_fingerprint_ledger.json` | 最终入口五元组身份账本（现行） |
| `evidence/standards_gap_audit.json` | 逐单元证据状态 |
| `sources.md`、`references.bib` | 引文与来源边界 |
| `MemVulBench-v4-portable.zip` | **封存的 2026-09-17 v4 阅读包**（291 计数时代），仅作历史快照 |

压缩版期刊变体 `MemVulBench_manuscript_revised.md` 已移出仓库，存于
`/media/hahafish/Data/ForUbuntu/backup/`（2026-09-18）；本目录不再维护该副本。
`portable/` 目录与 v2／v3 阅读包已于 2026-09-18 清理（与 v4 zip 内容重复或被其覆盖）。

## 本轮边界

292 是指定环境下已观察的五元组计分数；未知故障仍可能存在，且五元组与独立根因
不保证一一对应。类型取自五元组 `kind`。目录关联组 290 与最终五元组 292 数字不同、
组成亦不同。数量对评测粒度和整体效能只作定性论证。

## evidence/ 时效说明（2026-09-18）

- 席位／准入级文件已随 arrow 替换手工同步：`selected_projects.{csv,md}`、
  `all_manual_projects.csv`、`version_provenance.csv`、`summary.json`、
  `selected_recorded_details.json`、`standards_gap_audit.json`。
- 观测级誊录保留 2026-09-17 审计快照，未随替换重写：`observation_register.json`、
  `recorded_verdicts.csv`、`field_audit.csv`、`material_chain{,_groups,_units}.csv`
  与 `material_chain.json`。librawspeed 的观测链保留作过程证据；arrow 的对应
  材料见 `data/measure/manual/arrow/` 与 `data/measure/rereplay/2026-09-18/`。
- `rereplay_fingerprint_ledger.json` 为现行账本（301 条观测：2026-09-17 批次
  去掉 librawspeed 后 292 条，加 2026-09-18 arrow 批次 9 条）。
- `scripts/audit_standards.py` 仍按旧账本 schema（`units` 键）编写，复用前需与
  现行 `observations` 列表结构对齐；其余脚本只读测量元数据，不决定准入。

## v4 历史写作工件的再生流程

确认原始来源未变后，在仓库根目录依次运行：

```bash
python3 papers/MemVulBench/scripts/export_evidence.py
python3 papers/MemVulBench/scripts/analyze_snapshot.py
python3 papers/MemVulBench/scripts/build_material_chain.py
python3 papers/MemVulBench/scripts/audit_standards.py      # 需先修复账本 schema 漂移
python3 papers/MemVulBench/scripts/compute_rereplay_fingerprints.py
python3 papers/MemVulBench/scripts/make_figures.py
python3 papers/MemVulBench/scripts/package_revision.py
python3 papers/MemVulBench/scripts/validate_revision.py
```

`export_evidence.py` / `analyze_snapshot.py` 只读测量元数据。五元组账本由
`compute_rereplay_fingerprints.py` 读取已写复验日志；当前账本已经 2026-09-18
替换合并，重跑该脚本前需确认复验日志仍在。准入不由这些脚本决定。绘图需要
Matplotlib。检查结果是写作一致性，不是重新回放。
