"""MemVulBench command line entry point."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from . import arvo, fetch, reintroduce, select

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "census"


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
    head = f"{'score':>6} {'sites':>5} {'issues':>6} {'dup':>5} {'temp':>5} {'wr':>4}  target"
    print(head)
    print("-" * (len(head) + 24))
    for g in groups[:limit]:
        name = g.key if g.harness else g.project
        print(f"{g.score():6.1f} {g.n_sites:5d} {len(g.buildable):6d} "
              f"{g.dup_ratio:4.0%} {g.n_temporal:5d} {g.n_write:4d}  {name}")
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
            "labels": dict(g.labels),
            "oss_ids": [c.oss_id for c in g.buildable],
        }
        for g in groups
    ], indent=1))
    print(f"wrote {out.relative_to(ROOT)}")


def cmd_plan(args) -> None:
    cands = _load(args)
    bugs = [c for c in cands
            if c.tier == "core" and c.buildable and c.project == args.project
            and (args.harness is None or c.harness == args.harness)]
    if not bugs:
        raise SystemExit(f"no core bugs for {args.project}/{args.harness}")
    repo_url = args.repo or next(c.repo for c in bugs if c.repo)

    # One bug per crash site: duplicates cost build effort and buy nothing.
    seen: set[str] = set()
    refs: list[reintroduce.BugRef] = []
    for c in sorted(bugs, key=lambda c: c.oss_id):
        if c.site_key in seen:
            continue
        seen.add(c.site_key)
        refs.append(reintroduce.BugRef(c.oss_id, c.fix_commit or "", c.label))

    print(f"{args.project}/{args.harness}: {len(bugs)} issues -> "
          f"{len(refs)} distinct crash sites")
    print(f"cloning {repo_url} ...", flush=True)
    res = reintroduce.plan_group(args.project, args.harness, repo_url, refs,
                                 n_bases=args.bases, window_days=args.window)

    print(f"fix commits resolved: {res['n_resolved']}/{res['n_bugs']}"
          f"  (missing {res['n_missing_commit']}), "
          f"intro estimated for {res['n_intro_estimated']}\n")
    hdr = (f"{'base':<14}{'date':<12}{'present':>8}{'unk':>5}{'notyet':>7}"
           f"{'rev-ok':>7}{'confl':>6}{'stack':>6}{'CAND':>6}")
    print(hdr)
    print("-" * len(hdr))
    import datetime as _dt
    for b in res["bases"]:
        day = _dt.date.fromtimestamp(b["base_date"]).isoformat()
        print(f"{b['base']:<14}{day:<12}{b['present']:>8}{b['intro_unknown']:>5}"
              f"{b['not_yet']:>7}{b['revert_ok']:>7}{b['revert_conflict']:>6}"
              f"{b['stacked']:>6}{b['candidates']:>6}")

    out = DATA.parent / "plans" / f"{args.project}_{args.harness or 'all'}.json"
    reintroduce.save(res, out)
    print(f"\nwrote {out.relative_to(ROOT)}")
    print("present = fix not landed and defect already introduced (SZZ estimate); "
          "stack = revert applies on top of the others.\n"
          "CAND = present + unk + stack, an upper bound. PoC replay and the "
          "negative control decide admission.")


def cmd_fetch(args) -> None:
    root = Path(args.dest)
    ids = args.ids
    if args.plan:
        plan = json.loads(Path(args.plan).read_text())
        best = plan["bases"][0]
        ids = sorted(best["ids"]["present"] + best["ids"]["stacked"])
        print(f"base {best['base']}: {len(ids)} bugs from {args.plan}")

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

    q = sub.add_parser("plan", help="find the best base commit for a slice")
    q.add_argument("--project", required=True)
    q.add_argument("--harness")
    q.add_argument("--repo", help="override the repo URL from ARVO")
    q.add_argument("--bases", type=int, default=12)
    q.add_argument("--window", type=int, default=730,
                   help="max age in days of a fix still worth reverting")
    q.set_defaults(func=cmd_plan)

    f = sub.add_parser("fetch", help="pull PoCs from ARVO images via the registry")
    f.add_argument("ids", nargs="*", type=int)
    f.add_argument("--plan", help="take the bug list from a plan JSON's best base")
    f.add_argument("--dest", default="/tmp/memvul/pocs")
    f.add_argument("--binary", action="store_true",
                   help="also save the prebuilt reference ASan harness")
    f.add_argument("--refresh", action="store_true")
    f.set_defaults(func=cmd_fetch)

    args = p.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
