# 考古目录契约

第一阶段交付物：每个 ARVO 核心内存漏洞数 **> 10** 的项目一份记录，
标明**天然潜伏数量最多的上游基线**，以及该基线上的漏洞清单。

目录根：`catalog/`。机器可读的总表是 `catalog/index.json`，人读总表是
`catalog/index.md`，每项目一份 `catalog/<project>/target.yaml`。

## `target.yaml`

```yaml
project: assimp
repo: https://github.com/assimp/assimp.git
n_sites: 42                          # 去重崩溃点（core, buildable）
n_issues: 48
harnesses: [assimp_fuzzer]

base:
  commit: d34cd103f477fba496f09e3daf49d3ce671eb21a
  date: 2021-09-09
  method: measured_sweep             # measured_sweep | wave_eve | unresolved
  n_latent: 25                       # 该基线上判定为天然潜伏的去重崩溃点数
  n_latent_upper: 25                 # 修复尚未落地的数量（含尚未引入的上界）
  n_wave: 8                          # 紧随其后的那一波批量修复规模（下界）
  note: null

waves:                               # 考虑过的批量修复日，按规模降序
  - day: 2021-10-29
    n: 8
    eve: 30f17aa2064b...             # 该波第一次修复的父提交
    n_latent_upper: 22

bugs:                                # 基线上判定潜伏的每一个去重崩溃点
  - oss_id: 42486052
    harness: assimp_fuzzer
    label: heap-oob-read
    cwe: CWE-125
    group: spatial
    fix_commit: 6a3ac623b960...
    fix_date: 2021-10-29
    crash_func: ...
    crash_file: ...
    signature: [heap-buffer-overflow, READ, ..., ...]
    status: latent                   # latent | not_latent | unresolved
    evidence: sweep                  # sweep | fix_not_landed | wave_member

rejected:
  - oss_id: 379418968
    reason: harness_bug
```

`n_latent` 的口径按 `method` 分三档，目录里必须写明用的是哪一档：

| method | `n_latent` 的含义 | 何时使用 |
|---|---|---|
| `measured_sweep` | PoC 开火且人工核验指纹匹配 | 已完成人工测量 |
| `wave_eve` | 修复尚未落地、且在基线之后两年内落地的去重崩溃点（上界） | 仓库可克隆、fix commit 可解析 |
| `unresolved` | 只能给出修复日直方图，没有可 checkout 的 sha | 仓库克隆失败或 fix 不在当前历史里 |

并列时取**较晚**的基线（未知漏洞污染较轻）。

当前 benchmark 的下载、人工编译/回放和持久化归档进展见
[docs/build-progress.md](build-progress.md)。`known_real` 只计 expected
之外的 unique 五元组。2026-09-14 的四元组备忘见 [known-real.md](known-real.md)。

## 人工编译/回放与最终准入

前台开工（决定编译哪个项目）仍要求目录里至少有 8 个 PoC，统计范围跨越
所有 harness。PoC 数按 `target.yaml` 中带 `oss_id` 的漏洞条目统计。

进入最终 benchmark 的项目级门槛是 **可验证内存漏洞数 ≥ 8**：
去重后的 expected 五元组 + unique `known_real` 五元组。少于 6 直接 pass；
6–7 暂缓，除非有明确人工复核。2026-09-18 起正式 20 席全部 ≥ 8：
arrow（7 expected + 1 目录外）经最终入口复验后替换 librawspeed（7，原经明确复核）。
当时的四元组 `known_real` 备忘见 [known-real.md](known-real.md)。
