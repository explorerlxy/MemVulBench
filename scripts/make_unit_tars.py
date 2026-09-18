"""Create per-unit release tars and ScienceDB metadata cards.

Usage:
    python3 scripts/make_unit_tars.py --cards          # (re)generate all metadata cards
    python3 scripts/make_unit_tars.py --unit ghostpdl  # tar one unit for manual upload
    python3 scripts/make_unit_tars.py --unit ghostpdl --clean  # remove its tar after upload

Tars land in /tmp/memvul/release-upload/ (largest unit 6.1 GB; make them one at
a time and delete after upload). Packaging only: no compile, no replay.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "benchmark"
TAR_TMP = Path("/tmp/memvul/release-upload")
CARDS = BENCH / "checks" / "sciencedb-metadata"
GITHUB = "https://github.com/explorerlxy/MemVulBench"
TAG = "memvulbench-v1.0.0"
VERSION = "v1.0.0"

AUTHORS = ("芦笑瑜（Xiaoyu Lu）、魏强（Qiang Wei，通讯作者）、王云峰（Yunfeng Wang）；"
           "信息工程大学（Information Engineering University）")


def unit_names() -> list[str]:
    man = json.loads((BENCH / "manifest.json").read_text())
    return [Path(m).parts[-2] for m in man["unit_manifests"]]


def tar_path(project: str, commit: str) -> Path:
    return TAR_TMP / f"{project}-{commit[:12]}-v1.0.0.tar"


def make_tar(project: str) -> Path:
    manifest = json.loads((BENCH / f"units/{project}/manifest.json").read_text())
    tar = tar_path(project, manifest["source_commit"])
    if tar.exists():
        print(f"exists, reusing: {tar}")
        return tar
    TAR_TMP.mkdir(parents=True, exist_ok=True)
    print(f"tarring {project} -> {tar.name} ...", flush=True)
    with tarfile.open(tar, "w") as tf:
        tf.add(BENCH / "units" / project, arcname=project)
    print(f"done: {tar} ({tar.stat().st_size / 2**30:.2f} GiB)")
    print(f"after uploading this record: rm {tar}")
    return tar


def card(project: str) -> str:
    m = json.loads((BENCH / f"units/{project}/manifest.json").read_text())
    c = m["source_commit"][:12]
    n, routes = m["verified_memory_bug_count"], len(m["entry"]["mapping"])
    tar = tar_path(project, m["source_commit"]).name
    files = "\n".join(
        f"- `{p['path']}`" for p in
        [{"path": tar},
         {"path": "manifest.json"},
         {"path": "run-config.json"}])
    return f"""# ScienceDB 提交卡片：{project}

逐字段复制到 ScienceDB「提交数据」表单。文件在 `/tmp/memvul/release-upload/`
（先用 `python3 scripts/make_unit_tars.py --unit {project}` 生成 tar）。

## 标题（中文）
MemVulBench {VERSION} 测试单元：{project}（上游提交 {c}）

## 标题（英文）
MemVulBench {VERSION} test unit: {project} @ upstream commit {c}

## 作者
{AUTHORS}

## 摘要 / 描述
MemVulBench 是面向 C/C++ 内存安全模糊测试的真实多漏洞基准（20 个测试单元、
292 个经核验的唯一漏洞指纹）。本数据集是其一个测试单元：上游仓库
{m['upstream_repo']} 在提交 {m['source_commit']} 的未经修改源码上构建，
对外入口 {m['entry']['method']}（{routes} 个路由），含 {n} 个经核验的唯一
漏洞指纹（expected {m['expected_five_tuples']} + 经审计额外
{m['extra_five_tuples']}），每个指纹有触发 PoC、最终入口首错日志与
SHA-256 清单。tar 内含最终聚合 Docker 镜像、{len(m['scoring_pocs'])} 个计分
PoC 与全部验证日志；按 run-config.json 回放，各 PoC 首错应与
logs/final-entry/ 下对应日志一致。软件与跨单元指纹索引见
{GITHUB}（标签 {TAG}）。镜像内上游源码遵循其原始许可。

英文一句话版：One admitted test unit of MemVulBench {VERSION} (20 units, 292
verified unique memory-vulnerability fingerprints in total): upstream
{m['upstream_repo']} at commit {m['source_commit']}, entry
{m['entry']['method']} with {routes} routes, {n} verified fingerprints with
PoCs, final-entry first-fault logs and SHA-256 manifests.

## 关键词
fuzzing; memory safety; benchmark; ARVO; OSS-Fuzz; C/C++; {project}

## 许可
CC BY 4.0

## 版本
{VERSION}

## 关联论文
MemVulBench：面向 C/C++ 内存漏洞模糊测试的真实多漏洞基准构建（投稿中）。
软件仓库：{GITHUB}（标签 {TAG}）

## 本记录文件清单（3 个）
{files}
"""


def index_card() -> str:
    idx = json.loads((BENCH / "fingerprint-index.json").read_text())
    n = idx["unique_fingerprints"]
    return f"""# ScienceDB 提交卡片：索引记录（第 21 条）

## 标题（中文）
MemVulBench {VERSION} 指纹索引：{n} 个经核验漏洞指纹

## 标题（英文）
MemVulBench {VERSION} index: {n} verified vulnerability fingerprints

## 作者
{AUTHORS}

## 摘要 / 描述
MemVulBench {VERSION} 的机器可读总索引：20 个准入测试单元、{n} 个唯一漏洞
指纹（最终入口首错五元组）。每条指纹指向所属单元、见证 PoC、持久化首错
日志与目录关联（修复提交、问题报告）。各单元数据见 ScienceDB 对应记录；
软件见 {GITHUB}（标签 {TAG}）。

## 关键词
fuzzing; memory safety; benchmark; ground truth; fingerprint; ARVO; OSS-Fuzz

## 许可
CC BY 4.0

## 版本
{VERSION}

## 本记录文件清单（3 个）
- fingerprint-index.json
- manifest.json
- README.md
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", help="tar this unit for manual upload")
    ap.add_argument("--all", action="store_true", help="tar every unit in order")
    ap.add_argument("--clean", help="delete this unit's tar after a finished upload")
    ap.add_argument("--cards", action="store_true",
                    help="(re)generate all metadata cards under benchmark/checks/")
    args = ap.parse_args()

    if args.cards:
        CARDS.mkdir(parents=True, exist_ok=True)
        for p in unit_names():
            (CARDS / f"{p}.md").write_text(card(p))
        (CARDS / "_index.md").write_text(index_card())
        print(f"wrote {len(unit_names()) + 1} cards under {CARDS}")
    if args.unit:
        make_tar(args.unit)
    if args.all:
        for p in unit_names():
            make_tar(p)
    if args.clean:
        m = json.loads((BENCH / f"units/{args.clean}/manifest.json").read_text())
        t = tar_path(args.clean, m["source_commit"])
        t.unlink(missing_ok=True)
        print(f"removed {t}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
