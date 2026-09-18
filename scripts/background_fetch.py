"""Continuously fetch and persist benchmark PoCs and one builder image per project.

The downloader intentionally uses a project-scoped temporary directory and
removes it after the PoCs have been copied to the persistent archive.  It does
not compile or run targets; that work remains in the foreground.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from memvul import arvo, fetch, measure  # noqa: E402

WORK = Path("/tmp/memvul/poc-download")
ACTIVE = WORK.parent / "active"
STATUS = ROOT / "data" / "measure" / "downloads"
LOCK = Path("/tmp/memvul/background-fetch.lock")
MIN_FREE_BYTES = 50 * 1024**3
FETCH_STRATEGY = "abort-after-large-layer-v3"
# Construction refill after dropping binutils-gdb (harness suite too
# scattered). Do not retry ffmpeg / imagemagick / gdal. Already-eligible
# and already-measured pass/deferred projects are not listed.
BENCHMARK20_DOWNLOAD = [
    "skia",
    "openh264",
    "espeak-ng",
    "ndpi",
    "hunspell",
    "openthread",
    "lcms",
    "libvips",
    "wolfssl",
    "icu",
    "wireshark",
]


def candidates() -> list[arvo.Candidate]:
    cache = ROOT / "data" / "census" / "arvo_candidates.json"
    raw = json.loads(cache.read_text())
    return [arvo.Candidate(**{k: v for k, v in row.items() if k != "site_key"})
            for row in raw]


def project_ids(rec: dict) -> list[int]:
    """Return every project PoC; admission is project-level, not harness-level."""
    return sorted({int(b["oss_id"]) for b in rec.get("bugs", [])
                   if b.get("oss_id") is not None})


def remove_image_if_loaded_here(tag: str) -> None:
    subprocess.run(["docker", "image", "rm", "-f", tag],
                   capture_output=True, text=True, timeout=120)


def previous_attempts(project: str) -> int:
    marker = STATUS / f"{project}.json"
    if not marker.exists():
        return 0
    try:
        return int(json.loads(marker.read_text()).get("attempt", 0))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return 0


def fetch_project(project: str) -> dict:
    rec = measure.load_target(project)
    ids = project_ids(rec)
    bug_rows = [row for row in (rec.get("bugs") or [])
                if int(row["oss_id"]) in set(ids)]
    dest = WORK / project
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    result: dict = {"project": project, "ids": ids, "failed_poc": [],
                    "attempt": previous_attempts(project) + 1,
                    "fetch_strategy": FETCH_STRATEGY}
    try:
        n_poc, missing = measure.restore_pocs(project, bug_rows, dest)
        if missing:
            hmap = {int(row["oss_id"]): row.get("harness") or ""
                    for row in bug_rows}
            fetched, failed = measure.fetch_pocs(
                missing, dest,
                on_success=lambda _oid: measure.persist_pocs(
                    project, bug_rows, src_root=dest),
                harness_by_id=hmap)
            n_poc += fetched
        else:
            failed = []
        result.update({"n_poc": n_poc, "failed_poc": failed})
        measure.persist_pocs(project, bug_rows, src_root=dest)
        index_path = measure.POC_STORE / project / "index.json"
        try:
            index = json.loads(index_path.read_text())
        except (OSError, json.JSONDecodeError):
            index = {}
        result["archived_poc"] = sum(1 for oid in ids if str(oid) in index)
        if n_poc == 0:
            result["status"] = "poc_failed"
            return result

        fetched = [oid for oid in ids if (dest / str(oid) / "poc").exists()]
        for oid in measure.pick_builders(rec, fetched):
            tag = f"n132/arvo:{oid}-vul"
            archive = fetch.store_tar(f"{oid}-vul")
            if archive.exists() and archive.stat().st_size > 0:
                result["image"] = str(archive)
                result["image_source"] = "archive"
                break
            free = shutil.disk_usage(archive.parent).free
            if free < MIN_FREE_BYTES:
                result["status"] = "paused_low_disk"
                result["free_bytes"] = free
                return result
            info = fetch.load_into_docker("n132/arvo", f"{oid}-vul")
            archive = fetch.store_tar(f"{oid}-vul")
            result["image"] = str(archive)
            result["image_source"] = info.get("source", "registry")
            remove_image_if_loaded_here(tag)
            break
        else:
            result["status"] = "no_builder"
            return result

        result["status"] = "partial" if failed else "ok"
        if failed and result["attempt"] >= 3:
            result["status"] = "blocked_missing_poc"
            result["note"] = ("PoC extraction failed repeatedly; delete this "
                              "marker to retry after the registry changes.")
        return result
    finally:
        # Preserve every PoC obtained before a slow registry response or
        # operator interruption; the next pass can resume from the archive.
        try:
            measure.persist_pocs(project, bug_rows, src_root=dest)
        except Exception as exc:  # noqa: BLE001
            print(f"    WARN partial PoC persist failed: {exc}", flush=True)
        shutil.rmtree(dest, ignore_errors=True)


def write_status(project: str, result: dict) -> None:
    STATUS.mkdir(parents=True, exist_ok=True)
    (STATUS / f"{project}.json").write_text(
        json.dumps(result, indent=1, ensure_ascii=False) + "\n")


def run(interval: int, retry_projects: list[str] | None = None) -> None:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    forced = list(retry_projects or [])
    with LOCK.open("w") as fh:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("background fetch is already running")
        while True:
            pending = []
            seen: set[str] = set()

            def needs_download(project: str) -> bool:
                if (ACTIVE / project).exists():
                    return False
                marker = STATUS / f"{project}.json"
                if not marker.exists():
                    return True
                try:
                    old = json.loads(marker.read_text())
                    old_status = old.get("status")
                    old_archived = int(old.get("archived_poc", 0))
                    current_total = measure.project_poc_count(
                        measure.load_target(project))
                    done = (old_status == "ok" and
                            old_archived >= current_total) or (
                            old_status == "blocked_missing_poc" and
                            old.get("fetch_strategy") == FETCH_STRATEGY) or (
                            old_status == "skipped_operator") or (
                            old_status == "poc_failed" and
                            old.get("fetch_strategy") == FETCH_STRATEGY and
                            int(old.get("attempt") or 0) >= 3)
                except (OSError, TypeError, ValueError, json.JSONDecodeError):
                    return True
                return not done

            def add(project: str) -> None:
                if project in seen or not needs_download(project):
                    return
                pending.append(project)
                seen.add(project)

            for project in forced:
                add(project)
            for project in BENCHMARK20_DOWNLOAD:
                add(project)
            if not pending:
                print("benchmark20 download cohort idle; waiting", flush=True)
                time.sleep(interval)
                continue
            project = pending[0]
            print(f"=== download {project} ===", flush=True)
            if project in forced:
                forced = [item for item in forced if item != project]
            try:
                result = fetch_project(project)
            except Exception as exc:  # record and continue with the next project
                result = {"project": project, "status": "error",
                          "error": f"{type(exc).__name__}: {exc}"}
            write_status(project, result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
            if result.get("status") == "paused_low_disk":
                time.sleep(max(interval, 300))
            else:
                time.sleep(interval)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=30,
                        help="seconds between projects and queue checks")
    parser.add_argument("--retry-project", action="append", default=[],
                        help="run one immediate retry for this project before the normal queue")
    args = parser.parse_args()
    run(max(args.interval, 5), list(args.retry_project))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
