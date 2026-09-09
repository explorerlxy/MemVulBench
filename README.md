# MemVulBench

面向 C/C++ **内存安全**漏洞挖掘研究的评测平台：高密度、崩溃可验证、真值全自动。

**定位**：不是要独立发表的 benchmark artifact，而是支撑 fuzzing 技术研究的评测平台。
唯一判据是能不能可信地支撑"本方法比 baseline 发现更多漏洞"。

- 每个漏洞都是真实的历史 OSS-Fuzz 漏洞，不是人工植入。
- 每个漏洞的真值是**实测的 sanitizer 崩溃见证 + PoC**，不是手写谓词。
  Magma 138 条里只有 45 条（32.6%）在真实测试场景下可观测；这里是 100%。
- 每个目标就是**上游某个未经修改的 commit**，`git checkout` 即可复验。
  零补丁、零 pin、零手写代码。
- 全部限定为内存安全（空间 + 时效），并按 oracle 可见性分层标注。

设计见 [docs/design.md](docs/design.md)，构建方法论见 [docs/methodology.md](docs/methodology.md)。

## 现状

原型阶段。已完成 ARVO 语料普查、切片候选排名、assimp 端到端闭环实验、方法论定稿。

两条被淘汰的构建路线（[docs/feasibility.md](docs/feasibility.md)）：

- **修复回退**——已被实测否定。补丁 12/12 干净应用，漏洞只有 3/14 复现。
- **文件级时间 pin**——未被否定，但为把密度从 8 推到 26 要付十倍工程量，降级为可选增量。

同一实验的第三行是现行方案的依据：**同基线上天然潜伏的漏洞复现率 6/6（100%）**。
现行路线是**纯考古**——找到漏洞本来就共存的那个 commit，不做任何改动。
单目标密度 6–12，总量靠目标数量：12 个目标 ≈ 100+ 个可观测漏洞，是 Magma 的两倍以上。

```bash
python3 -m memvul census                          # ARVO 6138 条的分类普查
python3 -m memvul slices --by harness --labels    # 候选项目排名
python3 -m memvul candidates --project assimp     # fix 日期直方图 → 候选基线（零构建）
python3 -m memvul sweep --project assimp --harness assimp_fuzzer \
        --container memvul-assimp                 # 各候选基线的天然产量实测
python3 -m memvul base   --project assimp --harness assimp_fuzzer   # 取 argmax
python3 -m memvul verify --project assimp --harness assimp_fuzzer   # 三道闸门
python3 -m memvul emit   --project assimp --harness assimp_fuzzer   # 物化目标
```

`memvul pin` / `memvul slice` 属于可选增量（[methodology.md](docs/methodology.md) §9），
本轮搁置，代码保留。

普查结果（ARVO-Meta v3，6138 条）：

| | 数量 |
|---|---:|
| 核心内存安全（空间 + 时效） | 3685 (60.0%) |
| 其中可构建（有 fix commit + 仓库，非 submodule） | 3670 |
| 去重后的**不同崩溃点** | 2833 |
| 去重后 ≥10 个崩溃点的 (项目, harness) 组 | 62 |

## 布局

| 路径 | 内容 |
|---|---|
| `docs/` | 设计、构建方法论、`bug.yaml` 契约、确定性契约（搁置） |
| `memvul/` | Python 工具链：普查 / 选片 / 候选基线 / sweep / 验证 / 物化 |
| `targets/` | 每目标一个基线 commit + 漏洞清单 + PoC |
| `data/` | 普查、候选基线、sweep 结果 |

## 运行约束

仓库本身在 NTFS 上，**只放代码和元数据**。
克隆、构建、模糊测试战役一律落在 ext4（默认 `/tmp/memvul`）。
