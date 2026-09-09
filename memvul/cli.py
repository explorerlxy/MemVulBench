"""MemVulBench command line entry point."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from . import arvo, basepick, bug as bugmod, emit, fetch, pin, reintroduce
from . import select, slice as slmod, sweep, verify
from .gitutil import clone

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "census"
SWEEPS = ROOT / "data" / "sweeps"
PINS = ROOT / "data" / "pins"
SLICES = ROOT / "data" / "slices"


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


def _annotate_and_store(sw: sweep.Sweep, bugs: list[bugmod.Bug],
                        probe: sweep.Probe, shots: dict[str, sweep.Shot],
                        status: str) -> None:
    sweep.annotate_matches(bugs, shots)
    sw.matrix[probe.sha] = {oid: {
        "verdict": s.verdict, "kind": s.kind,
        "signature": s.signature, "match": s.match,
    } for oid, s in shots.items()}
    rec = {"sha": probe.sha, "date": probe.date, "reason": probe.reason,
           "status": status, "n_live": sum(1 for s in shots.values() if s.match)}
    sw.probes = [p for p in sw.probes if p["sha"] != probe.sha] + [rec]


def cmd_sweep(args) -> None:
    bugs, repo = _prepare(args)
    out = _sweep_path(args)
    sw = sweep.load(out)
    if sw is None:
        sw = sweep.Sweep(
            project=args.project, harness=args.harness,
            repo=next(b.repo for b in bugs if b.repo) or "",
            srcdir=args.srcdir, container=args.container,
            bugs=[{"oss_id": b.oss_id, "label": b.label,
                   "signature": list(b.signature or []),
                   "fix": b.fix_resolved, "fix_date": b.fix_date,
                   "arvo_vuln": b.arvo_vuln, "has_poc": bool(b.poc)}
                  for b in bugs],
        )
    probes = sweep.propose_probes(repo, bugs, every_days=args.every_days)
    if args.mode == "refine" and sw.matrix:
        matrix_shots = {
            sha: {oid: sweep._as_shot(s) for oid, s in row.items()}
            for sha, row in sw.matrix.items()
        }
        probes = probes + sweep.propose_refine(
            repo, bugs,
            [sweep.Probe(p["sha"], p["date"], p.get("reason", "")) for p in sw.probes],
            matrix_shots,
        )
    if args.max_probes:
        probes = probes[:args.max_probes]
    print(f"{args.project}/{args.harness}: {len(bugs)} sites, "
          f"{sum(1 for b in bugs if b.poc)} PoCs, {len(probes)} probes",
          flush=True)
    if args.dry_run:
        for p in probes:
            day = __import__("datetime").date.fromtimestamp(p.date).isoformat()
            print(f"  {p.short}  {day}  {p.reason}")
        return

    if args.container:
        n = sweep.sync_pocs(args.container, Path(args.pocs))
        if n:
            print(f"synced {n} PoCs into {args.container}", flush=True)
        sweep.install_scripts(args.container, ROOT)

    done = {p["sha"] for p in sw.probes if p.get("status") in ("ok", "fail")}
    for i, probe in enumerate(probes, 1):
        if probe.sha in done and not args.refresh:
            print(f"[{i}/{len(probes)}] {probe.short} cached", flush=True)
            continue
        if not args.container:
            print(f"[{i}/{len(probes)}] {probe.short} SKIP (no --container)",
                  flush=True)
            continue
        print(f"[{i}/{len(probes)}] {probe.short} {probe.reason} ...",
              flush=True)
        harness = args.harness or bugs[0].harness or "fuzzer"
        try:
            shots = sweep.run_probe(args.container, probe.sha, args.srcdir,
                                    harness, timeout=args.timeout)
            status = "fail" if not shots and _probe_failed(args.container, probe.sha) else "ok"
            if status == "fail":
                print(f"    BUILD_FAIL", flush=True)
            else:
                sweep.annotate_matches(bugs, shots)
                print(f"    live={sum(1 for s in shots.values() if s.match)}"
                      f"/{len(shots)}", flush=True)
            _annotate_and_store(sw, bugs, probe, shots, status)
        except Exception as e:  # noqa: BLE001
            print(f"    ERROR {type(e).__name__}: {e}", flush=True)
            _annotate_and_store(sw, bugs, probe, {}, "error")
        sweep.save(sw, out)

    all_probes = [sweep.Probe(p["sha"], p["date"], p.get("reason", ""))
                  for p in sw.probes]
    sweep.reconstruct(bugs, all_probes or probes, sw.matrix)
    sw.windows = {str(b.oss_id): (b.window.to_dict() if b.window else None)
                  for b in bugs}
    sweep.save(sw, out)
    measured = sum(1 for b in bugs if b.window)
    print(f"\nwindows measured: {measured}/{len(bugs)}")
    print(f"wrote {out.relative_to(ROOT)}")


def _probe_failed(container: str, sha: str) -> bool:
    p = sweep.docker("exec", container, "cat", f"/reports/sweep/{sha}/status")
    return "BUILD_FAIL" in p.stdout


def cmd_base(args) -> None:
    bugs, repo = _prepare(args)
    sw = sweep.load(_sweep_path(args))
    if sw is None:
        raise SystemExit("run `memvul sweep` first")
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


def cmd_pin(args) -> None:
    bugs, repo = _prepare(args)
    sw = sweep.load(_sweep_path(args))
    if sw is None:
        raise SystemExit("run `memvul sweep` first")
    sweep.attach_windows(bugs, sw)
    base = args.base
    if not base:
        probe_cands = [(p["sha"], p["date"]) for p in sw.probes
                       if p.get("status") == "ok"]
        ranked = basepick.rank(bugs, probe_cands, n=1)
        if not ranked:
            raise SystemExit("no scored base; pass --base")
        base = ranked[0].sha
        print(f"using best base {base[:12]} (latent={ranked[0].n_latent})")
    dates = {p["sha"]: p["date"] for p in sw.probes}
    plan = pin.plan(repo, bugs, base, dates)
    print(f"base {plan.base[:12]}")
    print(f"  latent {len(plan.latent)}  mosaic {len(plan.mosaic)}  "
          f"rejected {len(plan.rejected)}")
    print(f"  file pins {len(plan.pins)}  "
          f"function-pin candidates {len(plan.function_pin_candidates)}")
    if plan.rejected:
        from collections import Counter
        print("  rejects:", dict(Counter(plan.rejected.values())))
    out = PINS / f"{args.project}_{args.harness or 'all'}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan.to_dict(), indent=1))
    print(f"wrote {out.relative_to(ROOT)}")


def cmd_slice(args) -> None:
    bugs, repo = _prepare(args)
    pin_path = Path(args.pin) if args.pin else PINS / f"{args.project}_{args.harness or 'all'}.json"
    raw = json.loads(pin_path.read_text())
    sw = sweep.load(_sweep_path(args))
    if sw:
        sweep.attach_windows(bugs, sw)
    # Recompute claims so the slice graph matches the pin plan.
    plan = pin.PinPlan(
        project=raw["project"], harness=raw.get("harness"),
        base=raw["base"], base_date=raw["base_date"],
        latent=raw.get("latent", []), mosaic=raw.get("mosaic", []),
        rejected=raw.get("rejected", {}),
        pins=[pin.FilePin(**p) for p in raw.get("pins", [])],
        function_pin_candidates=raw.get("function_pin_candidates", []),
    )
    for b in bugs:
        if str(b.oss_id) in plan.rejected:
            b.reject = plan.rejected[str(b.oss_id)]
        elif not b.claim and b.fix_resolved and not b.reject:
            b.claim = pin.claim_e0(repo, b)
    slices = slmod.partition(bugs, plan)
    print(f"{len(slices)} slices from {pin_path.name}")
    for s in slices:
        print(f"  {s.name}: {s.purity} {s.kind}  bugs={len(s.bugs)}  "
              f"pins={s.mosaic_files}  dropped={len(s.dropped)}")
    dest = SLICES / f"{args.project}_{args.harness or 'all'}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps([s.to_dict() for s in slices], indent=1))
    print(f"wrote {dest.relative_to(ROOT)}")


def cmd_emit(args) -> None:
    bugs, repo = _prepare(args)
    bundle = json.loads(Path(args.slice_json).read_text())
    slices = [slmod.Slice.from_dict(s) for s in (bundle if isinstance(bundle, list) else [bundle])]
    sl = slices[args.index]
    dest = Path(args.dest) if args.dest else Path("/tmp/memvul/trees") / sl.name
    # Apply on the host clone, then the caller can rsync. Manifest is the
    # source of truth; the worktree is a convenience.
    enabled = set(int(x) for x in args.enable.split(",")) if args.enable else None
    emit.apply(repo, sl.base, sl.pins, enabled)
    fails = emit.fidelity(repo, sl.base, sl.pins, enabled)
    stats = emit.mosaic_stats(repo, sl.base, sl.pins)
    dest.mkdir(parents=True, exist_ok=True)
    emit.write_manifest(sl, dest / "pins.yaml", extra={"mosaic": stats,
                                                       "fidelity_fail": fails})
    emit.write_toggles(sl, dest / "toggles.cmake")
    print(f"{sl.name}: mosaic_ratio={stats['mosaic_ratio']} "
          f"pinned={stats['files_pinned']}/{stats['source_files']}")
    print(f"fidelity failures: {len(fails)}")
    print(f"wrote {dest}")


def cmd_verify(args) -> None:
    bugs, repo = _prepare(args)
    bundle = json.loads(Path(args.slice_json).read_text())
    slices = [slmod.Slice.from_dict(s) for s in (bundle if isinstance(bundle, list) else [bundle])]
    sl = slices[args.index]
    results = verify.verify_slice(
        repo, sl, bugs, container=args.container,
        srcdir=args.srcdir, harness=args.harness or bugs[0].harness or "fuzzer",
        expand=not args.no_expand,
    )
    admitted = sum(1 for r in results if r.status == "admitted")
    print(f"{sl.name}: {admitted}/{len(results)} admitted")
    from collections import Counter
    reasons = Counter(r.reject_reason for r in results if r.reject_reason)
    if reasons:
        print("rejects:", dict(reasons))
    out = SLICES / f"{sl.name}_verify.json"
    out.write_text(json.dumps([r.to_dict() for r in results], indent=1))
    print(f"wrote {out.relative_to(ROOT)}")


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

    for name, help_, fn in (
        ("sweep", "measure observability windows by building + replaying", cmd_sweep),
        ("base", "rank bases by how many measured windows they stab", cmd_base),
        ("pin", "solve claim sets and vul/fix pin pairs", cmd_pin),
        ("slice", "carve pin plans into conflict-free slices", cmd_slice),
        ("emit", "materialise a slice (checkout + pin + manifest)", cmd_emit),
        ("verify", "run admission gates 1–6 on a slice", cmd_verify),
    ):
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("--project", required=True)
        sp.add_argument("--harness")
        sp.add_argument("--repo")
        sp.add_argument("--pocs", default="/tmp/memvul/pocs")
        sp.add_argument("--sweep", help="path to a sweep JSON")
        if name == "sweep":
            sp.add_argument("--container")
            sp.add_argument("--srcdir", default="/src/assimp")
            sp.add_argument("--every-days", type=int, default=40)
            sp.add_argument("--mode", choices=("coarse", "refine"), default="coarse")
            sp.add_argument("--max-probes", type=int)
            sp.add_argument("--timeout", type=int, default=1200)
            sp.add_argument("--dry-run", action="store_true")
        if name == "base":
            sp.add_argument("--limit", type=int, default=12)
        if name == "pin":
            sp.add_argument("--base", help="base commit; default = best from sweep")
        if name == "slice":
            sp.add_argument("--pin", help="path to a pin-plan JSON")
        if name in ("emit", "verify"):
            sp.add_argument("--slice-json", required=True, dest="slice_json")
            sp.add_argument("--index", type=int, default=0)
        if name == "emit":
            sp.add_argument("--dest")
            sp.add_argument("--enable", help="comma-separated oss_ids to turn ON")
        if name == "verify":
            sp.add_argument("--container")
            sp.add_argument("--srcdir", default="/src/assimp")
            sp.add_argument("--no-expand", action="store_true")
        sp.set_defaults(func=fn)

    args = p.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
