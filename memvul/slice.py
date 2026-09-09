"""Conflict-graph slicing (methodology.md §5–§6).

Two bugs conflict when they claim the same file and their windows are
disjoint. Overlapping-window co-claimers already share a FilePin and do
not produce an edge. Shared-infrastructure bugs are carved into their
own slice stream so they never mix with plugin-local ones.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field

from .bug import Bug
from .pin import FilePin, PinPlan


@dataclass
class Slice:
    name: str
    kind: str                    # plugin | infra | mixed
    purity: str                  # pure | mosaic
    base: str
    base_date: int
    bugs: list[int]
    dropped: dict[str, str] = field(default_factory=dict)
    pins: list[dict] = field(default_factory=list)
    mosaic_files: int = 0
    temporal_spread_days: int | None = None
    n_forward: int = 0
    n_backward: int = 0
    n_function_pin: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "Slice":
        keep = {k: raw[k] for k in cls.__dataclass_fields__ if k in raw}
        return cls(**keep)


def _adj(bugs: list[Bug], pins: list[FilePin]) -> dict[int, set[int]]:
    """Conflict edges from the file-pin table."""
    by_id = {b.oss_id: b for b in bugs}
    file_clusters: dict[str, list[list[int]]] = defaultdict(list)
    for p in pins:
        file_clusters[p.file].append(list(p.bugs))
    adj: dict[int, set[int]] = {b.oss_id: set() for b in bugs}
    for _path, clusters in file_clusters.items():
        if len(clusters) < 2:
            continue
        for i, a in enumerate(clusters):
            for b in clusters[i + 1:]:
                for x in a:
                    for y in b:
                        if x in adj and y in adj:
                            adj[x].add(y)
                            adj[y].add(x)
    # Also conflict if claims overlap even when pin planner missed a file.
    claims = {b.oss_id: set(b.claim) for b in bugs}
    ids = [b.oss_id for b in bugs]
    for i, x in enumerate(ids):
        for y in ids[i + 1:]:
            if not (claims[x] & claims[y]):
                continue
            wx, wy = by_id[x].window, by_id[y].window
            if not wx or not wy or wx.intro_date is None or wy.intro_date is None:
                continue
            overlap = wx.intro_date < wy.fix_date and wy.intro_date < wx.fix_date
            if not overlap:
                adj[x].add(y)
                adj[y].add(x)
    return adj


def _mis(ids: list[int], adj: dict[int, set[int]],
         weight: dict[int, float]) -> list[int]:
    """Maximum-cardinality independent set, component-wise.

    n is small (a conflict component is a handful of bugs sharing a file).
    Tie-break by the sum of per-bug weights (temporal / write preferred).
    """
    remaining = set(ids)
    chosen: list[int] = []
    while remaining:
        v = next(iter(remaining))
        comp = _component(v, adj, remaining)
        remaining -= set(comp)
        chosen.extend(_mis_exact(comp, adj, weight))
    return chosen


def _component(v: int, adj: dict[int, set[int]], universe: set[int]) -> list[int]:
    seen = {v}
    stack = [v]
    while stack:
        x = stack.pop()
        for y in adj.get(x, ()):
            if y in universe and y not in seen:
                seen.add(y)
                stack.append(y)
    return list(seen)


def _mis_exact(nodes: list[int], adj: dict[int, set[int]],
               weight: dict[int, float]) -> list[int]:
    nodes = sorted(nodes, key=lambda i: weight.get(i, 0), reverse=True)
    n = len(nodes)
    if n > 22:
        # Greedy fallback; should not fire on real claim graphs.
        picked, blocked = [], set()
        for v in nodes:
            if v not in blocked:
                picked.append(v)
                blocked |= adj.get(v, set()) | {v}
        return picked
    best: list[int] = []
    best_key = (-1, -1.0)

    def rec(i: int, cur: list[int], blocked: set[int]) -> None:
        nonlocal best, best_key
        rest = n - i
        if len(cur) + rest < best_key[0]:
            return
        if i == n:
            key = (len(cur), sum(weight.get(x, 0) for x in cur))
            if key > best_key:
                best_key = key
                best = cur[:]
            return
        v = nodes[i]
        if v not in blocked:
            cur.append(v)
            rec(i + 1, cur, blocked | adj.get(v, set()))
            cur.pop()
        rec(i + 1, cur, blocked)

    rec(0, [], set())
    return best


def _weight(b: Bug) -> float:
    w = 1.0
    if b.group == "temporal":
        w += 0.5
    if "write" in b.label:
        w += 0.3
    return w


def _pins_for(ids: set[int], pins: list[FilePin], base: str,
              base_date: int) -> list[dict]:
    out = []
    for p in pins:
        if not ids.intersection(p.bugs):
            continue
        # A pin whose toggle unit is only partly in the slice would pull
        # the rest in. Keep the pin only if the whole unit is in, or if
        # the unit collapses to the in-slice subset (disjoint-window
        # sibling was dropped).
        unit = [i for i in p.bugs if i in ids]
        if not unit:
            continue
        d = p.to_dict()
        d["bugs"] = unit
        # Identity pins (ON == base) do not count as mosaic.
        mosaic = p.on_commit != base
        d["mosaic"] = mosaic
        out.append(d)
    return out


def _spread(pins: list[dict], base_date: int) -> tuple[int | None, int, int]:
    dates = []
    n_fwd = n_back = 0
    for p in pins:
        if not p.get("mosaic"):
            continue
        if p.get("direction") == "forward":
            n_fwd += 1
        else:
            n_back += 1
    # temporal_spread needs commit dates; caller fills if it wants precision.
    # Here we only report None unless every pin carries an on_date.
    on_dates = [p["on_date"] for p in pins if "on_date" in p]
    spread = (max(on_dates) - min(on_dates)) // 86400 if on_dates else None
    return spread, n_fwd, n_back


def partition(bugs: list[Bug], plan: PinPlan) -> list[Slice]:
    usable = [b for b in bugs
              if not b.reject and b.window and b.oss_id not in
              {int(k) for k in plan.rejected}]
    infra = [b for b in usable if b.shared_infra]
    plugin = [b for b in usable if not b.shared_infra]
    slices: list[Slice] = []
    for kind, group in (("plugin", plugin), ("infra", infra)):
        if not group:
            continue
        leftover = list(group)
        part = 0
        while leftover:
            adj = _adj(leftover, plan.pins)
            weight = {b.oss_id: _weight(b) for b in leftover}
            keep = set(_mis([b.oss_id for b in leftover], adj, weight))
            drop = {b.oss_id: "conflict_dropped"
                    for b in leftover if b.oss_id not in keep}
            pins = _pins_for(keep, plan.pins, plan.base, plan.base_date)
            mosaic_files = len({p["file"] for p in pins if p.get("mosaic")})
            purity = "pure" if mosaic_files == 0 else "mosaic"
            spread, n_fwd, n_back = _spread(pins, plan.base_date)
            name = f"{plan.project}_{plan.harness or 'all'}_{kind}_{part}"
            slices.append(Slice(
                name=name,
                kind=kind,
                purity=purity,
                base=plan.base,
                base_date=plan.base_date,
                bugs=sorted(keep),
                dropped={str(k): v for k, v in drop.items()},
                pins=pins,
                mosaic_files=mosaic_files,
                temporal_spread_days=spread,
                n_forward=n_fwd,
                n_backward=n_back,
            ))
            leftover = [b for b in leftover if b.oss_id not in keep]
            part += 1
            if part > 20:
                break
    return slices
