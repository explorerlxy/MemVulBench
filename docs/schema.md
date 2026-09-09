# `bug.yaml` 契约

每个漏洞一个目录，目录里的 `bug.yaml` 是该漏洞的全部真值。
**原则：这个文件里的每个字段要么是从上游元数据抄来的出处信息，要么是本地实测出来的观测值。没有"人工判断"字段。**

```yaml
id: HFB-007                      # 稳定，不复用
status: admitted                 # admitted | rejected | pending
reject_reason: null              # 被拒时必填，见 §3

                                 # 准入要求 oracle.native 或 oracle.asan 开火

class:
  group: spatial                 # spatial | temporal
  label: heap-oob-write
  cwe: CWE-787

provenance:                      # 出处，抄自上游
  source: arvo
  oss_fuzz_issue: 42536390
  report: https://issues.oss-fuzz.com/issues/42536390
  cve: null
  fix_commit: 07afa23bd0fa74d18fb7faee898b2a876536a170
  repo: https://github.com/harfbuzz/harfbuzz.git

slice:
  project: harfbuzz
  harness: hb-subset-fuzzer
  base_commit: 9c1f0f4d...
  reintroduction: revert         # revert = 回退了修复；latent = 基线上本来就有

site:                            # 基线上的漏洞点，探针插在这里
  file: src/hb-subset-plan.cc
  function: hb_subset_plan_create_or_fail
  line: 412

oracle:                          # 实测矩阵，不是断言
  native:   {fired: false}
  asan:     {fired: true, kind: heap-buffer-overflow, access: WRITE, size: 4}
  msan:     {fired: false}
  ubsan:    {fired: false}
  valgrind: {fired: true, kind: InvalidWrite}

signature:                       # 崩溃归因的匹配依据；不含行号
  kind: heap-buffer-overflow
  access: WRITE
  crash_func: hb_subset_plan_create_or_fail
  crash_file: hb-subset-plan.cc
  alloc_func: hb_malloc

poc:
  - path: poc/001.ttf
    sha256: 3f9a...
    determinism: 5/5             # 5 次重放全部复现

control:                         # D4 条件 3 的负对照
  clean_base_fires: false        # 干净基线上同一 PoC 不崩 → revert 确实是成因

verified:
  at: 2026-09-08
  tool: memvul 0.1.0
  toolchain: clang-18.1.3
  asan_runtime: compiler-rt-18
```

## 1. 为什么 `signature` 不含行号

同一个漏洞回退到不同基线上，函数和文件不变，行号一定漂移。
归因用 `(kind, access, crash_func, crash_file)`；行号只作展示。

如果 slice 内两个漏洞的 signature 相同，它们**在评测中不可区分**，
按 D4 条件 6 合并为同一个 ID（`merged_from` 记录被合并的 OSS-Fuzz issue）。

## 2. 准入由 `oracle` 推导，不手填

```
admitted  ⟸  oracle.native.fired 或 oracle.asan.fired
excluded  ⟸  其余，按拒收原因分流到 data/excluded/
```

ASan 沉默但 MSan/Valgrind 开火的，记 `reject_reason: not_observable`
并保留完整 oracle 矩阵 —— 它们不进主目录，但是后续做检测器研究的现成素材。

## 3. 拒收原因（这些数据本身是结果）

| `reject_reason` | 含义 |
|---|---|
| `commit_missing` | fix commit 在当前仓库里不存在（rebase / 镜像不全） |
| `revert_conflict` | 修复补丁无法回退到基线 |
| `build_fail` | 回退后编译不过 |
| `no_repro` | 回退了但 PoC 不再触发（漏洞已被周边代码变更消解）—— **Magma 病** |
| `control_positive` | 干净基线上 PoC 也崩 → 崩的不是这个漏洞 |
| `nondeterministic` | 5 次重放不一致 |
| `signature_clash` | 与 slice 内其他漏洞不可区分，已合并 |
| `not_observable` | 确属内存违规，但 native 与 ASan 都沉默，超出可发现性口径 |
| `all_oracles_silent` | 无任何 oracle 见证 → Magma 的 `canary_only` 类 |

各原因的占比是论文里"为什么前向移植不可靠"的直接证据。
