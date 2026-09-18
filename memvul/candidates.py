"""Fix-date waves → archaeological candidate bases.

OSS-Fuzz onboardings arrive as bursts of reports; maintainers fix them in
batches. The parent of the earliest fix in a batch is the eve of that wave:
those bugs were live together, zero patches required.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import gitutil
from .bug import Bug


@dataclass
class Wave:
    day: str
    n: int
    oss_ids: list[int]
    first_fix: str | None
    first_fix_date: int | None
    eve: str | None = None
    eve_date: int | None = None
    n_latent_upper: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def _day(ts: int) -> str:
    return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).date().isoformat()


def waves(bugs: list[Bug]) -> list[Wave]:
    by_day: dict[str, list[Bug]] = defaultdict(list)
    for b in bugs:
        if b.fix_date:
            by_day[_day(b.fix_date)].append(b)
    out: list[Wave] = []
    for day, group in by_day.items():
        group = sorted(group, key=lambda b: (b.fix_date or 0, b.oss_id))
        first = group[0]
        out.append(Wave(
            day=day,
            n=len(group),
            oss_ids=[b.oss_id for b in group],
            first_fix=first.fix_resolved,
            first_fix_date=first.fix_date,
        ))
    return sorted(out, key=lambda w: (-w.n, w.day))


def resolve_eves(repo: Path, waves_: list[Wave]) -> None:
    """Eve = parent of the earliest fix in the wave (tree just before it)."""
    for w in waves_:
        if not w.first_fix:
            continue
        par = gitutil.parent(repo, w.first_fix)
        if not par:
            continue
        w.eve = par
        w.eve_date = gitutil.commit_date(repo, par)


def score_eve(repo: Path, eve: str, bugs: list[Bug],
              horizon_days: int = 730) -> list[Bug]:
    """Bugs whose fix has not landed at ``eve`` and lands within ``horizon_days``.

    Unbounded "fix not landed" always prefers the oldest commit. OSS-Fuzz
    bursts last months, not decades, so a two-year horizon is the estimate
    that matches measured peaks (assimp: 25 at 2021-09 vs. 37 unbounded).
    """
    eve_date = gitutil.commit_date(repo, eve)
    horizon = horizon_days * 86400
    latent = []
    for b in bugs:
        if not b.fix_resolved or not b.fix_date:
            continue
        if b.fix_resolved == eve:
            continue
        if gitutil.is_ancestor(repo, b.fix_resolved, eve):
            continue
        delta = b.fix_date - eve_date
        if delta <= 0 or delta > horizon:
            continue
        latent.append(b)
    return latent


def plan(repo: Path, bugs: list[Bug], min_wave: int = 2,
         horizon_days: int = 730) -> dict:
    """Histogram + eve commits + upper-bound scores. No builds."""
    ws = waves(bugs)
    resolve_eves(repo, ws)
    dated = [b for b in bugs if b.fix_date]
    for w in ws:
        if w.eve:
            w.n_latent_upper = len(score_eve(repo, w.eve, bugs, horizon_days))
    scored = [w for w in ws if w.eve and w.n >= min_wave]
    if not scored:
        scored = [w for w in ws if w.eve]
    scored.sort(key=lambda w: (w.n_latent_upper, w.eve_date or 0), reverse=True)
    best = scored[0] if scored else None
    return {
        "n_bugs": len(bugs),
        "n_dated": len(dated),
        "n_waves": len(ws),
        "waves": [w.to_dict() for w in ws],
        "best": best.to_dict() if best else None,
    }
