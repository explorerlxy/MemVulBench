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
  vul_commit: 3ab19f70...        # ARVO 镜像 config blob 里记录的漏洞版本，白送的
  repo: https://github.com/harfbuzz/harfbuzz.git

target:                          # 目标 = 上游某个未经修改的 commit
  project: harfbuzz
  harness: hb-subset-fuzzer
  base_commit: 9c1f0f4d...       # 唯一的目标定义；git checkout 即可复验
  latent: true                   # 恒为 true —— 纯考古路线下漏洞天然存在于 base_commit

site:                            # 基线上的漏洞点，仅供展示，不参与任何判定
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
    fires_at_base: true          # D4 闸门 1
    signature_match: true        # D4 闸门 2

verified:
  at: 2026-09-09
  tool: memvul 0.1.0
  toolchain: clang-18.1.3
  asan_runtime: compiler-rt-18
```

纯考古路线下，`bug.yaml` 里**没有** pin 表、保真 manifest、存活窗口、开关名、
负对照与隔离对照字段——这些都是文件级 pin 方案的产物，随该方案一并搁置
（[methodology.md](methodology.md) §9）。若日后启用机会主义 pin，再补 `pins` 段。

## 1. 为什么 `signature` 不含行号

基线 commit 与 ARVO 记录的漏洞版本 commit 通常不是同一个，函数和文件不变但行号一定漂移。
归因用 `(kind, access, crash_func, crash_file)`，行号只作展示。

指纹有三个用途，都是机械判定：

1. **sweep 判活**：候选基线上"PoC 开火 **且** 指纹匹配 ARVO 参考"才算该漏洞在此基线上潜伏。
   只看开火不看指纹会把撞到别的漏洞算成成功——这是 Magma 病的入口。
2. **目标内可区分**：两个漏洞 signature 相同则在评测中不可区分，
   按 D4 闸门 3 合并为同一个 ID（`merged_from` 记录被合并的 OSS-Fuzz issue）。
3. **战役归因**：把工具的 `crashes/` 灌进 recover build，按指纹映射到 bug ID。

## 2. 准入由 `oracle` 推导，不手填

```
admitted  ⟸  oracle.native.fired 或 oracle.asan.fired
excluded  ⟸  其余，按拒收原因分流到 data/excluded/
```

ASan 沉默但 MSan/Valgrind 开火的，记 `reject_reason: not_observable`
并保留完整 oracle 矩阵 —— 它们不进主目录，但是后续做检测器研究的现成素材。

## 3. 拒收原因

| `reject_reason` | 含义 |
|---|---|
| `poc_missing` | ARVO 镜像里取不到 PoC，无法验证 |
| `commit_missing` | fix commit 在当前仓库里不存在（rebase / 镜像不全） |
| `not_latent` | PoC 在基线上不开火 —— 漏洞在该 commit 上尚未引入、已被修复，或被周边代码临时遮蔽 |
| `signature_mismatch` | 崩了但指纹与 ARVO 参考不符 → 撞上了别的漏洞 |
| `signature_clash` | 与目标内其他漏洞不可区分，已合并 |
| `harness_bug` | 漏洞位于 harness 文件内，切换基线会改变 harness，排除 |
| `not_observable` | 确属内存违规，但 native 与 ASan 都沉默，超出可发现性口径 |
| `all_oracles_silent` | 无任何 oracle 见证 → Magma 的 `canary_only` 类 |

`not_latent` 会是占比最大的一类，这是纯考古路线的正常代价：
它换来的是剩下那批漏洞的 100% 可信度。各原因的占比随数据一并记录在 `data/sweeps/`。
