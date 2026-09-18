"""Build the phase-1 archaeology catalog (docs/catalog.md).

Walk every ARVO project with more than ``min_sites`` distinct core crash
sites, clone the repo, score batch-fix eves, and write one ``target.yaml``
plus a rolled-up index. Measured sweep results override git-level estimates
when present.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
from collections import defaultdict
from pathlib import Path

# Host → replacement clone URL. Object ids are shared with the ARVO remotes.
REPO_MIRRORS: dict[str, str] = {
    "git.ffmpeg.org": "https://github.com/FFmpeg/FFmpeg.git",
    "skia.googlesource.com": "https://github.com/google/skia.git",
    "sourceware.org": "https://github.com/bminor/binutils-gdb.git",
    "cgit.ghostscript.com": "https://github.com/ArtifexSoftware/ghostpdl.git",
    "git.ghostscript.com": "https://github.com/ArtifexSoftware/ghostpdl.git",
}


def _clone_url(url: str) -> str:
    from urllib.parse import urlparse
    host = urlparse(url).netloc.split("@")[-1]
    return REPO_MIRRORS.get(host, url)

from . import candidates, gitutil
from .bug import Bug, from_candidate, project_relpath
from .arvo import Candidate

CATALOG = Path(__file__).resolve().parent.parent / "catalog"
SWEEPS = Path(__file__).resolve().parent.parent / "data" / "sweeps"


def projects_over(cands: list[Candidate], min_sites: int = 10) -> list[str]:
    sites: dict[str, set[str]] = defaultdict(set)
    for c in cands:
        if c.tier == "core" and c.buildable:
            sites[c.project].add(c.site_key)
    return sorted((p for p, s in sites.items() if len(s) > min_sites),
                  key=lambda p: -len(sites[p]))


def group_project(cands: list[Candidate], project: str) -> list[Bug]:
    picked = [c for c in cands
              if c.tier == "core" and c.buildable and c.project == project]
    seen: dict[str, Bug] = {}
    for c in sorted(picked, key=lambda c: c.oss_id):
        if c.site_key in seen:
            continue
        seen[c.site_key] = from_candidate(c)
    return list(seen.values())


def clone_bare(url: str, name: str, workdir: Path = gitutil.WORKDIR,
               timeout: int = 600) -> Path:
    """Partial bare clone: commit graph only, enough to date and ancestry-test."""
    workdir.mkdir(parents=True, exist_ok=True)
    dest = workdir / f"{name}.git"
    if (dest / "HEAD").exists() or dest.exists() and (dest / "objects").exists():
        return dest
    # Prefer a worktree clone we already have.
    wt = workdir / name
    if (wt / ".git").exists():
        return wt
    url = _clone_url(url)
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    cmd = ["git", "clone", "--bare", "--filter=blob:none", "--no-tags",
           "--quiet", url, str(dest)]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           env=env, start_new_session=True)
    except subprocess.TimeoutExpired as e:
        subprocess.run(["rm", "-rf", str(dest)], check=False)
        raise gitutil.GitError(f"clone timeout after {timeout}s: {url}") from e
    if p.returncode != 0:
        raise gitutil.GitError(p.stderr.strip()[:400] or p.stdout.strip()[:400])
    return dest


def _iso(ts: int | None) -> str | None:
    if not ts:
        return None
    return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).date().isoformat()


def _measured_override(project: str, bugs: list[Bug]) -> dict | None:
    """Use an existing sweep ranking when one exists for this project."""
    best = None
    best_n = -1
    for path in SWEEPS.glob(f"{project}_*_bases.json"):
        try:
            rows = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if not rows:
            continue
        top = rows[0]
        n = len(top.get("latent") or [])
        if n > best_n:
            best, best_n = top, n
    if not best:
        return None
    latent_ids = set(best["latent"])
    by_id = {b.oss_id: b for b in bugs}
    return {
        "commit": best["sha"],
        "date": _iso(best["date"]),
        "method": "measured_sweep",
        "n_latent": best_n,
        "n_latent_upper": best_n,
        "latent_ids": [i for i in best["latent"] if i in by_id],
        "source": "sweep",
    }


def analyse(project: str, bugs: list[Bug], repo_url: str,
            workdir: Path = gitutil.WORKDIR) -> dict:
    harnesses = sorted({b.harness or "?" for b in bugs})
    rec: dict = {
        "project": project,
        "repo": repo_url,
        "n_sites": len(bugs),
        "n_issues": len(bugs),
        "harnesses": harnesses,
        "base": None,
        "waves": [],
        "bugs": [],
        "rejected": [],
        "error": None,
    }

    measured = _measured_override(project, bugs)
    try:
        repo = clone_bare(repo_url, project, workdir, timeout=480)
    except (gitutil.GitError, subprocess.TimeoutExpired, OSError) as e:
        rec["error"] = f"clone: {e}"
        rec["base"] = {
            "commit": None, "date": None, "method": "unresolved",
            "n_latent": 0, "n_latent_upper": 0, "n_wave": 0,
            "note": rec["error"],
        }
        rec["bugs"] = [_bug_row(b, "unresolved", "none") for b in bugs]
        return rec

    for b in bugs:
        if not b.fix_commit:
            rec["rejected"].append({"oss_id": b.oss_id, "reason": "commit_missing"})
            continue
        sha = gitutil.resolve(repo, b.fix_commit)
        if not sha:
            rec["rejected"].append({"oss_id": b.oss_id, "reason": "commit_missing"})
            continue
        b.fix_resolved = sha
        b.fix_date = gitutil.commit_date(repo, sha)

    plan = candidates.plan(repo, [b for b in bugs if b.fix_resolved])
    rec["waves"] = [
        {k: w[k] for k in ("day", "n", "eve", "n_latent_upper", "oss_ids")
         if k in w}
        for w in plan["waves"][:12]
    ]

    if measured:
        eve = measured["commit"]
        try:
            eve = gitutil.resolve(repo, eve) or eve
            eve_date = gitutil.commit_date(repo, eve)
        except gitutil.GitError:
            eve_date = None
        latent_ids = set(measured["latent_ids"])
        rec["base"] = {
            "commit": eve,
            "date": measured["date"] or _iso(eve_date),
            "method": "measured_sweep",
            "n_latent": measured["n_latent"],
            "n_latent_upper": measured["n_latent_upper"],
            "n_wave": (plan["best"] or {}).get("n", 0),
            "note": "PoC replay + signature match",
        }
        for b in bugs:
            if b.oss_id in latent_ids:
                rec["bugs"].append(_bug_row(b, "latent", "sweep"))
            elif any(r["oss_id"] == b.oss_id for r in rec["rejected"]):
                continue
            else:
                rec["bugs"].append(_bug_row(b, "not_latent", "sweep"))
        return rec

    best = plan.get("best")
    if not best or not best.get("eve"):
        rec["base"] = {
            "commit": None, "date": None, "method": "unresolved",
            "n_latent": 0, "n_latent_upper": 0, "n_wave": 0,
            "note": "no resolvable fix-wave eve",
        }
        rec["bugs"] = [_bug_row(b, "unresolved", "none")
                       for b in bugs
                       if not any(r["oss_id"] == b.oss_id for r in rec["rejected"])]
        return rec

    eve = best["eve"]
    latent = candidates.score_eve(repo, eve, [b for b in bugs if b.fix_resolved],
                                  horizon_days=730)
    latent_ids = {b.oss_id for b in latent}
    rec["base"] = {
        "commit": eve,
        "date": _iso(best.get("eve_date")),
        "method": "wave_eve",
        "n_latent": len(latent),
        "n_latent_upper": len(latent),
        "n_wave": best["n"],
        "note": f"eve of {best['day']} wave ({best['n']} same-day fixes); "
                f"n_latent is fix-not-landed upper bound",
    }
    for b in bugs:
        if any(r["oss_id"] == b.oss_id for r in rec["rejected"]):
            continue
        if b.oss_id in latent_ids:
            evidence = "wave_member" if b.oss_id in best["oss_ids"] else "fix_not_landed"
            rec["bugs"].append(_bug_row(b, "latent", evidence))
        else:
            rec["bugs"].append(_bug_row(b, "not_latent", "fix_landed"))
    return rec


def _bug_row(b: Bug, status: str, evidence: str) -> dict:
    sig = list(b.signature) if b.signature else None
    return {
        "oss_id": b.oss_id,
        "harness": b.harness,
        "label": b.label,
        "cwe": b.cwe,
        "group": b.group,
        "fix_commit": b.fix_resolved or b.fix_commit,
        "fix_date": _iso(b.fix_date),
        "crash_func": b.crash_func,
        "crash_file": project_relpath(b.crash_file or "", b.project),
        "signature": sig,
        "status": status,
        "evidence": evidence,
        "report": b.report_url,
    }


def write_target(rec: dict, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(_yaml(rec))


def write_index(rows: list[dict], root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    slim = []
    rows = sorted(rows, key=lambda r: (-(r.get("n_sites") or 0), r["project"]))
    for r in rows:
        b = r.get("base") or {}
        slim.append({
            "project": r["project"],
            "repo": r["repo"],
            "n_sites": r["n_sites"],
            "harnesses": r["harnesses"],
            "base": b.get("commit"),
            "base_date": b.get("date"),
            "method": b.get("method"),
            "n_latent": b.get("n_latent"),
            "n_wave": b.get("n_wave"),
            "n_rejected": len(r.get("rejected") or []),
            "error": r.get("error"),
        })
    (root / "index.json").write_text(json.dumps(slim, indent=1) + "\n")
    write_index_md(slim, root)


def write_index_md(slim: list[dict], root: Path) -> None:
    lines = [
        "# MemVulBench 考古目录",
        "",
        "ARVO 核心内存漏洞去重崩溃点 **> 10** 的全部项目。",
        "每行的基线是该项目上**天然潜伏数量最多**的上游 commit。",
        "口径见 [docs/catalog.md](../docs/catalog.md)。",
        "",
        f"项目数：{len(slim)}　"
        f"其中已解析基线：{sum(1 for s in slim if s['base'])}　"
        f"潜伏合计：{sum(s['n_latent'] or 0 for s in slim)}　"
        f"已实测：{sum(1 for s in slim if s.get('method') == 'measured_sweep')}",
        "",
        "| 项目 | 崩溃点 | 基线 | 日期 | 潜伏 | 波规模 | 方法 |",
        "|---|---:|---|---|---:|---:|---|",
    ]
    for s in slim:
        sha = (s["base"] or "—")[:12]
        lines.append(
            f"| [{s['project']}]({s['project']}/target.yaml) "
            f"| {s['n_sites']} "
            f"| `{sha}` "
            f"| {s['base_date'] or '—'} "
            f"| {s['n_latent'] if s['n_latent'] is not None else '—'} "
            f"| {s['n_wave'] if s['n_wave'] is not None else '—'} "
            f"| {s['method'] or '—'} |"
        )
    (root / "index.md").write_text("\n".join(lines) + "\n")


def patch_index_entry(root: Path, project: str, updates: dict) -> None:
    """Update one project's slim row and regenerate the human index."""
    path = root / "index.json"
    slim = json.loads(path.read_text())
    for s in slim:
        if s["project"] == project:
            s.update(updates)
            break
    path.write_text(json.dumps(slim, indent=1) + "\n")
    write_index_md(slim, root)


def _yaml(obj, indent: int = 0) -> str:
    """Minimal YAML emitter; avoids a PyYAML dependency."""
    sp = "  " * indent
    if isinstance(obj, dict):
        if not obj:
            return "{}\n"
        parts = []
        for k, v in obj.items():
            if v is None:
                parts.append(f"{sp}{k}: null\n")
            elif isinstance(v, bool):
                parts.append(f"{sp}{k}: {'true' if v else 'false'}\n")
            elif isinstance(v, (int, float)):
                parts.append(f"{sp}{k}: {v}\n")
            elif isinstance(v, str):
                parts.append(f"{sp}{k}: {_q(v)}\n")
            elif isinstance(v, dict):
                parts.append(f"{sp}{k}:\n")
                parts.append(_yaml(v, indent + 1))
            elif isinstance(v, list):
                if not v:
                    parts.append(f"{sp}{k}: []\n")
                elif all(isinstance(x, (str, int, float, type(None))) for x in v):
                    inner = ", ".join("null" if x is None else _q(x) if isinstance(x, str) else str(x)
                                      for x in v)
                    parts.append(f"{sp}{k}: [{inner}]\n")
                else:
                    parts.append(f"{sp}{k}:\n")
                    for x in v:
                        if isinstance(x, dict):
                            first = True
                            for kk, vv in x.items():
                                prefix = "- " if first else "  "
                                first = False
                                if isinstance(vv, list) and vv and not isinstance(vv[0], dict):
                                    inner = ", ".join(_q(i) if isinstance(i, str) else str(i) for i in vv)
                                    parts.append(f"{sp}  {prefix}{kk}: [{inner}]\n")
                                elif vv is None:
                                    parts.append(f"{sp}  {prefix}{kk}: null\n")
                                else:
                                    parts.append(f"{sp}  {prefix}{kk}: {_q(vv) if isinstance(vv, str) else vv}\n")
                        else:
                            parts.append(f"{sp}  - {_q(x) if isinstance(x, str) else x}\n")
            else:
                parts.append(f"{sp}{k}: {_q(str(v))}\n")
        return "".join(parts)
    return _q(str(obj)) + "\n"


def _q(s: str) -> str:
    if s == "" or any(c in s for c in ":#{}[]&*!|>'\"%@`) \t\n"):
        return json.dumps(s, ensure_ascii=False)
    return s
