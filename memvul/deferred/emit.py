"""Materialise a slice: checkout the base, apply file pins, write the manifest.

The fidelity invariant is checkable on the resulting tree: every source
file's sha256 equals ``git show <recorded-commit>:<path>``.
"""

from __future__ import annotations

import json
from pathlib import Path

from .. import gitutil
from .slice import Slice


def apply(repo: Path, base: str, pins: list[dict],
          enabled: set[int] | None = None) -> list[dict]:
    """Reset to ``base`` then check out each pin's ON or OFF blob.

    ``enabled`` is the set of bug ids that should be ON. A pin whose
    toggle unit intersects ``enabled`` is applied ON (the unit is
    atomic). ``enabled is None`` means everything ON.
    """
    gitutil.checkout_detach(repo, base)
    applied = []
    for p in pins:
        unit = set(p["bugs"])
        on = enabled is None or bool(unit & enabled)
        commit = p["on_commit"] if on else p["off_commit"]
        if on and commit == base:
            applied.append({**p, "applied": "base", "commit": commit})
            continue
        gitutil.checkout_file(repo, commit, p["file"])
        applied.append({**p, "applied": "on" if on else "off", "commit": commit})
    return applied


def fidelity(repo: Path, base: str, pins: list[dict],
             enabled: set[int] | None = None) -> list[dict]:
    """Compare every pinned file (and only those) to the recorded blob."""
    failures = []
    for p in pins:
        unit = set(p["bugs"])
        on = enabled is None or bool(unit & enabled)
        commit = p["on_commit"] if on else p["off_commit"]
        expect = p["on_blob"] if on else p["off_blob"]
        if p.get("fidelity") == "function":
            continue
        path = repo / p["file"]
        if not path.exists():
            failures.append({"file": p["file"], "reason": "missing"})
            continue
        actual = gitutil.file_sha256(path)
        if expect and actual != expect:
            # Recompute from git in case the plan was serialised without blobs.
            expect = expect or gitutil.blob_sha256(repo, commit, p["file"])
        if expect and actual != expect:
            failures.append({
                "file": p["file"],
                "expected": expect,
                "actual": actual,
                "commit": commit,
            })
    return failures


def mosaic_stats(repo: Path, base: str, pins: list[dict]) -> dict:
    src = gitutil.src_files_at(repo, base)
    pinned = {p["file"] for p in pins if p["on_commit"] != base}
    return {
        "source_files": len(src),
        "files_pinned": len(pinned),
        "mosaic_ratio": round(len(pinned) / len(src), 4) if src else 0.0,
    }


def write_manifest(sl: Slice, dest: Path, extra: dict | None = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = sl.to_dict()
    if extra:
        payload.update(extra)
    dest.write_text(json.dumps(payload, indent=1))


def write_toggles(sl: Slice, dest: Path) -> None:
    """CMake-friendly cache entries. Source itself stays #ifdef-free."""
    units: dict[str, list[int]] = {}
    for p in sl.pins:
        key = "MEMVUL_BUG_" + "_".join(str(i) for i in p["bugs"])
        units.setdefault(key, p["bugs"])
    lines = [
        "# Generated. Each cache entry selects the ON or OFF blob of a pin unit.",
        "# The source tree has no #ifdefs; python3 -m memvul.deferred emit flips files.",
        "",
    ]
    for key, ids in units.items():
        lines.append(f'option({key} "bugs {ids}" ON)')
    dest.write_text("\n".join(lines) + "\n")
