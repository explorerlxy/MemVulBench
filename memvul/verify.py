"""Admission gates 1–6 (methodology.md §8). Determinism is deferred."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import asan, emit, gitutil, sweep
from .bug import Bug
from .pin import expand_e1, expand_e2, expand_e3
from .slice import Slice


@dataclass
class GateResult:
    oss_id: int
    status: str                  # admitted | rejected | pending
    reject_reason: str | None = None
    gates: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _sig_of(bug: Bug) -> tuple[str, ...] | None:
    return bug.signature


def _replay_one(container: str, binary: str, poc_dir: str,
                oss_id: int, timeout: int = 20) -> dict:
    dest = f"/tmp/verify_{oss_id}.log"
    cmd = (
        f"timeout -s KILL {timeout} {binary} {poc_dir}/{oss_id}/poc "
        f"> {dest} 2>&1; echo EXIT:$?"
    )
    p = sweep.docker("exec", container, "bash", "-lc", cmd, timeout=timeout + 30)
    log = sweep.docker("exec", container, "cat", dest)
    text = log.stdout
    rep = asan.parse(text)
    fired = bool(rep.kind) or "ERROR: AddressSanitizer" in text
    return {
        "fired": fired,
        "kind": rep.kind,
        "signature": list(rep.signature()) if rep.kind else None,
        "rc": p.stdout.strip().split("EXIT:")[-1] if "EXIT:" in p.stdout else None,
    }


def verify_slice(repo: Path, sl: Slice, bugs: list[Bug],
                 container: str | None = None,
                 srcdir: str = "/src/assimp",
                 harness: str = "assimp_fuzzer",
                 expand: bool = True) -> list[GateResult]:
    by_id = {b.oss_id: b for b in bugs}
    members = [by_id[i] for i in sl.bugs if i in by_id]
    results = [GateResult(oss_id=b.oss_id, status="pending") for b in members]
    by_res = {r.oss_id: r for r in results}

    # Gate 2 can run on the host tree after emit.apply.
    emit.apply(repo, sl.base, sl.pins)
    fails = emit.fidelity(repo, sl.base, sl.pins)
    for r in results:
        r.gates["fidelity"] = not fails
    if fails:
        for r in results:
            r.status = "rejected"
            r.reject_reason = "build_fail"
            r.notes.append(f"fidelity {fails[:3]}")
        return results

    if container is None:
        return results

    # Gate 1 + 3: full-ON build and replay.
    _apply_in_container(container, srcdir, sl.base, sl.pins, enabled=None)
    binary = _compile(container, srcdir, harness, "/out/verify")
    if binary is None:
        if expand:
            _try_expand(repo, sl)
        for r in results:
            r.status = "rejected"
            r.reject_reason = "build_fail"
            r.gates["build"] = False
        return results
    for r in results:
        r.gates["build"] = True

    shots = {}
    for b in members:
        shots[b.oss_id] = _replay_one(container, binary, "/pocs", b.oss_id)
        match = sweep.signatures_match(b.signature, tuple(shots[b.oss_id]["signature"] or ()))
        r.gates["repro"] = bool(shots[b.oss_id]["fired"] and match)
        if not shots[b.oss_id]["fired"]:
            r.status = "rejected"
            r.reject_reason = "no_repro"
        elif not match:
            r.status = "rejected"
            r.reject_reason = "signature_mismatch"

    # Gate 6: unique signatures among those that fired.
    seen: dict[tuple, int] = {}
    for b in members:
        r = by_res[b.oss_id]
        if r.reject_reason:
            continue
        sig = tuple(shots[b.oss_id]["signature"] or ())
        if sig in seen:
            r.status = "rejected"
            r.reject_reason = "signature_clash"
            r.gates["distinct"] = False
        else:
            seen[sig] = b.oss_id
            r.gates["distinct"] = True

    # Gates 4 and 5: OFF and isolated. Skip rejected.
    alive = [b for b in members if not by_res[b.oss_id].reject_reason]
    for b in alive:
        r = by_res[b.oss_id]
        # OFF: this bug's unit off, everyone else on.
        off_set = {x.oss_id for x in alive} - {b.oss_id}
        _apply_in_container(container, srcdir, sl.base, sl.pins, enabled=off_set)
        binary = _compile(container, srcdir, harness, "/out/verify_off")
        if binary is None:
            r.notes.append("off-state build failed")
            r.gates["off_silent"] = None
        else:
            shot = _replay_one(container, binary, "/pocs", b.oss_id)
            r.gates["off_silent"] = not shot["fired"]
            if shot["fired"]:
                r.status = "rejected"
                r.reject_reason = "control_positive"
                continue
        # Isolated: only this bug on.
        _apply_in_container(container, srcdir, sl.base, sl.pins,
                            enabled={b.oss_id})
        binary = _compile(container, srcdir, harness, "/out/verify_iso")
        if binary is None:
            r.notes.append("isolated build failed")
            r.gates["isolated"] = None
        else:
            shot = _replay_one(container, binary, "/pocs", b.oss_id)
            match = sweep.signatures_match(
                b.signature, tuple(shot["signature"] or ()))
            r.gates["isolated"] = bool(shot["fired"] and match)

    for r in results:
        if r.status == "pending" and not r.reject_reason:
            r.status = "admitted"
    return results


def _apply_in_container(container: str, srcdir: str, base: str,
                        pins: list[dict], enabled: set[int] | None) -> None:
    cmds = [
        f"cd {srcdir}",
        "git revert --quit 2>/dev/null || true",
        f"git checkout -q --force --detach {base}",
        f"git reset --hard --quiet {base}",
        "git clean -qfd",
    ]
    for p in pins:
        unit = set(p["bugs"])
        on = enabled is None or bool(unit & enabled)
        commit = p["on_commit"] if on else p["off_commit"]
        if on and commit == base:
            continue
        cmds.append(f"git checkout -q {commit} -- {p['file']}")
    sweep.docker("exec", container, "bash", "-lc", " && ".join(cmds))


def _compile(container: str, srcdir: str, harness: str,
             out: str) -> str | None:
    script = f"""
set -e
cd {srcdir}
rm -f CMakeCache.txt
export OUT={out} FUZZING_ENGINE=libfuzzer SANITIZER=address \\
       FUZZING_LANGUAGE=c++ ARCHITECTURE=x86_64
rm -rf {out} && mkdir -p {out}
if [ -x /out/llvm-symbolizer ]; then cp /out/llvm-symbolizer {out}/; fi
compile > /tmp/verify_compile.log 2>&1
test -x {out}/{harness}
"""
    p = sweep.docker("exec", container, "bash", "-lc", script, timeout=900)
    if p.returncode != 0:
        return None
    return f"{out}/{harness}"


def _try_expand(repo: Path, sl: Slice) -> None:
    """Record E1 extras on the slice pins; caller re-runs verify if wanted."""
    base = sl.base
    extras: list[dict] = []
    for p in sl.pins:
        more = expand_e1(repo, [p["file"]], p["on_commit"], base)
        for f in more:
            extras.append({
                "file": f,
                "on_commit": p["on_commit"],
                "off_commit": p["off_commit"],
                "on_blob": gitutil.blob_sha256(repo, p["on_commit"], f),
                "off_blob": gitutil.blob_sha256(repo, p["off_commit"], f),
                "bugs": p["bugs"],
                "fidelity": "file",
                "direction": p.get("direction", "backward"),
                "reason": "expand_compile",
            })
    sl.pins.extend(extras)
    _ = (expand_e2, expand_e3)  # used by the CLI expansion path
