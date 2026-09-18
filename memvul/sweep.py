"""Read and analyze manually recorded observability results.

This module deliberately contains no container, build, or replay driver.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import asan, gitutil
from .bug import Bug, Window

@dataclass
class Probe:
    sha: str
    date: int
    reason: str

    @property
    def short(self) -> str:
        return self.sha[:12]


@dataclass
class Shot:
    """One PoC at one probe."""

    verdict: str          # asan | signal | timeout | clean | build_fail
    kind: str | None = None
    signature: list[str] | None = None
    match: bool = False


@dataclass
class Sweep:
    project: str
    harness: str | None
    repo: str
    srcdir: str
    container: str | None
    bugs: list[dict]
    probes: list[dict] = field(default_factory=list)
    matrix: dict[str, dict[str, dict]] = field(default_factory=dict)
    windows: dict[str, dict] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _month_key(ts: int) -> str:
    return dt.date.fromtimestamp(ts).strftime("%Y-%m")


def propose_probes(repo: Path, bugs: list[Bug],
                   every_days: int = 32) -> list[Probe]:
    """Monthly-ish grid plus ARVO vuln commits and a left sentinel.

    ``every_days`` defaults to ~one month so a 3-year span is ~35 builds,
    ARVO vuln commits are free high-value
    points (each is known-live for at least one bug).
    """
    dated = [b.fix_date for b in bugs if b.fix_date]
    if not dated:
        return []
    since = min(dated) - 180 * 86400
    until = max(dated) + 14 * 86400
    history = gitutil.log_span(repo, since, until)
    if not history:
        return []

    picked: dict[str, Probe] = {}

    def add(sha: str, ts: int, reason: str) -> None:
        sha = gitutil.resolve(repo, sha) or sha
        if len(sha) < 12:
            return
        if sha not in picked:
            picked[sha] = Probe(sha, ts, reason)
        elif reason not in picked[sha].reason:
            picked[sha].reason += f"+{reason}"

    # Grid: last commit of each bucket.
    bucket: dict[int, tuple[str, int]] = {}
    for sha, ts in history:
        key = ts // (every_days * 86400)
        prev = bucket.get(key)
        if prev is None or ts > prev[1]:
            bucket[key] = (sha, ts)
    for sha, ts in bucket.values():
        add(sha, ts, "grid")

    # Left sentinel: newest commit before the grid.
    first = history[0]
    earlier = gitutil.git(
        repo, "log", "-1", "--first-parent", "--format=%H %ct",
        f"--until={first[1] - 1}", check=False).strip()
    if earlier:
        sha, ts = earlier.split()
        add(sha, int(ts), "sentinel")

    def near(ts: int, days: int = 14) -> bool:
        return any(abs(p.date - ts) <= days * 86400 for p in picked.values())

    for b in bugs:
        if not b.arvo_vuln:
            continue
        sha = gitutil.resolve(repo, b.arvo_vuln)
        if not sha:
            continue
        ts = gitutil.commit_date(repo, sha)
        if not near(ts):
            add(sha, ts, "arvo_vuln")

    # fix^ only when no probe already sits near the fix.
    # Six fixes on the same afternoon must not become six rebuilds.
    for b in bugs:
        if not b.fix_resolved or not b.fix_date:
            continue
        par = gitutil.parent(repo, b.fix_resolved)
        if not par or near(b.fix_date):
            continue
        add(par, gitutil.commit_date(repo, par), "fix^")

    return sorted(picked.values(), key=lambda p: p.date)


def propose_refine(repo: Path, bugs: list[Bug],
                   probes: list[Probe],
                   matrix: dict[str, dict[str, Shot]]) -> list[Probe]:
    """Midpoints of unclear window boundaries."""
    extra: list[Probe] = []
    by_sha = {p.sha: p for p in probes}
    ordered = sorted(probes, key=lambda p: p.date)
    seen: set[str] = set()

    def live(b: Bug, sha: str) -> bool | None:
        shot = matrix.get(sha, {}).get(str(b.oss_id))
        if shot is None:
            return None
        return shot.match

    for b in bugs:
        if not b.fix_resolved:
            continue
        flags = [(p, live(b, p.sha)) for p in ordered]
        for i, (p, flag) in enumerate(flags):
            if flag is None:
                continue
            # live after unknown/dead → bisect left
            left = None
            for j in range(i - 1, -1, -1):
                if flags[j][1] is not None:
                    left = flags[j]
                    break
            if left and left[1] is False and flag is True:
                mid = gitutil.midpoint(repo, left[0].sha, p.sha)
                if mid and mid not in by_sha and mid not in seen:
                    seen.add(mid)
                    extra.append(Probe(mid, gitutil.commit_date(repo, mid),
                                       f"refine:{b.oss_id}"))
            # last live then dead → bisect right (unless the dead is the fix)
            if i + 1 < len(flags) and flag is True and flags[i + 1][1] is False:
                mid = gitutil.midpoint(repo, p.sha, flags[i + 1][0].sha)
                if mid and mid not in by_sha and mid not in seen:
                    seen.add(mid)
                    extra.append(Probe(mid, gitutil.commit_date(repo, mid),
                                       f"refine:{b.oss_id}"))
    extra.sort(key=lambda p: p.date)
    return extra


def signatures_match(ref: tuple[str, ...] | None,
                     got: tuple[str, ...] | None) -> bool:
    """Methodology: kind + crash function + crash file; line numbers ignored."""
    if not ref or not got:
        return False
    rk, ra, rf, rfile = (list(ref) + ["-"] * 4)[:4]
    gk, ga, gf, gfile = (list(got) + ["-"] * 4)[:4]
    if rk.lower() != gk.lower():
        return False
    if rfile != "-" and gfile != "-" and rfile.split("/")[-1] != gfile.split("/")[-1]:
        return False
    if rf != "-" and gf != "-" and _norm(rf) != _norm(gf):
        return False
    if ra not in ("-", None) and ga not in ("-", None) and ra != ga:
        return False
    return True


def _norm(func: str) -> str:
    return asan._norm_func(func)


def annotate_matches(bugs: list[Bug], shots: dict[str, Shot]) -> None:
    by_id = {str(b.oss_id): b for b in bugs}
    for oid, shot in shots.items():
        b = by_id.get(oid)
        if b is None:
            continue
        got = tuple(shot.signature) if shot.signature else None
        shot.match = shot.verdict == "asan" and signatures_match(b.signature, got)


def _as_shot(raw) -> Shot | None:
    if raw is None:
        return None
    if isinstance(raw, Shot):
        return raw
    return Shot(
        verdict=raw.get("verdict", "clean"),
        kind=raw.get("kind"),
        signature=raw.get("signature"),
        match=bool(raw.get("match")),
    )


def reconstruct(bugs: list[Bug], probes: list[Probe],
                matrix: dict[str, dict[str, Shot]]) -> None:
    """Fill ``bug.window`` from the survival matrix.

    Window = the maximal contiguous live run that ends at the last live
    probe before ``fix``. Gaps before that run are recorded, not glued.
    """
    ordered = sorted(probes, key=lambda p: p.date)
    for b in bugs:
        if not b.fix_resolved or not b.fix_date:
            b.reject = b.reject or "commit_missing"
            continue
        shots: list[tuple[Probe, Shot | None]] = []
        for p in ordered:
            if p.date >= b.fix_date:
                break
            shots.append((p, _as_shot(matrix.get(p.sha, {}).get(str(b.oss_id)))))
        live_runs: list[list[Probe]] = []
        cur: list[Probe] = []
        for p, s in shots:
            if s is not None and s.match:
                cur.append(p)
            elif s is not None:
                if cur:
                    live_runs.append(cur)
                    cur = []
            # unknown (build_fail / not yet run) does not break a run
        if cur:
            live_runs.append(cur)
        used = sum(1 for _, s in shots if s is not None)
        if not live_runs:
            if used:
                b.reject = b.reject or "window_unmeasured"
            b.window = None
            continue
        # The run that sits against the fix (last one) is the window.
        run = live_runs[-1]
        gaps = []
        if len(live_runs) > 1:
            for earlier in live_runs[:-1]:
                gaps.append({
                    "from": earlier[0].sha,
                    "to": earlier[-1].sha,
                    "n": len(earlier),
                })
        b.window = Window(
            intro=run[0].sha,
            intro_date=run[0].date,
            fix=b.fix_resolved,
            fix_date=b.fix_date,
            contiguous=not gaps,
            gaps=gaps,
            live_probes=[p.sha for p in run],
            probes_used=used,
        )
        if b.reject == "window_unmeasured":
            b.reject = None


def load(path: Path) -> Sweep | None:
    if not path.exists():
        return None
    raw = json.loads(path.read_text())
    sw = Sweep(**{k: raw[k] for k in Sweep.__dataclass_fields__ if k in raw})
    return sw


def save(sw: Sweep, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sw.to_dict(), indent=1))


def attach_windows(bugs: list[Bug], sw: Sweep) -> None:
    """Rehydrate Window objects onto Bug records from a saved sweep."""
    by_id = {str(b.oss_id): b for b in bugs}
    for oid, w in sw.windows.items():
        b = by_id.get(oid)
        if not b:
            continue
        if not w:
            b.reject = b.reject or "window_unmeasured"
            continue
        b.window = Window(**{k: w[k] for k in Window.__dataclass_fields__ if k in w})
        if b.window.intro is None:
            b.reject = b.reject or "window_unmeasured"
