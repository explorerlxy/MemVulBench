"""Claim-set and pin-pair solver (methodology.md §3–§4).

E0 claim = source files touched by the fix. Expansion E1–E4 runs later,
when verify sees a compile or replay failure. This module only does the
git-level work: claim, harness/infra tags, vul-pin / fix-pin selection.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import gitutil
from .bug import Bug
from .gitutil import SRC_EXT

HARNESS_HINTS = (
    "fuzz/", "fuzzer", "ossfuzz", "oss-fuzz", "test/fuzzing",
)
TEST_PREFIXES = ("test/", "tests/", "unittests/")

# Directories that methodology.md §6 says must not share a slice with
# plugin-local bugs. Extend per project as we learn more.
INFRA_PREFIXES: dict[str, tuple[str, ...]] = {
    "assimp": ("code/Common/", "include/assimp/"),
}


@dataclass
class FilePin:
    file: str
    on_commit: str
    off_commit: str
    on_blob: str | None
    off_blob: str | None
    bugs: list[int]
    fidelity: str = "file"
    direction: str = "backward"
    reason: str = "fix_touched"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PinPlan:
    project: str
    harness: str | None
    base: str
    base_date: int
    latent: list[int] = field(default_factory=list)
    mosaic: list[int] = field(default_factory=list)
    rejected: dict[str, str] = field(default_factory=dict)
    pins: list[FilePin] = field(default_factory=list)
    function_pin_candidates: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["pins"] = [p.to_dict() for p in self.pins]
        return d


def claim_e0(repo: Path, bug: Bug) -> list[str]:
    if not bug.fix_resolved:
        bug.reject = bug.reject or "commit_missing"
        return []
    names = gitutil.git(repo, "show", "--pretty=", "--name-only",
                        bug.fix_resolved).split()
    src = [f for f in names if f.endswith(SRC_EXT)]
    src = [f for f in src if not f.startswith(TEST_PREFIXES)]
    if not src:
        bug.reject = bug.reject or "no_source_change"
        return []
    if all(_is_harness(f) for f in src):
        bug.harness_bug = True
        bug.reject = bug.reject or "harness_bug"
        return []
    src = [f for f in src if not _is_harness(f)]
    if not src:
        bug.harness_bug = True
        bug.reject = bug.reject or "harness_bug"
        return []
    prefixes = INFRA_PREFIXES.get(bug.project, ())
    bug.shared_infra = any(f.startswith(prefixes) for f in src) if prefixes else False
    return src


def _is_harness(path: str) -> bool:
    low = path.lower()
    return any(h in low for h in HARNESS_HINTS)


def expand_e1(repo: Path, files: list[str], pin: str, base: str) -> list[str]:
    """Same-directory headers that changed between the pin and the base."""
    extra: list[str] = []
    dirs = {str(Path(f).parent) for f in files}
    for d in dirs:
        try:
            changed = gitutil.changed_files(repo, pin, base, d)
        except gitutil.GitError:
            continue
        for f in changed:
            if f.endswith((".h", ".hh", ".hpp", ".hxx", ".inl")) and f not in files:
                extra.append(f)
    return sorted(set(extra))


def expand_e2(bug: Bug, repo: Path, pin: str, base: str) -> list[str]:
    """Whole directory of the crash site, files that differ from the base."""
    rel = bug.rel_crash_file()
    if not rel:
        return []
    d = str(Path(rel).parent)
    try:
        changed = gitutil.changed_files(repo, pin, base, d)
    except gitutil.GitError:
        return []
    return [f for f in changed if f.endswith(SRC_EXT)]


def expand_e3(repo: Path, files: list[str], pin: str, base: str) -> list[str]:
    """Changed files that any current claim file includes, one hop."""
    extra: list[str] = []
    for f in files:
        try:
            body = gitutil.git(repo, "show", f"{pin}:{f}", check=False)
        except gitutil.GitError:
            continue
        parent = str(Path(f).parent)
        for line in body.splitlines():
            line = line.strip()
            if not (line.startswith("#include") and '"' in line):
                continue
            name = line.split('"', 2)[1]
            cand = str(Path(parent) / name)
            cand = str(Path(cand))  # normalise ./
            if cand in files:
                continue
            if gitutil.blob_sha256(repo, pin, cand) is None:
                continue
            if gitutil.changed_files(repo, pin, base, cand):
                extra.append(cand)
    return sorted(set(extra))


def _closest_with_dates(bug: Bug, base_date: int,
                        dates: dict[str, int]) -> str | None:
    w = bug.window
    if not w or not w.live_probes:
        return None
    best, best_d = None, None
    for sha in w.live_probes:
        ts = dates.get(sha)
        if ts is None:
            continue
        dist = abs(ts - base_date)
        if best_d is None or dist < best_d:
            best, best_d = sha, dist
    return best or w.live_probes[-1]


def _windows_overlap(a: Bug, b: Bug) -> bool:
    wa, wb = a.window, b.window
    if not wa or not wb or wa.intro_date is None or wb.intro_date is None:
        return False
    return wa.intro_date < wb.fix_date and wb.intro_date < wa.fix_date


def plan(repo: Path, bugs: list[Bug], base: str,
         probe_dates: dict[str, int] | None = None) -> PinPlan:
    base = gitutil.resolve(repo, base) or base
    base_date = gitutil.commit_date(repo, base)
    probe_dates = probe_dates or {}
    out = PinPlan(project=bugs[0].project if bugs else "",
                  harness=bugs[0].harness if bugs else None,
                  base=base, base_date=base_date)

    eligible: list[Bug] = []
    for b in bugs:
        if b.reject:
            out.rejected[str(b.oss_id)] = b.reject
            continue
        if not b.window or b.window.intro_date is None:
            b.reject = b.reject or "window_unmeasured"
            out.rejected[str(b.oss_id)] = b.reject
            continue
        b.claim = claim_e0(repo, b)
        if b.reject:
            out.rejected[str(b.oss_id)] = b.reject
            continue
        if b.window.contains(base_date):
            out.latent.append(b.oss_id)
        else:
            out.mosaic.append(b.oss_id)
        eligible.append(b)

    # File → bugs claiming it.
    by_file: dict[str, list[Bug]] = {}
    for b in eligible:
        for f in b.claim:
            by_file.setdefault(f, []).append(b)

    # Cluster co-claimers with overlapping windows into one FilePin.
    # Disjoint-window co-claimers become function-pin candidates; slice
    # will drop all but one of them from a given slice.
    for path, owners in sorted(by_file.items()):
        clusters: list[list[Bug]] = []
        for b in owners:
            placed = False
            for cl in clusters:
                if any(_windows_overlap(b, x) for x in cl):
                    cl.append(b)
                    placed = True
                    break
            if not placed:
                clusters.append([b])
        if len(clusters) > 1:
            # True conflict on this file. Keep every cluster's pin; the
            # slice solver decides which cluster enters which slice.
            for cl in clusters[1:]:
                for b in cl:
                    if b.oss_id not in out.function_pin_candidates:
                        out.function_pin_candidates.append(b.oss_id)

        for cl in clusters:
            on = _cluster_on(cl, base_date, probe_dates)
            if on is None:
                for b in cl:
                    out.rejected.setdefault(str(b.oss_id), "window_unmeasured")
                continue
            # Independent OFF uses the earliest fix in the cluster: that
            # is the first commit at which the shared file is "all fixed"
            # for the oldest member. Later members stay a toggle unit if
            # their own fix is a different blob — recorded on the bug list.
            off = max(cl, key=lambda b: b.fix_date or 0).fix_resolved
            if off is None:
                continue
            direction = "backward" if gitutil.commit_date(repo, on) <= base_date \
                else "forward"
            # Latent cluster: ON is the base itself (no rewrite).
            if all(b.window and b.window.contains(base_date) for b in cl):
                on = base
                direction = "backward"
            out.pins.append(FilePin(
                file=path,
                on_commit=on,
                off_commit=off,
                on_blob=gitutil.blob_sha256(repo, on, path),
                off_blob=gitutil.blob_sha256(repo, off, path),
                bugs=[b.oss_id for b in cl],
                direction=direction,
                reason="fix_touched",
            ))
    return out


def _cluster_on(cl: list[Bug], base_date: int,
                dates: dict[str, int]) -> str | None:
    # Intersection of live-probe sets, then closest to base.
    sets = [set(b.window.live_probes) for b in cl if b.window]
    if not sets:
        return None
    inter = set.intersection(*sets)
    if not inter:
        # Fall back to each bug's own closest; they should agree on fix^.
        return _closest_with_dates(cl[0], base_date, dates)
    best, best_d = None, None
    for sha in inter:
        ts = dates.get(sha)
        if ts is None:
            continue
        dist = abs(ts - base_date)
        if best_d is None or dist < best_d:
            best, best_d = sha, dist
    return best or next(iter(inter))
