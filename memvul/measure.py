"""PoC and ARVO builder preparation helpers.

This module is intentionally limited to fetching and archiving inputs.  It
has no compile, replay, sweep, or automatic catalog-admission entry point;
those operations are performed manually and recorded by the operator.
"""

from __future__ import annotations

import os

import json
import re
import shutil
import subprocess
import time
from collections import Counter
from pathlib import Path

from . import fetch

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "catalog"
MEASURE = ROOT / "data" / "measure"
POCS = Path("/tmp/memvul/pocs")
POC_STORE = Path(os.environ.get("MEMVUL_POC_STORE",
                                  "/media/hahafish/Data/ForUbuntu/arvo-pocs"))
CONTAINER_POCS = "/measure-pocs"
MAX_BUILDER_TRIES = 3
MIN_MANUAL_POCS = 8
DIRECT_PASS_POC_LIMIT = 6
_SLUG_RE = re.compile(r"[^A-Za-z0-9._+-]+")


def load_target(project: str) -> dict:
    """Read the small, dependency-free subset of a catalog target."""
    text = (CATALOG / project / "target.yaml").read_text()
    rec: dict = {"project": project, "bugs": [], "waves": [], "rejected": []}
    section = None
    current: dict | None = None
    for raw in text.splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        line = raw.strip()
        if indent == 0 and line.endswith(":") and not line.startswith("-"):
            key = line[:-1]
            if key in ("base", "waves", "bugs", "rejected"):
                section = key
                current = None
                if key == "base":
                    rec["base"] = {}
                continue
            section = None
            k, _, v = line.partition(":")
            rec[k.strip()] = _scalar(v.strip())
            continue
        if indent == 0 and ":" in line:
            k, _, v = line.partition(":")
            rec[k.strip()] = _scalar(v.strip())
            section = None
            continue
        if section == "base" and indent == 2:
            k, _, v = line.partition(":")
            rec.setdefault("base", {})[k.strip()] = _scalar(v.strip())
        elif section in ("waves", "bugs", "rejected") and line.startswith("- "):
            current = {}
            rec[section].append(current)
            rest = line[2:]
            if ":" in rest:
                k, _, v = rest.partition(":")
                current[k.strip()] = _scalar(v.strip())
        elif section in ("waves", "bugs", "rejected") and current is not None and indent >= 2:
            k, _, v = line.partition(":")
            current[k.strip()] = _scalar(v.strip())
    return rec


def _scalar(value: str):
    value = value.strip()
    if value in ("", "null", "~"):
        return None
    if value in ("true", "false"):
        return value == "true"
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [] if not inner else [_scalar(x.strip()) for x in inner.split(",")]
    if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")):
        return value.strip("\"'")
    try:
        return int(value)
    except ValueError:
        return value


def dominant_harness(rec: dict) -> str:
    counts = Counter(b.get("harness") for b in rec.get("bugs") or []
                     if b.get("harness"))
    if counts:
        return counts.most_common(1)[0][0]
    return (rec.get("harnesses") or ["fuzzer"])[0]


def project_poc_count(rec: dict) -> int:
    """Count all catalog PoCs for a project, across every harness."""
    return sum(1 for bug in rec.get("bugs") or []
               if bug.get("oss_id") is not None)


def require_manual_admission(rec: dict, min_pocs: int = MIN_MANUAL_POCS) -> int:
    """Enforce the foreground compile/replay PoC admission gate."""
    n_poc = project_poc_count(rec)
    if n_poc < min_pocs:
        if n_poc < DIRECT_PASS_POC_LIMIT:
            action = "direct pass"
        else:
            action = "defer"
        raise RuntimeError(
            f"{rec.get('project')}: {action}; project has {n_poc} PoCs in total, "
            f"but manual admission requires at least {min_pocs}")
    return n_poc


def candidates_for(rec: dict, n: int = 5) -> list[str]:
    seen: list[str] = []
    base = (rec.get("base") or {}).get("commit")
    if base:
        seen.append(str(base))
    for wave in rec.get("waves") or []:
        eve = wave.get("eve")
        if eve and eve not in seen:
            seen.append(str(eve))
        if len(seen) >= n:
            break
    return seen


def fetch_pocs(oss_ids: list[int], dest: Path = POCS,
               on_success=None,
               harness_by_id: dict[int, str] | None = None) -> tuple[int, list[int]]:
    ok, failed = 0, []
    dest.mkdir(parents=True, exist_ok=True)
    names = harness_by_id or {}
    for i, oss_id in enumerate(oss_ids, 1):
        out_dir = dest / str(oss_id)
        if (out_dir / "poc").exists():
            print(f"  poc [{i}/{len(oss_ids)}] {oss_id} cached", flush=True)
            ok += 1
            continue
        try:
            result = fetch.extract(oss_id, out_dir,
                                   harness=names.get(oss_id))
            (out_dir / "meta.json").write_text(json.dumps(result, indent=1))
            print(f"  poc [{i}/{len(oss_ids)}] {oss_id} ok", flush=True)
            ok += 1
            if on_success is not None:
                on_success(oss_id)
        except Exception as exc:  # noqa: BLE001
            print(f"  poc [{i}/{len(oss_ids)}] {oss_id} FAIL "
                  f"{type(exc).__name__}: {exc}", flush=True)
            failed.append(oss_id)
    return ok, failed


def restore_pocs(project: str, bugs: list[dict], dest: Path = POCS) -> tuple[int, list[int]]:
    """Restore archived PoCs into the temporary working layout."""
    index_path = POC_STORE / project / "index.json"
    if not index_path.exists():
        return 0, [int(b["oss_id"]) for b in bugs]
    try:
        index = json.loads(index_path.read_text())
    except json.JSONDecodeError:
        return 0, [int(b["oss_id"]) for b in bugs]

    ok, missing = 0, []
    for bug in bugs:
        oid = int(bug["oss_id"])
        entry = index.get(str(oid)) or {}
        src = POC_STORE / project / str(entry.get("file") or "")
        if not src.is_file():
            missing.append(oid)
            continue
        out = dest / str(oid) / "poc"
        out.parent.mkdir(parents=True, exist_ok=True)
        if not out.exists() or out.stat().st_size != src.stat().st_size:
            shutil.copy2(src, out)
        ok += 1
    return ok, missing


def _slug(value: str) -> str:
    out = _SLUG_RE.sub("-", str(value or "unknown")).strip("-")
    return out or "unknown"


def poc_archive_name(bug: dict) -> str:
    return (f"{_slug(bug.get('label') or 'unknown')}-"
            f"{_slug(bug.get('fix_date') or 'undated')}-"
            f"{str(bug.get('fix_commit') or 'unknown')[:12]}")


def persist_pocs(project: str, bugs: list[dict], src_root: Path = POCS) -> int:
    """Copy working PoCs to the persistent project archive."""
    dest_dir = POC_STORE / project
    dest_dir.mkdir(parents=True, exist_ok=True)
    index_path = dest_dir / "index.json"
    try:
        index = json.loads(index_path.read_text()) if index_path.exists() else {}
    except json.JSONDecodeError:
        index = {}
    used = {entry.get("file") for entry in index.values() if entry.get("file")}
    copied = 0
    for bug in bugs:
        oid = int(bug["oss_id"])
        src = src_root / str(oid) / "poc"
        if not src.is_file():
            continue
        base = poc_archive_name(bug)
        name = index.get(str(oid), {}).get("file") or base
        owner = next((key for key, entry in index.items()
                      if key != str(oid) and entry.get("file") == name), None)
        if owner is not None:
            name = f"{base}-{oid}"
            suffix = 2
            while name in used:
                name = f"{base}-{oid}-{suffix}"
                suffix += 1
        dest = dest_dir / name
        if not dest.exists() or dest.stat().st_size != src.stat().st_size:
            shutil.copy2(src, dest)
            copied += 1
        used.add(name)
        entry = {
            "file": name,
            "oss_id": oid,
            "label": bug.get("label"),
            "fix_date": bug.get("fix_date"),
            "fix_commit": bug.get("fix_commit"),
            "harness": bug.get("harness"),
            "size": dest.stat().st_size,
        }
        href = src_root / str(oid) / "harness"
        if href.is_file():
            hdir = dest_dir / "harnesses"
            hdir.mkdir(exist_ok=True)
            raw_name = bug.get("harness") or "harness"
            try:
                meta = json.loads((src_root / str(oid) / "meta.json").read_text())
                raw_name = (meta.get("binary") or {}).get("name") or raw_name
            except (OSError, json.JSONDecodeError):
                pass
            hname = fetch.clean_harness_name(raw_name) or _slug(raw_name)
            hdest = hdir / hname
            if not hdest.exists():
                shutil.copy2(href, hdest)
            entry["ref_binary"] = f"harnesses/{hname}"
            entry["ref_binary_size"] = hdest.stat().st_size
        index[str(oid)] = entry
    index_path.write_text(json.dumps(index, indent=1) + "\n")
    return copied


def persist_cached() -> dict[str, int]:
    """Archive catalog PoCs currently present in the shared temp cache."""
    by_id: dict[int, tuple[str, dict]] = {}
    for project_dir in sorted(CATALOG.iterdir()):
        if not (project_dir / "target.yaml").exists():
            continue
        rec = load_target(project_dir.name)
        for bug in rec.get("bugs") or []:
            if bug.get("oss_id") is not None:
                by_id[int(bug["oss_id"])] = (project_dir.name, bug)
    grouped: dict[str, list[dict]] = {}
    for entry in POCS.iterdir() if POCS.exists() else []:
        if not (entry / "poc").is_file() or not entry.name.isdigit():
            continue
        hit = by_id.get(int(entry.name))
        if hit:
            grouped.setdefault(hit[0], []).append(hit[1])
    return {project: persist_pocs(project, bugs)
            for project, bugs in grouped.items()}


def cleanup_project_pocs(project: str, bugs: list[dict], src_root: Path = POCS) -> int:
    """Remove only temporary PoCs whose archived byte size is confirmed."""
    index_path = POC_STORE / project / "index.json"
    if not index_path.exists():
        return 0
    try:
        index = json.loads(index_path.read_text())
    except json.JSONDecodeError:
        return 0
    removed = 0
    for bug in bugs:
        oid = int(bug["oss_id"])
        src_dir = src_root / str(oid)
        src = src_dir / "poc"
        entry = index.get(str(oid)) or {}
        archived = POC_STORE / project / str(entry.get("file") or "")
        if src.is_file() and archived.is_file() and src.stat().st_size == archived.stat().st_size:
            shutil.rmtree(src_dir)
            removed += 1
    return removed


def pick_builders(rec: dict, fetched: list[int]) -> list[int]:
    """Prefer an archived builder from the catalog base wave."""
    base = str((rec.get("base") or {}).get("commit") or "")
    eve_ids: list[int] = []
    wave_ids: list[int] = []
    for wave in rec.get("waves") or []:
        ids = [int(oid) for oid in wave.get("oss_ids") or []]
        eve = str(wave.get("eve") or "")
        same = bool(base) and (eve == base or eve.startswith(base[:12]) or
                               base.startswith(eve[:12]))
        for oid in ids:
            if same and oid not in eve_ids:
                eve_ids.append(oid)
            if oid not in wave_ids:
                wave_ids.append(oid)
    ordered: list[int] = []
    for oid in eve_ids + wave_ids + fetched:
        if oid in fetched and oid not in ordered:
            ordered.append(oid)

    def rank(oid: int) -> tuple[int, int]:
        stored = 0 if fetch.store_tar(f"{oid}-vul").exists() else 1
        era = 0 if oid in eve_ids else 1
        return era, stored

    return sorted(ordered, key=rank)


def docker(*args: str, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def _pull(tag: str, attempts: int = 3) -> None:
    repo, _, name = tag.partition(":")
    if not name:
        repo, name = "n132/arvo", tag
    last = ""
    for attempt in range(attempts):
        print(f"  registry-load {tag} (try {attempt + 1}/{attempts}) ...",
              flush=True)
        try:
            info = fetch.load_into_docker(repo, name)
            print(f"    loaded cached={info.get('cached')} source={info.get('source')}",
                  flush=True)
            return
        except Exception as exc:  # noqa: BLE001
            last = str(exc)[-400:]
            print(f"    FAIL {type(exc).__name__}: {last}", flush=True)
            time.sleep(2 ** attempt)
    raise RuntimeError(f"registry-load failed: {last}")


def ensure_container(project: str, oss_id: int) -> str:
    name = f"memvul-{project}"
    if project == "assimp":
        raise RuntimeError("refusing to replace the existing assimp builder")
    insp = docker("inspect", "-f", "{{.State.Running}}", name, timeout=30)
    if insp.returncode == 0 and "true" in insp.stdout:
        return name
    if insp.returncode == 0:
        docker("rm", "-f", name, timeout=60)
    tag = f"n132/arvo:{oss_id}-vul"
    _pull(tag)
    run = docker("run", "-d", "--name", name,
                 "--security-opt", "seccomp=unconfined",
                 "--cap-add", "SYS_PTRACE", tag, "sleep", "infinity",
                 timeout=120)
    if run.returncode != 0:
        raise RuntimeError(f"docker run failed: {run.stderr[-400:]}")
    return name


def detect_srcdir(container: str, project: str) -> str:
    ls = docker("exec", container, "bash", "-lc", "ls -1 /src")
    names = ls.stdout.split()
    if project in names:
        return f"/src/{project}"
    skip = {"aflplusplus", "honggfuzz", "libfuzzer", "build.sh", "compiler_rt"}
    dirs = [name for name in names if name not in skip and not name.endswith(".diff")]
    if len(dirs) == 1:
        return f"/src/{dirs[0]}"
    for name in dirs:
        if name.lower() == project.lower():
            return f"/src/{name}"
    raise RuntimeError(f"cannot find srcdir in /src: {names}")


def drop_builder(project: str, oss_id: int | None = None) -> None:
    if project == "assimp":
        return
    docker("rm", "-f", f"memvul-{project}", timeout=60)
    if oss_id:
        docker("rmi", "-f", f"n132/arvo:{oss_id}-vul", timeout=180)


def _sync_project_pocs(container: str, oss_ids: list[int]) -> int:
    docker("exec", container, "bash", "-lc",
           f"rm -rf {CONTAINER_POCS} && mkdir -p {CONTAINER_POCS}")
    copied = 0
    for oid in oss_ids:
        src = POCS / str(oid)
        if not (src / "poc").exists():
            continue
        docker("cp", str(src), f"{container}:{CONTAINER_POCS}/{oid}", timeout=60)
        copied += 1
    return copied


def _open_builder(project: str, rec: dict, fetched: list[int]) -> tuple[str, int, str]:
    last: Exception | None = None
    for oss_id in pick_builders(rec, fetched)[:MAX_BUILDER_TRIES]:
        try:
            container = ensure_container(project, oss_id)
            srcdir = detect_srcdir(container, project)
            return container, oss_id, srcdir
        except Exception as exc:  # noqa: BLE001
            last = exc
            drop_builder(project, oss_id)
    raise RuntimeError(f"no usable ARVO builder: {last}")


def prepare_project(project: str) -> dict:
    """Fetch inputs and leave one builder ready for manual operator work."""
    rec = load_target(project)
    harness = dominant_harness(rec)
    require_manual_admission(rec)
    listed = [int(b["oss_id"]) for b in rec.get("bugs") or []
              if b.get("harness") == harness]
    if not listed:
        listed = [int(b["oss_id"]) for b in rec.get("bugs") or []]
    n_poc, failed = fetch_pocs(
        listed,
        harness_by_id={int(b["oss_id"]): b.get("harness") or ""
                       for b in rec.get("bugs") or []})
    if n_poc == 0:
        raise RuntimeError("no PoCs fetched")
    fetched = [oid for oid in listed if (POCS / str(oid) / "poc").exists()]
    persist_pocs(project, rec.get("bugs") or [])
    container, builder_id, srcdir = _open_builder(project, rec, fetched)
    synced = _sync_project_pocs(container, fetched)
    out = {
        "project": project,
        "harness": harness,
        "builder": f"n132/arvo:{builder_id}-vul",
        "builder_id": builder_id,
        "container": container,
        "srcdir": srcdir,
        "n_poc": n_poc,
        "failed_poc": failed,
        "base": (rec.get("base") or {}).get("commit"),
        "candidates": candidates_for(rec),
        "synced": synced,
        "stage": "prepared_for_manual_work",
    }
    MEASURE.mkdir(parents=True, exist_ok=True)
    (MEASURE / f"{project}.prepare.json").write_text(
        json.dumps(out, indent=1) + "\n")
    return out


def temporal_counts(rec: dict) -> tuple[int, int]:
    """Return (latent temporal bugs, all temporal bugs) for a catalog target."""
    latent = 0
    total = 0
    for bug in rec.get("bugs") or []:
        if bug.get("group") != "temporal":
            continue
        total += 1
        if bug.get("status") == "latent":
            latent += 1
    return latent, total


def queue(min_sites: int = 10, min_latent: int = 8,
          min_pocs: int = MIN_MANUAL_POCS) -> list[str]:
    """Return wave_eve projects worth preparing, temporal-heavy first.

    Download and later foreground work are short on use-after-free /
    double-free samples. Rank by latent temporal count, then all temporal
    bugs, then the wave_eve latent upper bound.
    """
    idx = json.loads((CATALOG / "index.json").read_text())
    ready = []
    for entry in idx:
        if entry.get("method") in ("measured_sweep", "unresolved"):
            continue
        if (entry.get("n_sites") or 0) <= min_sites:
            continue
        if (entry.get("n_latent") or 0) < min_latent:
            continue
        rec = load_target(entry["project"])
        n_poc = project_poc_count(rec)
        if n_poc < min_pocs:
            continue
        latent_temporal, temporal = temporal_counts(rec)
        ready.append((-latent_temporal, -temporal,
                      -(entry.get("n_latent") or 0),
                      -(entry.get("n_sites") or 0), entry["project"]))
    ready.sort()
    return [project for *_, project in ready]
