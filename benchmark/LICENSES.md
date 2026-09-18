# 许可（草案，待作者确认后生效）

> 状态：以下许可选择是发布方案第 3 节"为原创代码确定许可"的落地草案。
> 正式生效需作者书面确认；确认后本文件拆分为仓库根目录 `LICENSE` 与
> `DATA-LICENSE`，并在各归档记录回填。

## 原创软件代码

建议 **MIT License**（`memvul/`、`scripts/` 中原创部分）。

## 数据、目录与文档

建议 **CC BY 4.0**（`catalog/`、`data/measure/` 元数据、`docs/`、
`papers/` 证据索引、`benchmark/` 清单与索引）。

## 不由本仓库再分发的材料

- **上游源码与测试单元镜像**：镜像 tar 含上游项目源码与 ARVO 衍生构建层。
  各单元 `manifest.json` 记录上游仓库与精确提交；许可遵循上游项目与 ARVO
  的条款。若某单元许可不允许再分发，该单元归档记录只提供上游来源、获取或
  重建说明与 SHA-256，并注明复验限制。
- **PoC 触发输入**：来自 OSS-Fuzz / ARVO 公开问题记录；逐单元清单已在
  `manifest.json` 标注 `oss_id`，原始出处见 `fingerprint-index.json` 的
  `catalog_link.report`。
- **第三方材料**：`third_party/magma-v1.2.1-official-replay.md` 为核对备忘，
  Magma 本体遵循其自身许可。
