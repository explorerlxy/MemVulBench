"""Interval piercing: pick the base that stabs the most measured windows.

This is the cheap half of densification. Bugs whose windows contain B are
latent (zero pins). Everything else has to be pinned and is scored later.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .bug import Bug


@dataclass
class BaseScore:
    sha: str
    date: int
    latent: list[int]
    mosaic: list[int]
    unknown: list[int]

    @property
    def n_latent(self) -> int:
        return len(self.latent)

    def to_dict(self) -> dict:
        return asdict(self)


def rank(bugs: list[Bug], candidates: list[tuple[str, int]],
         n: int = 12) -> list[BaseScore]:
    """Score each candidate commit by how many windows contain it."""
    scored: list[BaseScore] = []
    seen: set[str] = set()
    for sha, ts in candidates:
        if sha in seen:
            continue
        seen.add(sha)
        lat, mos, unk = [], [], []
        for b in bugs:
            if b.reject or not b.window:
                unk.append(b.oss_id)
            elif b.window.contains(ts):
                lat.append(b.oss_id)
            else:
                mos.append(b.oss_id)
        scored.append(BaseScore(sha, ts, lat, mos, unk))
    scored.sort(key=lambda s: (s.n_latent, -len(s.mosaic)), reverse=True)
    return scored[:n]


def candidates_from_windows(bugs: list[Bug]) -> list[tuple[str, int]]:
    """Natural stab points: each intro and each live probe, plus each fix^."""
    out: dict[str, int] = {}
    for b in bugs:
        w = b.window
        if not w:
            continue
        if w.intro and w.intro_date:
            out[w.intro] = w.intro_date
        for sha in w.live_probes:
            if sha not in out:
                # date filled by caller if known; placeholder = intro
                out[sha] = w.intro_date or w.fix_date
        if w.fix_date:
            out[w.fix] = w.fix_date
    return sorted(out.items(), key=lambda p: p[1])
