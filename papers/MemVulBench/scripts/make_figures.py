"""Draw publication figures from recorded metadata; never execute targets."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/memvul-paper-mpl")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Patch

PAPER = Path(__file__).resolve().parents[1]
FIGURES = PAPER / "figures"
BLUE, TEAL, ORANGE, GRAY = "#0072B2", "#009E73", "#D89000", "#52616B"


def save(fig: plt.Figure, name: str) -> None:
    for ext in ("svg", "pdf", "png"):
        kw = {"metadata": {"Date": None}} if ext == "svg" else {}
        if ext == "pdf":
            kw = {"metadata": {"CreationDate": None, "ModDate": None}}
        fig.savefig(FIGURES / f"{name}.{ext}", dpi=240, bbox_inches="tight", facecolor="white", **kw)
    plt.close(fig)


def box(ax: plt.Axes, x: float, y: float, w: float, h: float,
        title: str, detail: str, color: str = BLUE) -> None:
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.008,rounding_size=0.012",
                               linewidth=1.2, edgecolor=color, facecolor="#F7FAFC"))
    ax.text(x+w/2, y+h*.73, title, ha="center", va="center", weight="bold", fontsize=10.5, color=color)
    ax.text(x+w/2, y+h*.29, detail, ha="center", va="center", fontsize=9, linespacing=1.5)


def arrow(ax: plt.Axes, start: tuple, end: tuple, style: str = "-") -> None:
    ax.annotate("", xy=end, xytext=start,
                arrowprops={"arrowstyle": "->", "color": GRAY, "lw": 1.4, "linestyle": style})


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "svg.fonttype": "none", "svg.hashsalt": "memvulbench-r1", "pdf.fonttype": 42})
    summary = json.loads((PAPER / "evidence/summary.json").read_text())
    with (PAPER / "evidence/selected_projects.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    with (PAPER / "evidence/field_audit.csv").open() as handle:
        audit = {r["project"]: r for r in csv.DictReader(handle)}

    fig, ax = plt.subplots(figsize=(11.5, 6.7))
    ax.set(xlim=(0, 1), ylim=(0, 1)); ax.axis("off")
    ax.text(.5, .965, "Design goal: 20 real projects, one exposed harness per project",
            ha="center", weight="bold", fontsize=13)
    ax.text(.5, .865, r"Test unit: $U=(P,V,H)$     Campaign: $C=(F,S,U,T)$",
            ha="center", fontsize=15, color=BLUE)
    ax.text(.5, .81, "Program / revision / harness   |   Fuzzer / sanitizer / unit / time budget",
            ha="center", fontsize=9.5, color=GRAY)
    cards = [
        (.025, .485, "C1  Native programs and historical faults", "Preserve historical program context\nTrace candidate fault provenance", BLUE),
        (.535, .485, "C2  Scoring entries per test unit", "Count witnessed first-fault fingerprints\nInterpret within a fixed configuration", BLUE),
        (.025, .185, "C3  Input-level verification materials", "Inputs and reports: physical witnesses\nFingerprints: operational scoring identities", TEAL),
        (.535, .185, "C4  Fixed build and runtime environments", "Record sources, binaries and dependencies\nAudit image and replay evidence", TEAL),
    ]
    for x, y, title, detail, color in cards:
        box(ax, x, y, .44, .24, title, detail, color)
    ax.text(.5, .105, "Environment E is linked separately; repetitions R belong to the experiment design.",
            ha="center", fontsize=9.5, color=GRAY)
    ax.text(.5, .045, "All four criteria require evidence; quantity alone does not establish evaluation efficiency.",
            ha="center", fontsize=9, color=GRAY)
    save(fig, "fig1_overview")

    fig, ax = plt.subplots(figsize=(11.5, 6.7))
    ax.set(xlim=(0, 1), ylim=(0, 1)); ax.axis("off")
    ax.text(.5, .965, "Criteria → construction artifacts → verification",
            ha="center", weight="bold", fontsize=13)
    upper = [
        ("1  Source and type screen", "C1 + C2\nHistorical memory-bug candidates"),
        ("2  Select a common revision", "C1 + C2\nUpstream version and candidate set"),
        ("3  Replay and attribute", "C3\nPoCs, reports and identity evidence"),
    ]
    for i, (title, detail) in enumerate(upper):
        x = .02 + i * .335
        box(ax, x, .615, .285, .24, title, detail)
        if i < 2:
            arrow(ax, (x + .29, .735), (x + .325, .735))
    box(ax, .69, .27, .285, .24, "4  Organize one harness", "C2\nOriginal entry or prefix dispatcher")
    box(ax, .355, .27, .285, .24, "5  Link final witnesses", "C2 + C3\nBug / fingerprint / input / route")
    box(ax, .02, .27, .285, .24, "6  Preserve environments", "C4\nBuild and runtime image manifests", TEAL)
    arrow(ax, (.833, .605), (.833, .52))
    arrow(ax, (.68, .39), (.65, .39))
    arrow(ax, (.345, .39), (.315, .39))
    arrow(ax, (.163, .26), (.163, .19))
    ax.plot([.02, .98], [.18, .18], color="#CBD5DF", lw=1)
    for i, label in enumerate(["RQ1  Real provenance", "RQ2  Entries per unit", "RQ3  PoCs + identities", "RQ4  Image evidence"]):
        ax.text(.125 + i * .25, .125, label, ha="center", fontsize=9.5, color=TEAL, weight="bold")
    ax.text(.5, .045, "Verification reports both supporting evidence and gaps; recorded metadata is not a passed check.",
            ha="center", fontsize=9, color=GRAY)
    save(fig, "fig2_workflow")

    fig,(ax,route)=plt.subplots(1,2,figsize=(11.5,7.8),sharey=True,
                                gridspec_kw={"width_ratios":[4,1.45],"wspace":.10},layout="constrained")
    rev=rows[::-1]; y=list(range(len(rev)))
    expected=[int(r["recorded_expected_unique"]) for r in rev]
    extra=[int(r["recorded_known_real_unique"]) for r in rev]
    ax.barh(y,expected,color=BLUE,height=.68,label="Catalog-associated groups")
    ax.barh(y,extra,left=expected,color=ORANGE,hatch="///",height=.68,label="Extra reports (separate)")
    ax.set_yticks(y,[r["project"] for r in rev]);ax.set_xlim(0,39)
    for pos,e,k in zip(y,expected,extra):
        ax.text(e+k+.35,pos,f"{e}"+(f" + {k}" if k else ""),va="center",fontsize=9)
    ax.axvline(8,color=GRAY,lw=1,ls=":",label="Selection count threshold")
    ax.set_xlabel("Recorded groups per selected test unit")
    ax.set_title("a  Catalog-associated groups and extra reports",loc="left",fontsize=11,pad=13)
    ax.legend(loc="lower right",fontsize=8,frameon=False)
    routes=[int(r["aggregation_route_count"]) for r in rev]
    route.barh(y,routes,color=[TEAL if n==1 else BLUE for n in routes],height=.68)
    for pos,n in zip(y,routes):route.text(n+.18,pos,str(n),va="center",fontsize=9)
    route.set_xlim(0,12);route.set_xticks([1,3,6,10]);route.set_xlabel("Recorded routes")
    route.set_title("b  Interface organization",loc="left",fontsize=11,pad=13)
    route.tick_params(axis="y",left=False,labelleft=False)
    route.legend(handles=[Patch(color=TEAL,label="Identity (9)"),Patch(color=BLUE,label="Prefix (11)")],
                 loc="lower right",fontsize=8,frameon=False)
    for a in (ax,route):a.xaxis.grid(True,alpha=.15);a.set_axisbelow(True)
    save(fig,"fig3_groups_routes")

    fig,ax=plt.subplots(figsize=(11.5,7.4),layout="constrained")
    keys=["source_commit_40hex_recorded","image_archive_sha256_recorded","binary_sha256_recorded",
          "wrapper_sha256_recorded","route_mapping_recorded","checked_matched_recorded",
          "core_instrumentation_explicitly_described"]
    labels=["Source\ncommit","Image\nhash","Binary\nhash","Interface\nhash","Route\nmapping","Check\ncounts","Core coverage\ndescription"]
    for y,r in enumerate(rows):
        for x,key in enumerate(keys):
            exists=audit[r["project"]][key]=="True"
            ax.scatter(x,y,marker="s" if x==6 else "o",s=105,
                       facecolors=(TEAL if x==6 else BLUE) if exists else "white",
                       edgecolors=(TEAL if x==6 else BLUE) if exists else "#AFBBC5",linewidths=1.3)
    ax.set_yticks(range(len(rows)),[r["project"] for r in rows]);ax.invert_yaxis()
    ax.set_xticks(range(7),labels);ax.xaxis.tick_top();ax.tick_params(length=0,pad=8)
    ax.set_xlim(-.6,6.65);ax.set_ylim(len(rows)+.55,-1)
    ax.axvline(5.5,color="#CDD6DD",lw=1)
    for y in range(len(rows)):ax.axhline(y,color="#EDF1F4",lw=.6,zorder=0)
    for spine in ax.spines.values():spine.set_visible(False)
    ax.text(2.7,len(rows)+.15,"Filled = recorded     Open = not established in the inspected field",ha="center",fontsize=9,color=GRAY)
    ax.set_title("C4 evidence inventory: recorded fields, not verified image completeness",pad=52,fontsize=13,weight="bold")
    save(fig,"fig4_evidence")

    labels=summary["core_screen_labels"];ordered=sorted(labels.items(),key=lambda kv:kv[1])
    temporal={"double-free","invalid-free","stack-use-after-return","use-after-free","use-after-poison"}
    review={"negative-size","overlapping-memcpy","unknown-crash"}
    colors=[ORANGE if k in review else TEAL if k in temporal else BLUE for k,_ in ordered]
    fig,ax=plt.subplots(figsize=(10,7.2),layout="constrained")
    ax.barh([k for k,_ in ordered],[v for _,v in ordered],color=colors)
    for i,(_,n) in enumerate(ordered):ax.text(n+12,i,str(n),va="center",fontsize=9)
    ax.set_xlim(0,1940);ax.set_xlabel("Historical issue records before site deduplication")
    ax.set_title("Input screening labels (3,685 records)",loc="left",pad=12)
    ax.legend(handles=[Patch(color=BLUE,label="Out-of-bounds labels"),Patch(color=TEAL,label="Lifetime-related labels"),
                       Patch(color=ORANGE,label="Additional classification needed")],loc="lower right",frameon=False,fontsize=9)
    ax.xaxis.grid(True,alpha=.15);ax.set_axisbelow(True)
    save(fig,"figS1_screen_types")
    print("Generated four main figures and one supplementary figure, PNG/SVG/PDF.")


if __name__ == "__main__":
    main()
