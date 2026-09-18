---
license: cc-by-4.0
task_categories:
- other
tags:
- fuzzing
- memory-safety
- security
- benchmark
- ARVO
- OSS-Fuzz
- C
- C++
language:
- en
- zh
pretty_name: MemVulBench
size_categories:
- 10GB<n<100GB
---

# MemVulBench v1.0.0

A real-world multi-bug benchmark for C/C++ memory-safety fuzzing:
**20 admitted test units, 292 verified unique memory-vulnerability fingerprints**
(287 expected + 5 audited extra). Each unit is one real upstream project at one
unmodified historical commit, driven through a single final entry point
(identity or byte-prefix dispatch), with per-fingerprint triggering PoCs,
persisted first-fault ASan logs and SHA-256 manifests.

## Layout

```
units/<project>/                            # browsable metadata (3 small files each)
  <project>-<commit12>-v1.0.0.tar           # final aggregate image + PoCs + logs
  manifest.json                             # per-file SHA-256, upstream commit, entry map
  run-config.json                           # docker load / replay commands, ASAN_OPTIONS
fingerprint-index.json                      # 292 fingerprints -> unit, PoC, log, fix commit
manifest.json                               # release manifest (20 units, 292 fingerprints)
checks/hash-verification.json               # 20/20 image sha256 recomputed & matched
README.md                                   # this card
```

## Quickstart

```bash
pip install -U "huggingface_hub[hf_xet]"
huggingface-cli download explorerlxy/MemVulBench --repo-type dataset \
    --include "units/arrow/*" --local-dir memvulbench

docker load -i memvulbench/units/arrow/arrow-8b09ecc5c690-v1.0.0.tar  # inside the tar
# replay per units/arrow/run-config.json; each PoC's first fault should match
# the corresponding final-entry log in the tar.
```

Mainland-China users can download without a VPN by prepending:

```bash
export HF_ENDPOINT=https://hf-mirror.com
```

## Provenance & license

- Software, catalog and evidence: <https://github.com/explorerlxy/MemVulBench>
  (tag `memvulbench-v1.0.0`; code MIT, data/docs CC BY 4.0).
- Every unit is an unmodified upstream commit recorded in its manifest; the
  images embed upstream sources under their original licenses.
- All bugs are historically public, upstream-fixed OSS-Fuzz issues (fix
  commits recorded per fingerprint in `fingerprint-index.json`).

## Citation

```bibtex
@dataset{memvulbench-v1.0.0,
  title  = {MemVulBench: A Real-World Multi-Bug Benchmark for C/C++ Memory-Safety Fuzzing},
  author = {Lu, Xiaoyu and Wei, Qiang and Wang, Yunfeng},
  year   = {2026},
  version= {v1.0.0},
  url    = {https://huggingface.co/datasets/explorerlxy/MemVulBench}
}
```
