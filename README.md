# MemVulBench

面向 C/C++ **内存安全**漏洞挖掘研究的 benchmark：高密度、崩溃可验证、真值全自动。

一句话定位：**Magma 的密度 × ARVO 的严谨**。

- 每个漏洞都是真实的历史 OSS-Fuzz / CVE 漏洞，不是人工植入。
- 每个漏洞的真值是**实测的 sanitizer 崩溃见证 + PoC**，不是手写谓词。
  Magma 138 条里只有 45 条（32.6%）在真实测试场景下可观测；这里是 100%。
- **保真不变式**：切片中每个参与编译的源文件都逐字节等于某个上游 commit 的 blob，
  manifest 记录对应关系，任何人可用 `git cat-file` 复验。Magma 给不出这条保证。
- 每个漏洞带**负对照**：把它切到 OFF（换成修复后的文件）后同一 PoC 不崩溃。
- 全部限定为内存安全（空间 + 时效），并按 oracle 可见性分层标注。

设计见 [docs/design.md](docs/design.md)，搬运方法论见 [docs/methodology.md](docs/methodology.md)。

## 现状

原型阶段。已完成：ARVO 语料普查、切片候选排名、assimp 端到端闭环实验、搬运方法论定稿。

关键实验结论（[docs/feasibility.md](docs/feasibility.md)）：**修复回退机制已被实测否定**
——补丁 12/12 干净应用，漏洞只有 3/14 复现，而同一基线上天然潜伏的是 6/6。
现行方案是文件级时间 pin，详见方法论文档。

```bash
python3 -m memvul census                          # ARVO 6138 条的分类普查
python3 -m memvul slices --by harness --labels    # 候选切片排名
python3 -m memvul plan --project harfbuzz \
        --harness hb-subset-fuzzer                # 为一个切片挑基线
```

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
| `docs/` | 设计、搬运方法论、`bug.yaml` 契约、确定性契约 |
| `memvul/` | Python 工具链：摄取 / 选片 / sweep / pin / 验证 / 归因 |
| `catalog/` | 漏洞真值，每漏洞一目录（纯文本，进 git） |
| `targets/` | 每项目的构建配方 |
| `data/` | 普查与规划输出 |

## 运行约束

仓库本身在 NTFS 上，**只放代码和元数据**。
克隆、构建、模糊测试战役一律落在 ext4（默认 `/tmp/memvul`）。
