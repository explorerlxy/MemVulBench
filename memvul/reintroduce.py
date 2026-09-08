"""Fix-reversal planning (docs/design.md D3).

Given a candidate group (project + harness) and its ARVO fix commits, work
out which base commit yields the most co-resident bugs, and which of those
bugs need a revert patch versus already being latent at that base.

For a base commit ``B`` and a bug whose upstream fix is ``F``:

* ``F`` is **not** an ancestor of ``B``  -> the fix has not landed yet, so the
  bug is *latent* at ``B`` provided it had already been introduced. Nothing to
  patch; the PoC replay decides.
* ``F`` **is** an ancestor of ``B``      -> the fix has landed, so the bug must
  be re-introduced by reverting ``F``. Whether that revert applies is decided
  mechanically here; whether it actually restores the bug is decided later by
  the PoC replay and the negative control.

Only the git-level question is answered in this module. Nothing here is
evidence that a bug reproduces; that is the job of the admission gate.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

WORKDIR = Path("/tmp/memvul/repos")


class GitError(RuntimeError):
    pass


def git(repo: Path | None, *args: str, check: bool = True,
        timeout: int = 600) -> str:
    cmd = ["git"] + (["-C", str(repo)] if repo else []) + list(args)
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode != 0:
        raise GitError(f"{' '.join(cmd[:6])}: {p.stderr.strip()[:300]}")
    return p.stdout


def clone(url: str, name: str, workdir: Path = WORKDIR) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    dest = workdir / name
    if (dest / ".git").exists():
        return dest
    git(None, "clone", "--quiet", url, str(dest), timeout=3600)
    return dest


@dataclass
class BugRef:
    oss_id: int
    fix: str
    label: str
    resolved: str | None = None
    date: int | None = None
    intro: str | None = None
    intro_date: int | None = None


@dataclass
class BasePlan:
    base: str
    base_date: int
    present: list[int] = field(default_factory=list)      # fix not landed, intro before base
    not_yet: list[int] = field(default_factory=list)      # introduced after base
    intro_unknown: list[int] = field(default_factory=list)
    revert_ok: list[int] = field(default_factory=list)
    revert_conflict: list[int] = field(default_factory=list)
    revert_skipped: list[int] = field(default_factory=list)  # older than the window
    stacked: list[int] = field(default_factory=list)

    @property
    def candidates(self) -> int:
        """Bugs worth trying to verify at this base. An upper bound."""
        return len(self.present) + len(self.intro_unknown) + len(self.stacked)


def resolve(repo: Path, bugs: list[BugRef]) -> tuple[list[BugRef], list[BugRef]]:
    """Split bugs into those whose fix commit exists in the clone and those not."""
    ok, missing = [], []
    for b in bugs:
        out = git(repo, "rev-parse", "--quiet", "--verify", f"{b.fix}^{{commit}}",
                  check=False).strip()
        if not out:
            missing.append(b)
            continue
        b.resolved = out
        b.date = int(git(repo, "show", "-s", "--format=%ct", out).strip())
        ok.append(b)
    return ok, missing


_HUNK_RE = __import__("re").compile(r"^@@ -(\d+)(?:,(\d+))? \+")
_SRC_EXT = (".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx")


def blame_intro(repo: Path, fix: str, max_files: int = 12,
                max_hunks: int = 40) -> tuple[str | None, int | None]:
    """Estimate the bug-introducing commit for ``fix`` (SZZ-style).

    Blame the lines that the fix deleted or modified, taken against the fix's
    parent; the newest commit among them is when the defect became reachable.
    Pure insertions (a bounds check added with nothing removed) have no deleted
    lines, so the insertion point's neighbouring context is blamed instead.

    This is an estimate. It is used only to decide which base commits are worth
    building, never as evidence that a bug is present.
    """
    parent = git(repo, "rev-parse", f"{fix}^", check=False).strip()
    if not parent:
        return None, None
    files = [f for f in git(repo, "show", "--pretty=", "--name-only", fix).split()
             if f.endswith(_SRC_EXT)][:max_files]
    if not files:
        return None, None

    commits: set[str] = set()
    hunks = 0
    for path in files:
        diff = git(repo, "show", "--unified=0", "--pretty=", fix, "--", path,
                   check=False)
        for line in diff.split("\n"):
            m = _HUNK_RE.match(line)
            if not m or hunks >= max_hunks:
                continue
            hunks += 1
            start, count = int(m.group(1)), int(m.group(2) or 1)
            lo = max(1, start if count else start - 1)
            hi = start + max(count, 2) - 1
            out = git(repo, "blame", "--porcelain", "-L", f"{lo},{hi}",
                      parent, "--", path, check=False, timeout=120)
            for bl in out.split("\n"):
                if len(bl) >= 40 and bl[:40].isalnum() and " " in bl:
                    sha = bl.split(" ")[0]
                    if len(sha) == 40:
                        commits.add(sha)
    if not commits:
        return None, None

    newest, newest_ts = None, -1
    for sha in commits:
        ts = git(repo, "show", "-s", "--format=%ct", sha, check=False).strip()
        if ts and int(ts) > newest_ts:
            newest, newest_ts = sha, int(ts)
    return newest, (newest_ts if newest_ts >= 0 else None)


def _is_ancestor(repo: Path, a: str, b: str) -> bool:
    p = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", a, b],
                       capture_output=True)
    return p.returncode == 0


def _reset_to(repo: Path, ref: str) -> None:
    subprocess.run(["git", "-C", str(repo), "revert", "--quit"], capture_output=True)
    git(repo, "reset", "--hard", "--quiet", ref)
    git(repo, "clean", "-qfd")


def _try_revert(repo: Path, commit: str, keep: bool = False) -> bool:
    """Revert ``commit`` onto the current tree.

    On success with ``keep``, the result is committed so that the next revert
    stacks on top of it and a failure can be rolled back to it. Without a
    commit to reset to, a conflicted revert leaves unmerged entries in the
    index that silently poison every later attempt.
    """
    p = subprocess.run(
        ["git", "-C", str(repo), "revert", "--no-commit", "--no-edit", commit],
        capture_output=True, text=True)
    if p.returncode != 0:
        _reset_to(repo, "HEAD")
        return False
    if keep:
        subprocess.run(
            ["git", "-C", str(repo), "-c", "user.email=bench@memvul",
             "-c", "user.name=memvul", "commit", "--quiet", "--no-verify",
             "--allow-empty", "-m", f"memvul: revert {commit[:12]}"],
            capture_output=True)
    else:
        _reset_to(repo, "HEAD")
    return True


def evaluate_base(repo: Path, base: str, base_date: int, bugs: list[BugRef],
                  window_days: int = 730) -> BasePlan:
    """Score one base commit.

    ``window_days`` bounds how far back a fix may be and still be worth trying
    to revert. Measured on harfbuzz: reverts land essentially always within
    ~180 days of the base and essentially never past ~400 days, because the
    surrounding code has moved on. Skipping the far ones costs almost no recall
    and removes most of the work.
    """
    plan = BasePlan(base=base, base_date=base_date)
    git(repo, "checkout", "--quiet", "--force", "--detach", base)
    _reset_to(repo, base)

    needs_revert: list[BugRef] = []
    for b in bugs:
        assert b.resolved
        if b.resolved != base and _is_ancestor(repo, b.resolved, base):
            if b.date and base_date - b.date > window_days * 86400:
                plan.revert_skipped.append(b.oss_id)
            else:
                needs_revert.append(b)
        elif b.intro is None:
            plan.intro_unknown.append(b.oss_id)
        elif _is_ancestor(repo, b.intro, base):
            plan.present.append(b.oss_id)   # introduced, not yet fixed
        else:
            plan.not_yet.append(b.oss_id)   # defect does not exist yet

    # Pass 1, isolated: does each revert apply to the pristine base at all?
    # This is the ceiling, independent of ordering.
    for b in needs_revert:
        assert b.resolved
        (plan.revert_ok if _try_revert(repo, b.resolved)
         else plan.revert_conflict).append(b.oss_id)
        _reset_to(repo, base)

    # Pass 2, stacked: newest fix first, so that undoing recent changes brings
    # the tree closer to the state each older patch was written against.
    ok = set(plan.revert_ok)
    for b in sorted((b for b in needs_revert if b.oss_id in ok),
                    key=lambda b: b.date or 0, reverse=True):
        assert b.resolved
        if _try_revert(repo, b.resolved, keep=True):
            plan.stacked.append(b.oss_id)
    git(repo, "checkout", "--quiet", "--force", "--detach", base)
    _reset_to(repo, base)
    return plan


def rank_bases(bugs: list[BugRef], window_days: int = 730,
               n: int = 12) -> list[tuple[str, int]]:
    """Shortlist bases by an optimistic, git-free estimate of slice size.

    A base can host a bug if the bug is live there (``[intro, fix)`` stabs it)
    or if its fix is recent enough to be worth reverting. Both are cheap date
    comparisons; the expensive revert test then runs only on the shortlist.
    """
    windows = [(b.intro_date, b.date) for b in bugs
               if b.intro_date and b.date and b.intro_date < b.date]
    fixes = [b.date for b in bugs if b.date]
    pool = [(b.resolved, b.date) for b in bugs if b.resolved and b.date]

    def bound(ts: int) -> int:
        live = sum(1 for lo, hi in windows if lo <= ts < hi)
        revertible = sum(1 for f in fixes if 0 < ts - f <= window_days * 86400)
        return live + revertible

    return sorted(
        ((sha, ts) for sha, ts in pool if sha),
        key=lambda p: bound(p[1]), reverse=True,
    )[:n]


def plan_group(project: str, harness: str | None, repo_url: str,
               bugs: list[BugRef], n_bases: int = 12, window_days: int = 730,
               workdir: Path = WORKDIR) -> dict:
    repo = clone(repo_url, project, workdir)
    resolved, missing = resolve(repo, bugs)
    for b in resolved:
        assert b.resolved
        b.intro, b.intro_date = blame_intro(repo, b.resolved)

    plans = [evaluate_base(repo, base, ts, resolved, window_days)
             for base, ts in rank_bases(resolved, window_days, n_bases)]
    plans.sort(key=lambda p: p.candidates, reverse=True)
    return {
        "project": project,
        "harness": harness,
        "repo": repo_url,
        "n_bugs": len(bugs),
        "n_resolved": len(resolved),
        "n_missing_commit": len(missing),
        "n_intro_estimated": sum(1 for b in resolved if b.intro),
        "missing": [b.oss_id for b in missing],
        "windows": {
            str(b.oss_id): {"intro": (b.intro or "")[:12], "intro_date": b.intro_date,
                            "fix": (b.resolved or "")[:12], "fix_date": b.date,
                            "label": b.label}
            for b in resolved
        },
        "bases": [
            {
                "base": p.base[:12],
                "base_date": p.base_date,
                "present": len(p.present),
                "intro_unknown": len(p.intro_unknown),
                "not_yet": len(p.not_yet),
                "revert_ok": len(p.revert_ok),
                "revert_conflict": len(p.revert_conflict),
                "revert_skipped": len(p.revert_skipped),
                "stacked": len(p.stacked),
                "candidates": p.candidates,
                "ids": {"present": p.present, "stacked": p.stacked,
                        "unknown": p.intro_unknown, "conflict": p.revert_conflict},
            }
            for p in plans
        ],
    }


def save(result: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1))
