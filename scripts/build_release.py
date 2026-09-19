"""Stage the MemVulBench public release tree under benchmark/.

Reads the audited records (admission, manual measures, final-entry rereplay,
fingerprint ledger, catalog targets) and materialises per-unit archives with
hard links to the persisted images, scoring PoCs and logs. Every staged file
is listed with a SHA-256 in the unit manifest. Nothing here compiles, replays
or admits: packaging only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "benchmark"
ADMISSION = ROOT / "data/measure/admission/2026-09-18.json"
REREPLAY = {
    "arrow": ROOT / "data/measure/rereplay/2026-09-18/arrow.json",
}
CATALOG = ROOT / "catalog"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def link(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        dest.unlink()
    os.link(source, dest)


def load_repo_url(project: str) -> str | None:
    text = (CATALOG / project / "target.yaml").read_text()
    m = re.search(r'^repo:\s*"?(.+?)"?\s*$', text, re.M)
    return m.group(1) if m else None


def load_yaml_bugs(project: str) -> dict[str, dict]:
    """Minimal key: value + '- oss_id:' list reader for catalog target.yaml."""
    text = (CATALOG / project / "target.yaml").read_text()
    bugs: dict[str, dict] = {}
    current: dict | None = None
    for line in text.splitlines():
        m = re.match(r"\s*- oss_id: (\d+)", line)
        if m:
            current = {"oss_id": m.group(1)}
            bugs[m.group(1)] = current
            continue
        if current is not None:
            m = re.match(r"\s+(fix_commit|report|crash_file|crash_func|cwe): (.+)", line)
            if m:
                current[m.group(1)] = m.group(2).strip().strip('"')
    return bugs


def main() -> None:
    admission = json.loads(ADMISSION.read_text())
    ledger = json.loads(
        (ROOT / "papers/MemVulBench/evidence/rereplay_fingerprint_ledger.json").read_text())
    if BENCH.exists():
        shutil.rmtree(BENCH)
    units_root = BENCH / "units"
    units_root.mkdir(parents=True)

    # fingerprint key -> index entry (built from ledger observations)
    by_key: dict[str, dict] = {}
    for obs in ledger["observations"]:
        fp = obs.get("fingerprint")
        if not fp:  # clean observations carry no identity
            continue
        entry = by_key.setdefault(fp["key"], {
            "fingerprint_id": fp["fingerprint_id"],
            "key": fp["key"],
            "kind": fp["kind"],
            "access": fp["access"],
            "file": fp["file"],
            "line": fp["line"],
            "h3": fp["h3"],
            "project": obs["project"],
            "verdicts": [],
            "witness_oss_ids": [],
            "final_entry_logs": [],
            "adjudication": fp.get("adjudication"),
        })
        entry["witness_oss_ids"].append(obs["oss_id"])
        entry["verdicts"].append(obs["verdict"])
        entry["final_entry_logs"].append(
            f"units/{obs['project']}/logs/final-entry/{obs['oss_id']}.log")

    unit_records = []
    problems: list[str] = []
    for unit in admission["units"]:
        project = unit["project"]
        manual = json.loads(Path(ROOT / unit["measure"]).read_text())
        agg = manual["aggregation"]
        rr_path = REREPLAY.get(project, ROOT / f"data/measure/rereplay/2026-09-17/{project}.json")
        rereplay = json.loads(rr_path.read_text())
        udir = units_root / project

        image = Path(agg["image_archive"])
        link(image, udir / "image" / image.name)

        pocs = []
        for obs in rereplay["observations"]:
            oss_id = obs["oss_id"]
            src = ROOT / "targets" / project / "pocs" / "agg" / str(oss_id)
            if not src.exists():
                problems.append(f"{project}: scoring PoC {oss_id} missing at {src}")
                continue
            link(src, udir / "pocs" / str(oss_id))
            pocs.append({"oss_id": oss_id, "sha256": sha256_file(src),
                         "bytes": src.stat().st_size})

        final_logs = []
        for obs in rereplay["observations"]:
            persisted = Path(obs["persisted_log"])
            if not persisted.exists():
                problems.append(f"{project}: persisted log {persisted} missing")
                continue
            link(persisted, udir / "logs" / "final-entry" / f"{obs['oss_id']}.log")
            final_logs.append({"oss_id": obs["oss_id"], "sha256": sha256_file(persisted),
                               "bytes": persisted.stat().st_size})

        # supplementary pre-final verification logs (aggregate + original runs)
        supp = []
        logs_root = ROOT / "targets" / project / "logs"
        if logs_root.is_dir():
            for d in sorted(p for p in logs_root.iterdir()
                            if p.is_dir() and "rereplay" not in p.name):
                for f in sorted(d.rglob("*")):
                    if not f.is_file() or f.is_symlink():
                        continue
                    rel = f"logs/verification-{d.name}/{f.relative_to(d)}"
                    link(f, udir / rel)
                    supp.append({"path": rel, "sha256": sha256_file(f),
                                 "bytes": f.stat().st_size})

        keys = sorted({k for k, e in by_key.items() if e["project"] == project})
        manifest = {
            "project": project,
            "source_commit": unit["source_commit"],
            "upstream_repo": load_repo_url(project),
            "verified_memory_bug_count": unit["verified_memory_bug_count"],
            "expected_five_tuples": unit["expected_five_tuples"],
            "extra_five_tuples": unit["extra_five_tuples"],
            "entry": {"method": agg["method"], "mapping": agg["mapping"]},
            "image": {"file": f"image/{image.name}",
                      "sha256_recorded": agg["image_archive_sha256"],
                      "bytes": image.stat().st_size,
                      "docker_tag": agg.get("image")},
            "final_binary": {"path": agg["binary"], "sha256": agg["binary_sha256"]},
            "wrapper": {"path": agg["source"], "sha256": agg["source_sha256"]},
            "scoring_pocs": pocs,
            "final_entry_logs": final_logs,
            "verification_logs": supp,
            "fingerprints": [by_key[k]["fingerprint_id"] for k in keys],
            "measure_record": unit["measure"],
            "rereplay_record": str(rr_path.relative_to(ROOT)),
        }
        (udir / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
        (udir / "run-config.json").write_text(json.dumps({
            "runner": "standalone main (one input per process)",
            "binary": agg["binary"],
            "asan_options": rereplay["asan_options"],
            "timeout_seconds": rereplay["timeout_seconds"],
            "docker_load": f"docker load -i image/{image.name}",
            "docker_run": (f"docker run --rm -v $PWD/pocs:/work/pocs {agg.get('image')} "
                           f"sh -c 'cd /work && timeout {rereplay['timeout_seconds']} "
                           f"{agg['binary']} /work/pocs/<oss_id>'"),
            "env": {"ASAN_OPTIONS": rereplay["asan_options"]},
        }, indent=1) + "\n")
        unit_records.append(manifest)

    catalog_cache = {p: load_yaml_bugs(p) for p in
                     {u["project"] for u in admission["units"]}}
    for entry in by_key.values():
        entry["classification"] = ("extra_known_real"
                                   if "known_real" in entry["verdicts"] else "expected")
        cat = catalog_cache[entry["project"]]
        links = [cat[str(o)] for o in entry["witness_oss_ids"] if str(o) in cat]
        entry["catalog_link"] = [{
            "oss_id": b["oss_id"], "fix_commit": b.get("fix_commit"),
            "report": b.get("report"), "cwe": b.get("cwe"),
        } for b in links] or None
        entry["unit_manifest"] = f"units/{entry['project']}/manifest.json"

    index = {
        "identity_rule": "kind|access|file|line|h3 (first fault, final entry)",
        "admission": "data/measure/admission/2026-09-18.json",
        "ledger": "papers/MemVulBench/evidence/rereplay_fingerprint_ledger.json",
        "unique_fingerprints": len(by_key),
        "fingerprints": sorted(by_key.values(),
                               key=lambda e: (e["project"], e["fingerprint_id"])),
    }
    (BENCH / "fingerprint-index.json").write_text(json.dumps(index, indent=1) + "\n")

    release = {
        "release": "memvulbench-v1.0.0",
        "created": "2026-09-18",
        "admission_decision": "data/measure/admission/2026-09-18.json",
        "units": len(unit_records),
        "verified_memory_bug_count": admission["verified_memory_bug_count"],
        "unique_expected": admission["unique_expected_five_tuples"],
        "unique_extra_known_real": admission["unique_extra_five_tuples_outside_expected"],
        "unit_manifests": [f"units/{m['project']}/manifest.json" for m in unit_records],
        "layers": {
            "software": "git repository at tag memvulbench-v1.0.0",
            "unit_data": "benchmark/units/<project>/ (published on https://huggingface.co/datasets/Fisho0/MemVulBench)",
            "process_archive": "benchmark/process-archive/README.md",
        },
    }
    (BENCH / "manifest.json").write_text(json.dumps(release, indent=1) + "\n")

    summary = {
        "units": len(unit_records),
        "fingerprints": len(by_key),
        "scoring_pocs": sum(len(m["scoring_pocs"]) for m in unit_records),
        "final_entry_logs": sum(len(m["final_entry_logs"]) for m in unit_records),
        "verification_logs": sum(len(m["verification_logs"]) for m in unit_records),
        "image_bytes_total": sum(m["image"]["bytes"] for m in unit_records),
        "problems": problems,
    }
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
