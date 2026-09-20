"""Upload the MemVulBench release to a ModelScope dataset repository.

Prereq (once):   modelscope login            # paste your access token
                 # or: export MODELSCOPE_TOKEN=...

    python3 scripts/ms_upload.py --index           # card + fingerprint index + checks
    python3 scripts/ms_upload.py --unit arrow      # tar -> upload -> clean, per unit
    python3 scripts/ms_upload.py --unit arrow --keep-tar

Default repo: hahafisho0/MemVulBench (create it once on modelscope.cn if missing).
Direct domestic connection: proxies are stripped for this script.
ModelScope has no resumable upload; per-unit batching keeps retry cost small,
and --use-cache skips files whose content is already on the server.
Packaging only: no compile, no replay, no admission.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "benchmark"
TAR_TMP = Path("/tmp/memvul/release-upload")
STAGE = TAR_TMP / "ms-stage"
DEFAULT_REPO = "hahafisho0/MemVulBench"


def clean_env() -> dict[str, str]:
    """ModelScope is domestic: drop proxy variables for direct connection."""
    return {k: v for k, v in os.environ.items()
            if not k.lower().endswith("_proxy")}


def tar_path(project: str) -> Path:
    commit = json.loads(
        (BENCH / f"units/{project}/manifest.json").read_text())["source_commit"]
    return TAR_TMP / f"{project}-{commit[:12]}-v1.0.0.tar"


def make_tar(project: str) -> Path:
    tar = tar_path(project)
    if tar.exists():
        print(f"reusing {tar}")
        return tar
    TAR_TMP.mkdir(parents=True, exist_ok=True)
    print(f"tarring {project} -> {tar.name} ...", flush=True)
    with tarfile.open(tar, "w") as tf:
        tf.add(BENCH / "units" / project, arcname=project)
    return tar


def upload(local: Path, remote: str, repo: str, token: str | None) -> None:
    cmd = ["modelscope"]
    if token:
        cmd += ["--token", token]
    cmd += ["upload", "--repo-type", "dataset", repo, str(local), remote]
    print(f"  $ {' '.join(cmd[1:])}", flush=True)
    subprocess.run(cmd, check=True, env=clean_env())


def stage_unit(project: str) -> Path:
    tar = make_tar(project)
    dest = STAGE / "units" / project
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy(tar, dest / tar.name)
    shutil.copy(BENCH / f"units/{project}/manifest.json", dest / "manifest.json")
    shutil.copy(BENCH / f"units/{project}/run-config.json", dest / "run-config.json")
    return dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--unit")
    ap.add_argument("--index", action="store_true",
                    help="upload README card, fingerprint index, manifest and checks")
    ap.add_argument("--keep-tar", action="store_true")
    args = ap.parse_args()
    repo = args.repo
    token = os.environ.get("MODELSCOPE_TOKEN")

    if not args.unit and not args.index:
        ap.error("need --unit <project> or --index")

    if args.index:
        if STAGE.exists():
            shutil.rmtree(STAGE)
        STAGE.mkdir(parents=True)
        shutil.copy(BENCH / "MS-CARD.md", STAGE / "README.md")
        shutil.copy(BENCH / "fingerprint-index.json", STAGE / "fingerprint-index.json")
        shutil.copy(BENCH / "manifest.json", STAGE / "manifest.json")
        checks = STAGE / "checks"
        checks.mkdir()
        shutil.copy(BENCH / "checks" / "hash-verification.json", checks)
        shutil.copy(BENCH / "checks" / "path-scan.json", checks)
        upload(STAGE / "README.md", "README.md", repo, token)
        for f in ("fingerprint-index.json", "manifest.json"):
            upload(STAGE / f, f, repo, token)
        for f in sorted(checks.iterdir()):
            upload(f, f"checks/{f.name}", repo, token)
        shutil.rmtree(STAGE)
        print("index uploaded")

    if args.unit:
        stage_unit(args.unit)
        d = STAGE / "units" / args.unit
        try:
            for f in sorted(d.iterdir()):
                upload(f, f"units/{args.unit}/{f.name}", repo, token)
        except Exception:
            if not args.keep_tar:
                tar_path(args.unit).unlink(missing_ok=True)
                shutil.rmtree(d, ignore_errors=True)
                print(f"cleaned after failure")
            raise
        if not args.keep_tar:
            t = tar_path(args.unit)
            t.unlink(missing_ok=True)
            shutil.rmtree(d, ignore_errors=True)
            print(f"cleaned {t}")
        print(f"unit {args.unit} uploaded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
