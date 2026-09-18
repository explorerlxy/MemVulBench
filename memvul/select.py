"""Rank candidate benchmark slices.

A *slice* is the unit a fuzzing campaign runs against: one project, one
harness, one base commit, and every bug we managed to re-introduce and
verify on top of it. Before spending build effort we rank the possible
(project, harness) groups by how much a slice built from them could be
worth.

The number that matters is **distinct crash sites**, not issue count. ARVO
contains long runs of issues that are the same defect refound with a
different input; they collapse onto one site key and must only be counted
once, or the density estimate is fiction.
"""

from __future__ import annotations

import os
import re
from collections import Counter
from dataclasses import dataclass, field

from .arvo import Candidate

_BUILD_NOISE = re.compile(
    r"^/(?:src|work|build|usr)(?:/[^/]+)*/"
    r"(?=(?:code|src|include|contrib|fuzz|test)/)"
)


@dataclass
class Group:
    project: str
    harness: str | None
    language: str | None
    repo: str | None
    members: list[Candidate] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.project}::{self.harness}"

    @property
    def buildable(self) -> list[Candidate]:
        return [c for c in self.members if c.buildable]

    @property
    def sites(self) -> set[str]:
        return {c.site_key for c in self.buildable}

    @property
    def n_sites(self) -> int:
        return len(self.sites)

    @property
    def labels(self) -> Counter:
        return Counter(c.label for c in self.buildable)

    @property
    def n_temporal(self) -> int:
        return len({c.site_key for c in self.buildable if c.group == "temporal"})

    @property
    def n_write(self) -> int:
        return len({c.site_key for c in self.buildable if "write" in c.label})

    @property
    def dup_ratio(self) -> float:
        n = len(self.buildable)
        return 1.0 - (self.n_sites / n) if n else 0.0

    @property
    def modularity(self) -> float:
        """1 − share of the single hottest crash-file directory.

        Plugin-style trees (assimp's AssetLib/*) score high; a flat ``src/``
        (harfbuzz, matio) scores low. Conflict rate is an architectural
        property, so this is a first-class ranking term.
        """
        dirs: list[str] = []
        seen: set[str] = set()
        for c in self.buildable:
            if c.site_key in seen:
                continue
            seen.add(c.site_key)
            path = _BUILD_NOISE.sub("", c.crash_file or "")
            dirs.append(os.path.dirname(path) or "?")
        if not dirs:
            return 0.0
        hottest = Counter(dirs).most_common(1)[0][1]
        return 1.0 - hottest / len(dirs)

    def score(self) -> float:
        """Expected benchmark value of a slice built from this group.

        Density and type diversity dominate. Modularity is a weak hint
        (it used to predict pin conflicts; pure archaeology does not pin).
        """
        if self.n_sites < 2:
            return 0.0
        diversity = len(self.labels)
        return (
            self.n_sites
            + 0.5 * self.n_temporal
            + 0.3 * self.n_write
            + 1.5 * diversity
            + 1.0 * self.modularity
        )


def group_by_harness(candidates: list[Candidate], tier: str = "core") -> list[Group]:
    groups: dict[tuple[str, str | None], Group] = {}
    for c in candidates:
        if c.tier != tier:
            continue
        k = (c.project, c.harness)
        g = groups.get(k)
        if g is None:
            g = groups[k] = Group(c.project, c.harness, c.language, c.repo)
        g.members.append(c)
        g.repo = g.repo or c.repo
    return sorted(groups.values(), key=lambda g: g.score(), reverse=True)


def group_by_project(candidates: list[Candidate], tier: str = "core") -> list[Group]:
    groups: dict[str, Group] = {}
    for c in candidates:
        if c.tier != tier:
            continue
        g = groups.get(c.project)
        if g is None:
            g = groups[c.project] = Group(c.project, None, c.language, c.repo)
        g.members.append(c)
        g.repo = g.repo or c.repo
    return sorted(groups.values(), key=lambda g: g.score(), reverse=True)
