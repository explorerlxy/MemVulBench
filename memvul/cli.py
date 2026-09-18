"""MemVulBench command line entry point."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from . import arvo, basepick, bug as bugmod, candidates, catalog, fetch
from . import measure, select, sweep
from .gitutil import clone

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "census"
SWEEPS = ROOT / "data" / "sweeps"


def _load(args) -> list[arvo.Candidate]:
    cache = DATA / "arvo_candidates.json"
    if cache.exists() and not args.refresh:
        raw = json.loads(cache.read_text())
        return [
            arvo.Candidate(**{k: v for k, v in r.items() if k != "site_key"})
            for r in raw
        ]
    cands = arvo.load(Path(args.db))
    arvo.dump(cands, cache)
    return cands


def cmd_census(args) -> None:
    cands = _load(args)
    print(f"ARVO issues: {len(cands)}\n")

    tiers = Counter(c.tier for c in cands)
    print("=== tier ===")
    for t in ("core", "extended", "out"):
        print(f"  {t:<9} {tiers[t]:5d}  ({tiers[t] / len(cands):5.1%})")

    core = [c for c in cands if c.tier == "core"]
    print(f"\n=== core memory-safety: {len(core)} ===")
    for g, n in Counter(c.group for c in core).most_common():
        print(f"  {g:<10} {n:5d}")
    print()
    for lab, n in Counter(c.label for c in core).most_common():
        print(f"  {lab:<22} {n:5d}")

    buildable = [c for c in core if c.buildable]
    sites = {c.site_key for c in buildable}
    parsed = [c for c in core if c.crash_func]
    print(f"\n=== feasibility (core) ===")
    print(f"  with fix_commit + repo, not submodule : {len(buildable):5d}")
    print(f"  with parsed crash site               : {len(parsed):5d}"
          f"  ({len(parsed) / len(core):.1%})")
    print(f"  distinct crash sites (buildable)     : {len(sites):5d}")
    print(f"  duplicate-issue ratio                : "
          f"{1 - len(sites) / max(len(buildable), 1):.1%}")


def _print_groups(groups: list[select.Group], limit: int, show_labels: bool) -> None:
    head = (f"{'score':>6} {'sites':>5} {'issues':>6} {'dup':>5} "
            f"{'temp':>5} {'wr':>4} {'mod':>5}  target")
    print(head)
    print("-" * (len(head) + 24))
    for g in groups[:limit]:
        name = g.key if g.harness else g.project
        print(f"{g.score():6.1f} {g.n_sites:5d} {len(g.buildable):6d} "
              f"{g.dup_ratio:4.0%} {g.n_temporal:5d} {g.n_write:4d} "
              f"{g.modularity:5.2f}  {name}")
        if show_labels:
            top = ", ".join(f"{k}×{v}" for k, v in g.labels.most_common(5))
            print(f"{'':>29}   {top}")


def cmd_slices(args) -> None:
    cands = _load(args)
    groups = (select.group_by_project if args.by == "project"
              else select.group_by_harness)(cands)
    groups = [g for g in groups if g.n_sites >= args.min_sites]
    print(f"candidate {args.by} groups with >= {args.min_sites} distinct "
          f"crash sites: {len(groups)}\n")
    _print_groups(groups, args.limit, args.labels)

    total = sum(g.n_sites for g in groups[:args.limit])
    print(f"\ntop-{min(args.limit, len(groups))} combined distinct sites: {total}")

    out = DATA / f"slices_by_{args.by}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps([
        {
            "project": g.project,
            "harness": g.harness,
            "language": g.language,
            "repo": g.repo,
            "score": round(g.score(), 2),
            "n_sites": g.n_sites,
            "n_issues": len(g.buildable),
            "n_temporal": g.n_temporal,
            "n_write": g.n_write,
            "modularity": round(g.modularity, 3),
            "labels": dict(g.labels),
            "oss_ids": [c.oss_id for c in g.buildable],
        }
        for g in groups
    ], indent=1))
    print(f"wrote {out.relative_to(ROOT)}")


def cmd_fetch(args) -> None:
    root = Path(args.dest)
    ids = args.ids

    ok, failed, total = [], [], 0
    for i, oss_id in enumerate(ids, 1):
        dest = root / str(oss_id)
        if (dest / "poc").exists() and not args.refresh:
            print(f"[{i}/{len(ids)}] {oss_id} cached")
            ok.append(oss_id)
            continue
        try:
            r = fetch.extract(oss_id, dest, want_binary=args.binary)
            total += r["fetched_bytes"]
            print(f"[{i}/{len(ids)}] {oss_id} poc={r['poc']['size']}B "
                  f"vul={r['vuln_commit'] or '?'} "
                  f"(fetched {r['fetched_bytes'] / 1e6:.0f}MB of "
                  f"{r['image_size'] / 1e9:.1f}GB image)", flush=True)
            (dest / "meta.json").write_text(json.dumps(r, indent=1))
            ok.append(oss_id)
        except Exception as e:  # noqa: BLE001 - report and keep going
            print(f"[{i}/{len(ids)}] {oss_id} FAILED: {type(e).__name__}: {e}",
                  flush=True)
            failed.append(oss_id)

    print(f"\nfetched {len(ok)}/{len(ids)}, {total / 1e9:.2f} GB transferred")
    if failed:
        print(f"failed: {failed}")


def cmd_candidates(args) -> None:
    bugs, repo = _prepare(args)
    plan = candidates.plan(repo, bugs, min_wave=args.min_wave)
    print(f"{args.project}: {plan['n_dated']}/{plan['n_bugs']} dated, "
          f"{plan['n_waves']} waves")
    print(f"{'day':<12}{'n':>5}{'upper':>7}  eve")
    print("-" * 52)
    for w in plan["waves"][: args.limit]:
        eve = (w.get("eve") or "—")[:12]
        print(f"{w['day']:<12}{w['n']:5d}{w.get('n_latent_upper') or 0:7d}  {eve}")
    if plan["best"]:
        b = plan["best"]
        print(f"\npick: {b['eve'][:12]}  day={b['day']}  "
              f"wave={b['n']}  latent_upper={b['n_latent_upper']}")
    out = DATA.parent / "candidates" / f"{args.project}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=1))
    print(f"wrote {out.relative_to(ROOT)}")


def cmd_catalog(args) -> None:
    cands = _load(args)
    names = catalog.projects_over(cands, min_sites=args.min_sites)
    if args.only:
        names = [p for p in names if p in args.only]
    # Small trees first so one ffmpeg-sized clone cannot stall the directory.
    names = list(reversed(names)) if not args.only else names
    print(f"projects with >{args.min_sites} distinct core sites: {len(names)}")
    rows: list[dict] = []
    root = Path(args.dest)
    for i, name in enumerate(names, 1):
        bugs = catalog.group_project(cands, name)
        repo_url = next((b.repo for b in bugs if b.repo), None)
        print(f"[{i}/{len(names)}] {name}  sites={len(bugs)} ...", flush=True)
        if not repo_url:
            rec = {"project": name, "repo": None, "n_sites": len(bugs),
                   "n_issues": len(bugs), "harnesses": [], "base": None,
                   "waves": [], "bugs": [], "rejected": [],
                   "error": "no repo URL"}
        else:
            try:
                rec = catalog.analyse(name, bugs, repo_url)
            except Exception as e:  # noqa: BLE001
                rec = {"project": name, "repo": repo_url, "n_sites": len(bugs),
                       "n_issues": len(bugs), "harnesses": sorted({b.harness or '?' for b in bugs}),
                       "base": {"commit": None, "date": None, "method": "unresolved",
                                "n_latent": 0, "n_latent_upper": 0, "n_wave": 0,
                                "note": f"{type(e).__name__}: {e}"},
                       "waves": [], "bugs": [], "rejected": [],
                       "error": f"{type(e).__name__}: {e}"}
        catalog.write_target(rec, root / name / "target.yaml")
        rows.append(rec)
        catalog.write_index(rows, root)
        base = rec.get("base") or {}
        print(f"    {base.get('method')}  latent={base.get('n_latent')}  "
              f"base={(base.get('commit') or '—')[:12]}  "
              f"{rec.get('error') or ''}", flush=True)
    catalog.write_index(rows, root)
    ok = sum(1 for r in rows if (r.get("base") or {}).get("commit"))
    latent = sum((r.get("base") or {}).get("n_latent") or 0 for r in rows)
    print(f"\n{ok}/{len(rows)} projects resolved, {latent} latent bugs recorded")
    print(f"wrote {root / 'index.md'}")


def cmd_measure(args) -> None:
    cands = _load(args)
    if args.project and not args.queue:
        names = [args.project]
    else:
        q = measure.queue(min_sites=args.min_sites,
                          min_latent=getattr(args, "min_latent", 8))
        take = q if args.limit <= 0 else q[: args.limit]
        if args.project:
            names = [args.project] + [p for p in take if p != args.project]
            if args.limit > 0:
                names = names[: args.limit]
        else:
            names = take
    if not names:
        print("queue empty (everything measured or unresolved)")
        return
    # Preparation only: PoCs and a builder image. All target work is manual.
    print(f"prepare queue: {names}", flush=True)
    name = names[0]
    print(f"\n=== prepare {name} ===", flush=True)
    out = measure.prepare_project(name)
    print(f"  ready {name}: {out.get('container')} {out.get('builder')} "
          f"pocs={out.get('n_poc')} base={(out.get('base') or '—')[:12]}",
          flush=True)


def _prepare(args) -> tuple[list[bugmod.Bug], Path]:
    cands = _load(args)
    bugs = bugmod.load_group(cands, args.project, getattr(args, "harness", None))
    if not bugs:
        raise SystemExit(f"no core bugs for {args.project}/{getattr(args, 'harness', None)}")
    pocs = Path(getattr(args, "pocs", "/tmp/memvul/pocs"))
    bugmod.attach_pocs(bugs, pocs)
    repo_url = getattr(args, "repo", None) or next(b.repo for b in bugs if b.repo)
    repo = clone(repo_url, args.project)
    bugmod.resolve_fixes(repo, bugs)
    return bugs, repo


def _sweep_path(args) -> Path:
    if getattr(args, "sweep", None):
        return Path(args.sweep)
    return SWEEPS / f"{args.project}_{args.harness or 'all'}.json"


def cmd_base(args) -> None:
    bugs, repo = _prepare(args)
    sw = sweep.load(_sweep_path(args))
    if sw is None:
        raise SystemExit("provide a manually recorded sweep JSON with --sweep")
    sweep.attach_windows(bugs, sw)
    probe_cands = [(p["sha"], p["date"]) for p in sw.probes if p.get("status") == "ok"]
    extra = basepick.candidates_from_windows(bugs)
    # Prefer actually-built probes; they are the only commits we *know* compile.
    pool = probe_cands or extra
    ranked = basepick.rank(bugs, pool, n=args.limit)
    print(f"{'base':<14}{'date':<12}{'latent':>8}{'mosaic':>8}{'unk':>6}")
    print("-" * 48)
    import datetime as _dt
    for s in ranked:
        day = _dt.date.fromtimestamp(s.date).isoformat()
        print(f"{s.sha[:12]:<14}{day:<12}{s.n_latent:8d}{len(s.mosaic):8d}"
              f"{len(s.unknown):6d}")
    out = SWEEPS / f"{args.project}_{args.harness or 'all'}_bases.json"
    out.write_text(json.dumps([s.to_dict() for s in ranked], indent=1))
    print(f"\nwrote {out.relative_to(ROOT)}")
    if ranked:
        print(f"pick: {ranked[0].sha}  latent={ranked[0].n_latent}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="memvul")
    p.add_argument("--db", default=str(arvo.DEFAULT_DB), help="ARVO-Meta sqlite")
    p.add_argument("--refresh", action="store_true", help="re-parse the db")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("census", help="classify the whole ARVO corpus")
    c.set_defaults(func=cmd_census)

    s = sub.add_parser("slices", help="rank candidate benchmark slices")
    s.add_argument("--by", choices=("harness", "project"), default="harness")
    s.add_argument("--min-sites", type=int, default=8)
    s.add_argument("--limit", type=int, default=30)
    s.add_argument("--labels", action="store_true")
    s.set_defaults(func=cmd_slices)

    f = sub.add_parser("fetch", help="pull PoCs from ARVO images via the registry")
    f.add_argument("ids", nargs="*", type=int)
    f.add_argument("--dest", default="/tmp/memvul/pocs")
    f.add_argument("--binary", action="store_true",
                   help="also save the prebuilt reference ASan harness")
    f.add_argument("--refresh", action="store_true")
    f.set_defaults(func=cmd_fetch)

    cand = sub.add_parser("candidates",
                          help="fix-date waves → archaeological candidate bases")
    cand.add_argument("--project", required=True)
    cand.add_argument("--harness")
    cand.add_argument("--repo")
    cand.add_argument("--pocs", default="/tmp/memvul/pocs")
    cand.add_argument("--min-wave", type=int, default=2)
    cand.add_argument("--limit", type=int, default=12)
    cand.set_defaults(func=cmd_candidates)

    cat = sub.add_parser("catalog",
                         help="walk every project with >N sites, write catalog/")
    cat.add_argument("--min-sites", type=int, default=10)
    cat.add_argument("--dest", default=str(catalog.CATALOG))
    cat.add_argument("--only", nargs="*", help="restrict to these project names")
    cat.set_defaults(func=cmd_catalog)

    m = sub.add_parser("measure",
                       help="fetch PoCs + load one ARVO builder; compile/replay are manual")
    m.add_argument("--project", help="measure this project (repeatable via --queue)")
    m.add_argument("--queue", action="store_true",
                   help="continue with the next unmeasured projects")
    m.add_argument("--limit", type=int, default=0,
                   help="how many projects to run; 0 = all remaining")
    m.add_argument("--min-sites", type=int, default=10)
    m.add_argument("--min-latent", type=int, default=8,
                   help="skip catalog targets whose n_latent is below this")
    m.set_defaults(func=cmd_measure)

    b = sub.add_parser("base", help="rank bases by how many measured windows they stab")
    b.add_argument("--project", required=True)
    b.add_argument("--harness")
    b.add_argument("--repo")
    b.add_argument("--pocs", default="/tmp/memvul/pocs")
    b.add_argument("--sweep", help="path to a sweep JSON")
    b.add_argument("--limit", type=int, default=12)
    b.set_defaults(func=cmd_base)

    args = p.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
