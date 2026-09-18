"""Plot Chinese manuscript figures from admitted first-fault fingerprints.

Reads recorded evidence only; never builds targets or executes PoCs.
"""
from __future__ import annotations

import csv
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/memvul-paper-mpl")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

PAPER = Path(__file__).resolve().parents[1]
ROOT = PAPER.parents[1]
OUTPUT = PAPER / "figures" / "zh"
KNOWN = {"expected_asan", "expected_crash", "known_real"}
BLUE, ORANGE, GRAY = "#356F99", "#D18A2D", "#8D99A6"
GRID, INK = "#DDE3E8", "#253746"
fig_width_mm = 160  # full-width artwork within the journal's A4 text block
KIND_ZH = {
    "heap-buffer-overflow": "堆缓冲区越界",
    "stack-buffer-overflow": "栈缓冲区越界",
    "heap-use-after-free": "堆释放后使用",
    "global-buffer-overflow": "全局缓冲区越界",
    "negative-size-param": "负长度参数",
    "memcpy-param-overlap": "重叠内存复制",
    "stack-buffer-underflow": "栈缓冲区下溢",
    "double-free": "重复释放",
    "container-overflow": "容器边界越界",
    "null-deref": "空指针解引用",
    "stack-use-after-return": "栈返回后使用",
    "stack-use-after-scope": "栈作用域结束后使用",
}


def load_data() -> tuple[list[dict], list[dict]]:
    admission = json.loads((ROOT / "data/measure/admission/2026-09-18.json").read_text())
    ledger = json.loads((PAPER / "evidence/rereplay_fingerprint_ledger.json").read_text())
    arrow = json.loads((ROOT / "data/measure/rereplay/2026-09-18/arrow.json").read_text())
    units = {unit["project"]: unit for unit in admission["units"]}
    assert len(units) == 20 and "arrow" in units and "librawspeed" not in units
    unique = {}

    def add(project: str, key: str, kind: str, access: str, verdict: str) -> None:
        row = {"project": project, "fingerprint_key": key, "kind": kind,
               "access": access, "origin": "extra" if verdict == "known_real" else "expected"}
        old = unique.get((project, key))
        if old:
            assert (old["kind"], old["access"]) == (kind, access)
            if old["origin"] == "expected":
                return
        unique[(project, key)] = row

    for obs in ledger["observations"]:
        if obs["project"] not in units or obs["project"] == "arrow" or obs.get("verdict") not in KNOWN:
            continue
        fp = obs.get("fingerprint") or {}
        if fp.get("key"):
            add(obs["project"], fp["key"], fp["kind"], fp["access"], obs["verdict"])
    for obs in arrow["observations"]:
        if obs.get("verdict") in KNOWN:
            kind, access, *_ = obs["key"].split("|")
            add("arrow", obs["key"], kind, access, obs["verdict"])

    rows = sorted(unique.values(), key=lambda r: (r["project"].lower(), r["fingerprint_key"]))
    assert len(rows) == admission["verified_memory_bug_count"] == 292
    assert {r["kind"] for r in rows} == set(KIND_ZH)
    assert {r["access"] for r in rows} <= {"READ", "WRITE", "-"}
    by_unit = defaultdict(Counter)
    for row in rows:
        by_unit[row["project"]][row["origin"]] += 1
    for project, unit in units.items():
        got = by_unit[project]
        assert got["expected"] == unit["expected_five_tuples"], project
        assert got["extra"] == unit["extra_five_tuples"], project
        assert sum(got.values()) == unit["verified_memory_bug_count"], project
    assert sum(r["origin"] == "expected" for r in rows) == admission["unique_expected_five_tuples"]
    assert sum(r["origin"] == "extra" for r in rows) == admission["unique_extra_five_tuples_outside_expected"]
    return list(units.values()), rows


def write_source_data(units: list[dict], fingerprints: list[dict]) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT / "figure_fingerprints.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["project", "fingerprint_key", "kind", "access", "origin"])
        writer.writeheader()
        writer.writerows(fingerprints)
    with (OUTPUT / "figure_unit_counts.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["project", "expected", "extra", "total"])
        writer.writeheader()
        for unit in units:
            writer.writerow({"project": unit["project"], "expected": unit["expected_five_tuples"],
                             "extra": unit["extra_five_tuples"], "total": unit["verified_memory_bug_count"]})


def configure_plotting() -> None:
    font = Path("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf")
    if not font.exists():
        raise RuntimeError("DroidSansFallbackFull.ttf is required for Chinese labels")
    font_manager.fontManager.addfont(str(font))
    plt.rcParams.update({
        "font.family": ["DejaVu Sans", "Droid Sans Fallback"],
        "font.sans-serif": ["DejaVu Sans", "Droid Sans Fallback"],
        "font.size": 8.5,
        "text.color": INK, "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK,
        "axes.edgecolor": INK, "axes.spines.top": False, "axes.spines.right": False,
        "axes.linewidth": 0.6, "svg.fonttype": "none", "pdf.fonttype": 42,
        "savefig.facecolor": "white",
    })


def save(fig: plt.Figure, name: str) -> None:
    fig.savefig(OUTPUT / f"{name}.svg", metadata={"Date": None})
    fig.savefig(OUTPUT / f"{name}.pdf", metadata={"CreationDate": None, "ModDate": None})
    fig.savefig(OUTPUT / f"{name}.png", dpi=600)
    fig.savefig(OUTPUT / f"{name}.tiff", dpi=600, pil_kwargs={"compression": "tiff_lzw"})
    plt.close(fig)


def finish_axis(ax: plt.Axes, xlabel: str) -> None:
    ax.set_xlabel(xlabel, fontsize=8.5)
    ax.tick_params(axis="both", length=0, labelsize=8)
    ax.tick_params(axis="y", pad=5)
    ax.xaxis.grid(True, color=GRID, linewidth=0.55)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color(GRID)


def plot_units(units: list[dict]) -> None:
    rows = sorted(units, key=lambda r: (-r["verified_memory_bug_count"], r["project"].lower()))
    fig, ax = plt.subplots(figsize=(fig_width_mm / 25.4, 111 / 25.4))
    fig.subplots_adjust(left=0.22, right=0.94, top=0.87, bottom=0.11)
    y = list(range(len(rows)))
    expected = [r["expected_five_tuples"] for r in rows]
    extra = [r["extra_five_tuples"] for r in rows]
    total = [r["verified_memory_bug_count"] for r in rows]
    ax.barh(y, expected, height=0.72, color=BLUE)
    ax.barh(y, extra, left=expected, height=0.72, color=ORANGE)
    ax.axvline(8, color=GRAY, linestyle=(0, (3, 2)), linewidth=0.9, zorder=0)
    for yi, value in zip(y, total):
        ax.text(value + 0.45, yi, str(value), va="center", fontsize=8)
    ax.set_yticks(y, [r["project"] for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 39)
    ax.set_xticks([0, 8, 16, 24, 32])
    finish_axis(ax, "每单元已核验唯一漏洞指纹数")
    handles = [Patch(facecolor=BLUE, label="目录关联"), Patch(facecolor=ORANGE, label="目录外已审核"),
               Line2D([0], [0], color=GRAY, linestyle=(0, (3, 2)), linewidth=0.9, label="准入门槛 8")]
    fig.legend(handles=handles, loc="upper right", bbox_to_anchor=(0.94, 0.97),
               ncol=3, frameon=False, fontsize=8, handlelength=1.4, columnspacing=1.5)
    save(fig, "fig1_unit_counts_zh")


def plot_types(fingerprints: list[dict]) -> None:
    counts = defaultdict(Counter)
    for row in fingerprints:
        counts[row["kind"]][row["access"]] += 1
    kinds = sorted(KIND_ZH, key=lambda kind: (-sum(counts[kind].values()), KIND_ZH[kind]))
    fig, ax = plt.subplots(figsize=(fig_width_mm / 25.4, 93 / 25.4))
    fig.subplots_adjust(left=0.31, right=0.95, top=0.84, bottom=0.13)
    y = list(range(len(kinds)))
    left = [0] * len(kinds)
    for access, color in (("READ", BLUE), ("WRITE", ORANGE), ("-", GRAY)):
        values = [counts[kind][access] for kind in kinds]
        ax.barh(y, values, left=left, height=0.67, color=color, edgecolor="white", linewidth=0.35)
        left = [a + b for a, b in zip(left, values)]
    for yi, value in zip(y, left):
        ax.text(value + 2.2, yi, str(value), va="center", fontsize=8)
    ax.set_yticks(y, [KIND_ZH[kind] for kind in kinds])
    ax.invert_yaxis()
    ax.set_xlim(0, 215)
    ax.set_xticks([0, 50, 100, 150, 200])
    finish_axis(ax, "已核验唯一漏洞指纹数")
    fig.legend(handles=[Patch(facecolor=BLUE, label="读"), Patch(facecolor=ORANGE, label="写"),
                        Patch(facecolor=GRAY, label="方向不适用")],
               loc="upper right", bbox_to_anchor=(0.95, 0.97), ncol=3,
               frameon=False, fontsize=8, handlelength=1.4, columnspacing=1.5)
    save(fig, "fig2_type_distribution_zh")


def main() -> None:
    units, fingerprints = load_data()
    write_source_data(units, fingerprints)
    configure_plotting()
    plot_units(units)
    plot_types(fingerprints)
    print(f"{len(units)} units; {len(fingerprints)} unique fingerprints; {len(KIND_ZH)} kinds")


if __name__ == "__main__":
    main()
