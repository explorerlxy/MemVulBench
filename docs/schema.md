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

window:                          # 实测存活区间，不是 SZZ 估计（methodology.md §7）
  intro: 4b2c8e91...             # PoC 首次开火的 commit
  fix: 07afa23b...               # 修复 commit，窗口右开
  probes: 14                     # 二分用掉的构建次数
  contiguous: true               # false 时 gaps 字段记录被临时遮蔽的区间

slice:
  project: harfbuzz
  harness: hb-subset-fuzzer
  base_commit: 9c1f0f4d...
  purity: mosaic                 # pure = 基线上天然潜伏，零 pin；mosaic = 有 pin
  toggle: MEMVUL_BUG_HFB_007     # configure 开关；共用 pin 时多个漏洞共享同一开关单元
  toggle_unit: [HFB-007]         # 不可独立开关时列出同单元的全部漏洞

pins:                            # 空表 ⟺ purity: pure
  - file: src/hb-subset-plan.cc
    fidelity: file               # file = 整文件逐字节等于上游；function = tier-2 逃生舱
    on:  {commit: 3ab19f70..., blob_sha256: 1c4e...}   # vul-pin
    off: {commit: 07afa23b..., blob_sha256: 9d02...}   # fix-pin，负对照用
    direction: backward          # backward = commit < base；forward = commit > base
    reason: fix_touched          # fix_touched | expand_compile | expand_repro
mosaic:                          # 切片级指标在 targets/<p>/pins.yaml 里汇总，这里存本漏洞的贡献
  files_pinned: 1
  temporal_distance_days: 138    # |date(vul-pin) - date(base)|

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

control:
  off_state_fires: false         # D4 条件 4：切到 fix-pin 后不崩 → 崩的确实是这个漏洞
  isolated_fires: true           # D4 条件 5：只开本漏洞的构建上同样复现
                                 # isolated_fires ≠ 切片上复现 → 存在漏洞间干扰，记入干扰量

verified:
  at: 2026-09-08
  tool: memvul 0.1.0
  toolchain: clang-18.1.3
  asan_runtime: compiler-rt-18
```

## 1. 为什么 `signature` 不含行号

同一个漏洞 pin 到不同基线上，函数和文件不变，行号一定漂移。
归因用 `(kind, access, crash_func, crash_file)`；行号只作展示。
指纹同时是**窗口实测的判据**：sweep 时"PoC 开火且指纹匹配"才算漏洞在该 commit 上存活。

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
| `no_source_change` | fix commit 未改动任何源文件，认领集为空 |
| `window_unmeasured` | sweep 未能定出存活窗口（PoC 在任何探针点都不开火） |
| `build_fail` | pin 之后编译不过，且扩张到 E4 仍失败 |
| `no_repro` | pin 了但 PoC 不再触发 —— **Magma 病** |
| `signature_mismatch` | 崩了但指纹与 ARVO 参考不符 → 撞上了别的漏洞 |
| `control_positive` | 切到 fix-pin（OFF）后 PoC 仍崩 → 崩的不是这个漏洞 |
| `conflict_dropped` | 与切片内更高价值的漏洞认领同一文件且窗口不相交，落选 |
| `mosaic_budget` | 认领集扩张后超出 `mosaic_ratio` / `temporal_spread` 上限 |
| `harness_bug` | 漏洞位于 harness 文件内，按 methodology.md §6 硬约束排除 |
| `signature_clash` | 与 slice 内其他漏洞不可区分，已合并 |
| `not_observable` | 确属内存违规，但 native 与 ASan 都沉默，超出可发现性口径 |
| `all_oracles_silent` | 无任何 oracle 见证 → Magma 的 `canary_only` 类 |

各原因的占比是论文里"漏洞搬运为什么会失败"的直接证据。
`nondeterministic` 待确定性闸门接入后启用（见 [determinism.md](determinism.md)）。
