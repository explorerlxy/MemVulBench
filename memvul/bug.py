"""Working record for one distinct crash site in the pin pipeline."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .arvo import Candidate

_BUILD_NOISE = re.compile(
    r"^/(?:src|work|build|usr)(?:/[^/]+)*/"
    r"(?=(?:code|src|include|contrib|fuzz|test)/)"
)


@dataclass
class Window:
    """Measured observability window: PoC fires with matching signature."""

    intro: str | None
    intro_date: int | None
    fix: str
    fix_date: int
    contiguous: bool = True
    gaps: list[dict] = field(default_factory=list)
    live_probes: list[str] = field(default_factory=list)
    probes_used: int = 0

    def contains(self, ts: int) -> bool:
        if self.intro_date is None:
            return False
        return self.intro_date <= ts < self.fix_date

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Bug:
    oss_id: int
    project: str
    harness: str | None
    label: str
    group: str
    cwe: str
    repo: str | None
    fix_commit: str | None
    crash_file: str | None
    crash_func: str | None
    crash_line: int | None
    signature: tuple[str, ...] | None
    site_key: str
    report_url: str | None = None

    fix_resolved: str | None = None
    fix_date: int | None = None
    arvo_vuln: str | None = None
    poc: str | None = None

    claim: list[str] = field(default_factory=list)
    claim_level: str = "E0"
    shared_infra: bool = False
    harness_bug: bool = False
    reject: str | None = None
    window: Window | None = None

    def rel_crash_file(self) -> str:
        return project_relpath(self.crash_file or "", self.project)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["signature"] = list(self.signature) if self.signature else None
        return d


def project_relpath(path: str, project: str) -> str:
    """Strip OSS-Fuzz / build prefixes so a crash file is a repo-relative path."""
    if not path:
        return ""
    path = path.replace("\\", "/")
    path = _BUILD_NOISE.sub("", path)
    for prefix in (f"/src/{project}/", f"{project}/", "/src/"):
        if path.startswith(prefix):
            path = path[len(prefix):]
    while path.startswith("../"):
        path = path[3:]
    return path.lstrip("/")


def dedupe(cands: list[Candidate]) -> list[Candidate]:
    """One candidate per crash site; keep the lowest OSS-Fuzz id."""
    best: dict[str, Candidate] = {}
    for c in cands:
        prev = best.get(c.site_key)
        if prev is None or c.oss_id < prev.oss_id:
            best[c.site_key] = c
    return sorted(best.values(), key=lambda c: c.oss_id)


def from_candidate(c: Candidate) -> Bug:
    sig = c.signature
    if isinstance(sig, list):
        sig = tuple(sig)
    return Bug(
        oss_id=c.oss_id,
        project=c.project,
        harness=c.harness,
        label=c.label,
        group=c.group,
        cwe=c.cwe,
        repo=c.repo,
        fix_commit=c.fix_commit,
        crash_file=c.crash_file,
        crash_func=c.crash_func,
        crash_line=c.crash_line,
        signature=sig,
        site_key=c.site_key,
        report_url=c.report_url,
    )


def load_group(cands: list[Candidate], project: str,
               harness: str | None) -> list[Bug]:
    picked = [c for c in cands
              if c.tier == "core" and c.buildable and c.project == project
              and (harness is None or c.harness == harness)]
    return [from_candidate(c) for c in dedupe(picked)]


def resolve_fixes(repo: Path, bugs: list[Bug]) -> None:
    from . import gitutil
    for b in bugs:
        if not b.fix_commit:
            b.reject = b.reject or "commit_missing"
            continue
        sha = gitutil.resolve(repo, b.fix_commit)
        if not sha:
            b.reject = b.reject or "commit_missing"
            continue
        b.fix_resolved = sha
        b.fix_date = gitutil.commit_date(repo, sha)


def attach_pocs(bugs: list[Bug], poc_root: Path) -> None:
    for b in bugs:
        d = poc_root / str(b.oss_id)
        poc = d / "poc"
        if poc.exists():
            b.poc = str(poc)
        meta = d / "meta.json"
        if meta.exists():
            try:
                b.arvo_vuln = json.loads(meta.read_text()).get("vuln_commit")
            except json.JSONDecodeError:
                pass
