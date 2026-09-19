# MemVulBench v1.0.0 发布目录

本目录按 `papers/MemVulBench/release-plan.md` 组织公开发布材料。发布范围：
**20 个准入测试单元、292 个经核验的唯一漏洞指纹**（预期 287 + 额外 5），
以 `data/measure/admission/2026-09-18.json` 为准；arrow 纳入，librawspeed
不纳入本版发布集合。

## 分层结构

| 层 | 位置 | 内容 |
|---|---|---|
| 软件与元数据 | git 仓库（标签 `memvulbench-v1.0.0`） | 目录、测量元数据、证据索引、分析代码、图表与文档 |
| 单元数据 | `units/<project>/` | 每单元：最终聚合镜像、计分 PoC、最终入口日志、验证日志、运行配置、SHA-256 清单 |
| 过程归档 | `process-archive/README.md` | 历史测试单元与旧版阅读包的索引（不与本版 20 单元混合计数） |

`units/` 下的镜像、PoC 与日志是对 `targets/` 持久材料的**硬链接**，不占额外
空间，也未纳入 git（`.gitignore` 已排除 `benchmark/units/`）。

## 匿名读者定位路径

1. 读 `manifest.json`：20 个单元、292 个指纹、各层哈希。
2. 任一指纹：查 `fingerprint-index.json`（键 `kind|access|file|line|h3`），
   得到所属单元、见证 PoC 的 `oss_id`、最终入口日志与目录关联（修复提交、报告）。
3. 对应单元：`units/<project>/manifest.json` 给出镜像 tar 与 SHA-256、二进制与
   包装器哈希、计分 PoC 与日志逐文件哈希；`run-config.json` 给出加载与回放命令。
4. 回放：`docker load -i image/<tar>` 后按 `run-config.json` 逐 PoC 执行；
   ASan 首错应与 `logs/final-entry/<oss_id>.log` 一致，其五元组应能在
   `fingerprint-index.json` 中按 `mvb:` 指纹号定位。

## 发布状态（2026-09-19）

- 数据层已整体发布于 Hugging Face：
  https://huggingface.co/datasets/Fisho0/MemVulBench （公开，66 文件，
  20 单元 + 索引；上传通道仅保留 HF，`scripts/hf_upload.py`）。
- 软件层：GitHub explorerlxy/MemVulBench，标签 memvulbench-v1.0.0。
- 镜像不做 GitHub Release 资产（单文件 <2 GiB 限制）。

## 复现打包

```bash
python3 scripts/build_release.py   # 从审定记录重建本目录（幂等）
```

准入、镜像加载、编译与 PoC 回放仍由操作者按仓库规则逐项执行；
`build_release.py` 只做材料组织与哈希清单。
