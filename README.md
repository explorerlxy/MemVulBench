# MemVulBench

面向 C/C++ **内存安全**漏洞挖掘研究的 benchmark：高密度、崩溃可验证、真值全自动。

一句话定位：**Magma 的密度 × ARVO 的严谨**。

- 每个漏洞都是真实的历史 OSS-Fuzz / CVE 漏洞，不是人工植入。
- 每个漏洞的真值是**实测的 sanitizer 崩溃见证 + PoC**，不是手写谓词。
  Magma 138 条里只有 45 条（32.6%）在真实测试场景下可观测；这里是 100%。
- 每个漏洞带**负对照**：同一 PoC 在未回退的干净基线上不崩溃。
- 全部限定为内存安全（空间 + 时效），并按 oracle 可见性分层标注。

详见 [docs/design.md](docs/design.md)。

## 现状

原型阶段。已完成：ARVO 语料普查、切片候选排名、基线选择与修复回退可行性分析。

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
| `docs/` | 设计、`bug.yaml` 契约、评测协议 |
| `memvul/` | Python 工具链：摄取 / 选片 / 构建 / 验证 / 归因 |
| `catalog/` | 漏洞真值，每漏洞一目录（纯文本，进 git） |
| `targets/` | 每项目的构建配方 |
| `data/` | 普查与规划输出 |

## 运行约束

仓库本身在 NTFS 上，**只放代码和元数据**。
克隆、构建、模糊测试战役一律落在 ext4（默认 `/tmp/memvul`）。
