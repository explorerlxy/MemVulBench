# MemVulBench

面向 C/C++ **内存安全**漏洞挖掘研究的评测集：真实历史漏洞、固定上游提交、最终入口五元组身份。

正式评测集是 **20 个测试单元**（每项目一个对外 harness）。2026-09-18 按最终入口五元组准入（取代 2026-09-17 决定），已核验已知内存漏洞 **292**（expected 287 + 额外 5）。arrow（7 expected + 1 审计过的目录外指纹，8 个）经最终入口复验后替换 librawspeed（7 个，原靠明确复核纳入）。决定见 [`data/measure/admission/2026-09-18.json`](data/measure/admission/2026-09-18.json)。

- 每个漏洞来自真实 OSS-Fuzz / ARVO 历史材料，不是人工植入。
- 身份是指定 \(S,E\) 下的首错五元组：类型、方向、文件、行号、三帧哈希。PoC 只作存在性见证。
- 核心源码是上游某个未经修改的 commit；聚合包装器单独保存，不写入核心树。
- 编译、PoC 回放、指纹裁决和准入由操作者逐条执行，仓库脚本不代替这些步骤。

论文修订稿见 [`papers/MemVulBench/`](papers/MemVulBench/)。早期设计备忘见 [`docs/design.md`](docs/design.md)（已加状态说明，不覆盖现行账本）。

## 现状

第一阶段考古目录仍覆盖 ARVO 中去重核心内存漏洞 > 10 的项目，总表见 [`catalog/index.md`](catalog/index.md)。现行评测集从中选出 20 席（含 espeak-ng、ndpi；arrow 于 2026-09-18 替换 librawspeed 复席；lwan 已归档）。下载与战役日志见 [`docs/build-progress.md`](docs/build-progress.md)。

```bash
python3 -m memvul census                          # ARVO 6138 条的分类普查
python3 -m memvul slices --by project --labels    # 按项目排名
python3 -m memvul candidates --project assimp     # 批量修复日 → 候选基线
python3 -m memvul catalog                         # 遍历全部 >10 站点的项目，写 catalog/
python3 -m memvul measure --project assimp         # 准备 PoC 与 ARVO builder，之后人工操作
python3 -m memvul base --project assimp            # 分析已有的人工测量记录
```

搁置的 pin / slice / emit 在 `memvul.deferred`，不注册到 `python3 -m memvul`。

进入前台编译和回放的项目必须在项目级（跨 harness）拥有至少 8 个 PoC；少于 6 个直接 pass，6–7 个暂缓除非明确复核。最终准入计数是 unique expected 五元组 + unique `known_real` 五元组。

普查结果（ARVO-Meta v3，6138 条）：

| | 数量 |
|---|---:|
| 核心内存安全（空间 + 时效） | 3685 (60.0%) |
| 其中可构建（有 fix commit + 仓库，非 submodule） | 3670 |
| 去重后的**不同崩溃点** | 2833 |
| 去重后 >10 个崩溃点的**项目** | 64 |
| 去重后 >10 个崩溃点的 (项目, harness) 组 | 55 |

## 布局

| 路径 | 内容 |
|---|---|
| `docs/` | 目录契约、战役日志、早期设计备忘 |
| `memvul/` | 普查 / 候选基线 / 考古目录 / 目录分析 |
| `catalog/` | 第一阶段：每项目基线 + 潜伏漏洞清单 |
| `targets/` | 评测集物化结果（镜像、PoC、日志不进 Git） |
| `data/` | 普查、人工测量、复验与准入记录 |
| `papers/MemVulBench/` | v4 论文修订稿与证据 |

## 运行约束

仓库只放代码和元数据。克隆、构建、模糊测试战役落在 ext4（默认 `/tmp/memvul`）或外部归档，不进 Git。
