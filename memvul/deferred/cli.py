"""Standalone entry for deferred pin / slice / emit. Not on python3 -m memvul."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from .. import arvo, basepick, sweep
from ..cli import ROOT, _prepare, _sweep_path
from . import emit, pin, slice as slmod

PINS = ROOT / "data" / "pins"
SLICES = ROOT / "data" / "slices"


def cmd_pin(args) -> None:
    bugs, repo = _prepare(args)
    sw = sweep.load(_sweep_path(args))
    if sw is None:
        raise SystemExit("provide a manually recorded sweep JSON with --sweep")
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
    _bugs, repo = _prepare(args)
    bundle = json.loads(Path(args.slice_json).read_text())
    slices = [slmod.Slice.from_dict(s) for s in (bundle if isinstance(bundle, list) else [bundle])]
    sl = slices[args.index]
    dest = Path(args.dest) if args.dest else Path("/tmp/memvul/trees") / sl.name
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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="memvul.deferred")
    p.add_argument("--db", default=str(arvo.DEFAULT_DB), help="ARVO-Meta sqlite")
    p.add_argument("--refresh", action="store_true", help="re-parse the db")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, help_, fn in (
        ("pin", "solve claim sets and vul/fix pin pairs", cmd_pin),
        ("slice", "carve pin plans into conflict-free slices", cmd_slice),
        ("emit", "materialise a slice", cmd_emit),
    ):
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("--project", required=True)
        sp.add_argument("--harness")
        sp.add_argument("--repo")
        sp.add_argument("--pocs", default="/tmp/memvul/pocs")
        sp.add_argument("--sweep", help="path to a sweep JSON")
        if name == "pin":
            sp.add_argument("--base", help="base commit; default = best from sweep")
        if name == "slice":
            sp.add_argument("--pin", help="path to a pin-plan JSON")
        if name == "emit":
            sp.add_argument("--slice-json", required=True, dest="slice_json")
            sp.add_argument("--index", type=int, default=0)
            sp.add_argument("--dest")
            sp.add_argument("--enable", help="comma-separated oss_ids to turn ON")
        sp.set_defaults(func=fn)
    args = p.parse_args(argv)
    args.func(args)
    return 0
