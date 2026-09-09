"""Small git helpers shared by the pin pipeline.

The host clone lives under ``/tmp/memvul/repos`` (ext4). The ARVO container
has its own worktree; both are driven through this module, the container one
via ``docker exec`` wrappers in ``sweep.py``.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

WORKDIR = Path("/tmp/memvul/repos")
SRC_EXT = (".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".inl")


class GitError(RuntimeError):
    pass


def git(repo: Path | None, *args: str, check: bool = True,
        timeout: int = 600) -> str:
    cmd = ["git"] + (["-C", str(repo)] if repo else []) + list(args)
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode != 0:
        raise GitError(f"{' '.join(cmd[:8])}: {p.stderr.strip()[:400]}")
    return p.stdout


def clone(url: str, name: str, workdir: Path = WORKDIR) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    dest = workdir / name
    if (dest / ".git").exists():
        return dest
    git(None, "clone", "--quiet", url, str(dest), timeout=3600)
    return dest


def resolve(repo: Path, sha: str) -> str | None:
    out = git(repo, "rev-parse", "--quiet", "--verify", f"{sha}^{{commit}}",
              check=False).strip()
    return out or None


def commit_date(repo: Path, sha: str) -> int:
    return int(git(repo, "show", "-s", "--format=%ct", sha).strip())


def is_ancestor(repo: Path, a: str, b: str) -> bool:
    p = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", a, b],
        capture_output=True)
    return p.returncode == 0


def reset_to(repo: Path, ref: str) -> None:
    subprocess.run(["git", "-C", str(repo), "revert", "--quit"],
                   capture_output=True)
    git(repo, "reset", "--hard", "--quiet", ref)
    git(repo, "clean", "-qfd")


def checkout_detach(repo: Path, ref: str) -> None:
    git(repo, "checkout", "--quiet", "--force", "--detach", ref)
    reset_to(repo, ref)


def checkout_file(repo: Path, commit: str, path: str) -> None:
    git(repo, "checkout", "--quiet", commit, "--", path)


def blob_sha256(repo: Path, commit: str, path: str) -> str | None:
    p = subprocess.run(
        ["git", "-C", str(repo), "show", f"{commit}:{path}"],
        capture_output=True)
    if p.returncode != 0:
        return None
    return hashlib.sha256(p.stdout).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def src_files_at(repo: Path, commit: str, path: str = ".") -> list[str]:
    out = git(repo, "ls-tree", "-r", "--name-only", commit, path)
    return [f for f in out.splitlines() if f.endswith(SRC_EXT)]


def changed_files(repo: Path, a: str, b: str, path: str | None = None) -> list[str]:
    args = ["diff", "--name-only", a, b]
    if path:
        args += ["--", path]
    return [f for f in git(repo, *args).splitlines() if f]


def commits_between(repo: Path, older: str, newer: str) -> list[tuple[str, int]]:
    """Commits in ``(older, newer]`` along first-parent, newest last."""
    out = git(repo, "log", "--first-parent", "--format=%H %ct",
              f"{older}..{newer}")
    rows = []
    for line in out.splitlines():
        sha, ts = line.split()
        rows.append((sha, int(ts)))
    rows.reverse()
    return rows


def log_span(repo: Path, since: int, until: int) -> list[tuple[str, int]]:
    # ``--all``: the worktree HEAD may sit on an old detached commit from a
    # previous experiment; we still want the project's full timeline.
    out = git(repo, "log", "--all", "--first-parent", "--format=%H %ct",
              f"--since={since}", f"--until={until}")
    rows = []
    for line in reversed(out.splitlines()):
        sha, ts = line.split()
        rows.append((sha, int(ts)))
    return rows


def parent(repo: Path, sha: str) -> str | None:
    out = git(repo, "rev-parse", f"{sha}^", check=False).strip()
    return out or None


def midpoint(repo: Path, older: str, newer: str) -> str | None:
    rows = commits_between(repo, older, newer)
    if not rows:
        return None
    return rows[len(rows) // 2][0]
