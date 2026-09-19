"""Upload the MemVulBench release to a Hugging Face dataset repository.

Usage (token once):   hf auth login          # write token
    python3 scripts/hf_upload.py --create               # private dataset repo + card/index
    python3 scripts/hf_upload.py --unit arrow           # tar -> upload -> clean, per unit
    python3 scripts/hf_upload.py --public               # flip to public when done
    python3 scripts/hf_upload.py --unit arrow --keep-tar  # keep the tar (default deletes)

Default repo: Fisho0/MemVulBench (override with --repo).
Uploads resume safely: rerun any command; unchanged files are skipped.
Packaging only: no compile, no replay, no admission.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tarfile
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "benchmark"
TAR_TMP = Path("/tmp/memvul/release-upload")
STAGE = TAR_TMP / "hf-stage"
DEFAULT_REPO = "Fisho0/MemVulBench"


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


def stage_unit(repo_layout: Path, project: str) -> Path:
    """Materialise units/<p>/{tar,manifest.json,run-config.json} in the stage."""
    tar = make_tar(project)
    dest = repo_layout / "units" / project
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy(tar, dest / tar.name)
    shutil.copy(BENCH / f"units/{project}/manifest.json", dest / "manifest.json")
    shutil.copy(BENCH / f"units/{project}/run-config.json", dest / "run-config.json")
    return dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--create", action="store_true",
                    help="create the dataset repo (private) and upload card/index")
    ap.add_argument("--unit")
    ap.add_argument("--index", action="store_true",
                    help="(re)upload card, fingerprint index, manifest and checks")
    ap.add_argument("--public", action="store_true",
                    help="flip the dataset to public (do this last)")
    ap.add_argument("--keep-tar", action="store_true",
                    help="keep the unit tar in /tmp after uploading")
    args = ap.parse_args()

    api = HfApi()
    who = api.whoami()
    print(f"authenticated as {who['name']}")

    if args.create:
        api.create_repo(args.repo, repo_type="dataset", private=True,
                        exist_ok=True)
        print(f"dataset repo ready (private): {args.repo}")

    if args.create or args.index:
        idx = STAGE
        if idx.exists():
            shutil.rmtree(idx)
        idx.mkdir(parents=True)
        shutil.copy(BENCH / "HF-CARD.md", idx / "README.md")
        shutil.copy(BENCH / "fingerprint-index.json", idx / "fingerprint-index.json")
        shutil.copy(BENCH / "manifest.json", idx / "manifest.json")
        checks = idx / "checks"
        checks.mkdir()
        shutil.copy(BENCH / "checks" / "hash-verification.json", checks)
        shutil.copy(BENCH / "checks" / "path-scan.json", checks)
        api.upload_large_folder(args.repo, folder_path=idx, repo_type="dataset")
        print("card/index uploaded")

    if args.unit:
        stage_unit(STAGE, args.unit)
        api.upload_large_folder(args.repo, folder_path=STAGE, repo_type="dataset")
        if not args.keep_tar:
            t = tar_path(args.unit)
            t.unlink(missing_ok=True)
            shutil.rmtree(STAGE / "units" / args.unit, ignore_errors=True)
            print(f"cleaned {t}")
        print(f"unit {args.unit} uploaded")

    if args.public:
        api.update_repo_settings(args.repo, repo_type="dataset", private=False)
        print(f"{args.repo} is now PUBLIC: "
              f"https://huggingface.co/datasets/{args.repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
