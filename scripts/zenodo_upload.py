"""Upload MemVulBench release artifacts to Zenodo via the REST API.

Usage:
    export ZENODO_TOKEN=...
    python3 scripts/zenodo_upload.py --unit ghostpdl          # one unit record
    python3 scripts/zenodo_upload.py --index                  # the index record
    python3 scripts/zenodo_upload.py --unit ghostppl --deposit-id 12345   # resume

Each unit record gets three files: a tar of benchmark/units/<project>/ plus the
browsable manifest.json and run-config.json. Drafts are left unpublished for
operator review; add --publish to submit for publishing after checking.

Only packaging and upload: nothing here compiles, replays or admits.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "benchmark"
TAR_TMP = Path("/tmp/memvul/release-upload")

API = "https://zenodo.org/api"
SANDBOX_API = "https://sandbox.zenodo.org/api"
LICENSE = "cc-by-4.0"
VERSION = "memvulbench-v1.0.0"


def http(url: str, token: str, method: str = "GET",
         data: bytes | None = None, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, method=method, data=data, headers={
        "Authorization": f"Bearer {token}",
        **(headers or {}),
    })
    with urllib.request.urlopen(req) as resp:
        body = resp.read()
        return json.loads(body) if body else {}


def upload_file(bucket: str, token: str, name: str, path: Path) -> None:
    url = f"{bucket}/{name}"
    size = path.stat().st_size
    print(f"  uploading {name} ({size / 2**30:.2f} GiB) ...", flush=True)
    req = urllib.request.Request(url, method="PUT", data=open(path, "rb"),
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "application/octet-stream"})
    with urllib.request.urlopen(req) as resp:
        print(f"  -> {resp.status} {name}")


def unit_tar(project: str) -> Path:
    manifest = json.loads((BENCH / f"units/{project}/manifest.json").read_text())
    commit = manifest["source_commit"][:12]
    TAR_TMP.mkdir(parents=True, exist_ok=True)
    tar = TAR_TMP / f"{project}-{commit}-v1.0.0.tar"
    if tar.exists():
        print(f"  reusing {tar}")
        return tar
    print(f"  tarring {project} -> {tar.name} ...", flush=True)
    with tarfile.open(tar, "w") as tf:
        tf.add(BENCH / "units" / project, arcname=project)
    return tar


def metadata(title: str, description: str) -> dict:
    return {
        "metadata": {
            "title": title,
            "upload_type": "dataset",
            "publication_date": "2026-09-18",
            "creators": [
                {"name": "Lu, Xiaoyu", "affiliation": "Information Engineering University"},
                {"name": "Wei, Qiang", "affiliation": "Information Engineering University"},
                {"name": "Wang, Yunfeng", "affiliation": "Information Engineering University"},
            ],
            "description": description,
            "license": LICENSE,
            "keywords": ["fuzzing", "memory safety", "benchmark", "ARVO",
                         "OSS-Fuzz", "C", "C++"],
            "version": VERSION,
        }
    }


def describe_unit(project: str) -> tuple[str, str, list[Path]]:
    manifest = json.loads((BENCH / f"units/{project}/manifest.json").read_text())
    title = f"MemVulBench v1.0.0 test unit: {project} @ {manifest['source_commit'][:12]}"
    n = manifest["verified_memory_bug_count"]
    description = (
        f"<p>One admitted test unit of MemVulBench v1.0.0 (20 units, 292 verified "
        f"unique memory-vulnerability fingerprints in total).</p>"
        f"<p>Upstream: <code>{manifest['upstream_repo']}</code> at commit "
        f"<code>{manifest['source_commit']}</code>. "
        f"Entry: {manifest['entry']['method']} with {len(manifest['entry']['mapping'])} routes. "
        f"Verified unique fingerprints in this unit: <b>{n}</b> "
        f"({manifest['expected_five_tuples']} expected + "
        f"{manifest['extra_five_tuples']} audited extra).</p>"
        f"<p>The tar contains the final aggregate image (docker load -i), the "
        f"{len(manifest['scoring_pocs'])} scoring PoCs, final-entry logs and "
        f"verification logs; every file's SHA-256 is in manifest.json. "
        f"Replay per run-config.json; each PoC's first fault should reproduce "
        f"the corresponding final-entry log.</p>"
        f"<p>Software and the cross-unit fingerprint index: see the MemVulBench "
        f"GitHub repository, tag {VERSION}. The image embeds upstream sources "
        f"under their original licenses.</p>")
    files = [unit_tar(project),
             BENCH / f"units/{project}/manifest.json",
             BENCH / f"units/{project}/run-config.json"]
    return title, description, files


def describe_index() -> tuple[str, str, list[Path]]:
    idx = json.loads((BENCH / "fingerprint-index.json").read_text())
    title = f"MemVulBench v1.0.0 index: {idx['unique_fingerprints']} verified fingerprints"
    description = (
        f"<p>Machine-readable index for MemVulBench v1.0.0: 20 admitted test "
        f"units and {idx['unique_fingerprints']} verified unique vulnerability "
        f"fingerprints (first-fault five-tuples on the final entry). Each entry "
        f"points to its unit, witness PoCs, persisted first-error logs and "
        f"catalog links (fix commit, issue report).</p>"
        f"<p>Unit data records are deposited as separate Zenodo records; "
        f"software at the GitHub repository, tag {VERSION}.</p>")
    return title, description, [
        BENCH / "fingerprint-index.json",
        BENCH / "manifest.json",
        BENCH / "README.md",
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit")
    ap.add_argument("--index", action="store_true")
    ap.add_argument("--deposit-id", type=int,
                    help="resume an existing draft instead of creating one")
    ap.add_argument("--publish", action="store_true",
                    help="submit the draft for publishing (irreversible)")
    ap.add_argument("--sandbox", action="store_true",
                    help="use sandbox.zenodo.org for a dry run")
    args = ap.parse_args()
    if not args.unit and not args.index:
        ap.error("need --unit <project> or --index")
    token = os.environ.get("ZENODO_TOKEN")
    if not token:
        sys.exit("set ZENODO_TOKEN first (Zenodo profile -> Applications)")
    api = SANDBOX_API if args.sandbox else API

    if args.index:
        title, description, files = describe_index()
    else:
        title, description, files = describe_unit(args.unit)

    if args.deposit_id:
        dep = http(f"{api}/deposit/depositions/{args.deposit_id}", token)
        print(f"resuming draft {args.deposit_id}")
    else:
        dep = http(f"{api}/deposit/depositions", token, method="POST",
                   data=b"{}", headers={"Content-Type": "application/json"})
        print(f"draft created: id={dep['id']}")
    dep_id = dep["id"]
    bucket = dep["links"]["bucket"]

    for f in files:
        upload_file(bucket, token, f.name, f)

    meta = metadata(title, description)
    http(f"{api}/deposit/depositions/{dep_id}", token, method="PUT",
         data=json.dumps(meta).encode(),
         headers={"Content-Type": "application/json"})
    print(f"metadata set; draft links:")
    print(f"  edit/review: https://{'sandbox.' if args.sandbox else ''}zenodo.org/deposit/{dep_id}")
    if args.publish:
        http(f"{api}/deposit/depositions/{dep_id}/actions/publish", token,
             method="POST")
        print("PUBLISHED")
    else:
        print("review the draft in the browser, then publish there "
              "(or rerun with --deposit-id <id> --publish)")
    if not args.sandbox:
        doi_file = BENCH / "checks" / "zenodo-dois.json"
        dois = json.loads(doi_file.read_text()) if doi_file.exists() else {}
        dois[str(dep_id)] = {"record": args.unit or "index", "title": title,
                             "published": bool(args.publish)}
        doi_file.write_text(json.dumps(dois, indent=1, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
