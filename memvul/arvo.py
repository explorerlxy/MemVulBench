"""Ingest ARVO-Meta into the MemVulBench candidate catalog.

ARVO gives us, per OSS-Fuzz issue: the project, the fuzz target, the
sanitizer report that OSS-Fuzz saw, and the upstream fix commit. That is
exactly the raw material for fix-reversal densification (docs/design.md D3):
the fix commit is what we revert, and the report is the reference signature
the re-introduced bug must reproduce.
"""

from __future__ import annotations

import os

import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from . import asan
from .taxonomy import VulnClass, classify

DEFAULT_DB = Path(
    os.environ.get(
        "MEMVUL_ARVO_DB",
        "/media/hahafish/Data/ForUbuntu/BoostFuzz/benchmarks/bug-catalog/cybergym/arvo.db",
    )
)


@dataclass
class Candidate:
    """One ARVO issue, normalised and classified."""

    oss_id: int
    project: str
    harness: str | None
    engine: str | None
    sanitizer: str | None
    language: str | None
    crash_type: str | None
    fix_commit: str | None
    repo: str | None
    patch_url: str | None
    report_url: str | None
    severity: str | None
    submodule_bug: bool

    tier: str
    group: str
    cwe: str
    label: str

    crash_func: str | None
    crash_file: str | None
    crash_line: int | None
    alloc_func: str | None
    free_func: str | None
    signature: tuple[str, ...] | None

    @property
    def site_key(self) -> str:
        """Identity of the *code location*, used to collapse near-duplicates.

        ARVO contains many issues that are the same underlying defect
        rediscovered through a different input; they share a crash site.
        Counting distinct site keys is the honest density measure.
        """
        return f"{self.crash_file or '?'}::{self.crash_func or '?'}::{self.label}"

    @property
    def buildable(self) -> bool:
        """Can we even attempt a fix-reversal build for this issue?"""
        return bool(self.fix_commit and self.repo and not self.submodule_bug)


def _row_to_candidate(row: sqlite3.Row) -> Candidate:
    cls: VulnClass = classify(row["crash_type"])
    rep = asan.parse(row["crash_output"] or "")
    site, alloc, freed = rep.crash_site, rep.alloc_site, rep.free_site
    return Candidate(
        oss_id=row["localId"],
        project=row["project"],
        harness=row["fuzz_target"],
        engine=row["fuzz_engine"],
        sanitizer=row["sanitizer"],
        language=row["language"],
        crash_type=row["crash_type"],
        fix_commit=row["fix_commit"],
        repo=row["repo_addr"],
        patch_url=row["patch_url"],
        report_url=row["report"],
        severity=row["severity"],
        submodule_bug=bool(row["submodule_bug"]),
        tier=cls.tier,
        group=cls.group,
        cwe=cls.cwe,
        label=cls.label,
        crash_func=site.func if site else None,
        crash_file=site.file if site else None,
        crash_line=site.line if site else None,
        alloc_func=alloc.func if alloc else None,
        free_func=freed.func if freed else None,
        signature=rep.signature() if rep.kind else None,
    )


def load(db: Path = DEFAULT_DB) -> list[Candidate]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [_row_to_candidate(r) for r in conn.execute("SELECT * FROM arvo")]
    finally:
        conn.close()


def dump(candidates: list[Candidate], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(c) | {"site_key": c.site_key} for c in candidates]
    out.write_text(json.dumps(payload, indent=1, ensure_ascii=False))
