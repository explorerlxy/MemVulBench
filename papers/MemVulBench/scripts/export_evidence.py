"""Export existing metadata for the paper; never build or replay targets.

Reads recorded counts and the operator admission field already written
in measure JSON. Does not parse sanitizer logs or decide admission.
"""

from __future__ import annotations

import csv
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path


PAPER = Path(__file__).resolve().parents[1]
ROOT = PAPER.parents[1]
OUT = PAPER / "evidence"


def write_json(name: str, value: object) -> None:
    (OUT / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )


def write_csv(name: str, rows: list[dict]) -> None:
    if not rows:
        return
    with (OUT / name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    census_path = ROOT / "data/census/arvo_candidates.json"
    catalog_path = ROOT / "catalog/index.json"
    manual_paths = sorted((ROOT / "data/measure/manual").glob("*/*.json"))
    candidates = json.loads(census_path.read_text())
    catalog = json.loads(catalog_path.read_text())
    catalog_by_project = {row["project"]: row for row in catalog}
    core = [row for row in candidates if row["tier"] == "core"]
    eligible = [row for row in core
                if row["fix_commit"] and row["repo"] and not row["submodule_bug"]]
    project_sites: dict[str, set[str]] = defaultdict(set)
    for row in eligible:
        project_sites[row["project"]].add(row["site_key"])

    projects = []
    selected_details = []
    verdicts = []
    for path in manual_paths:
        data = json.loads(path.read_text())
        summary = data.get("summary", {})
        agg = data.get("aggregation", {})
        project = data.get("project", path.parent.name)
        cat = catalog_by_project[project]
        observations = data.get("observations", [])
        counts = Counter(row.get("verdict", "missing_verdict") for row in observations)
        row = {
            "project": project,
            "source_commit": data.get("source_commit", ""),
            "catalog_base_date": cat.get("base_date", ""),
            "catalog_base_method": cat.get("method", ""),
            "catalog_candidate_score": cat.get("n_latent"),
            "benchmark_seat": summary.get("benchmark_seat", "not_selected"),
            "catalog_admission": summary.get("catalog_admission", "not_recorded"),
            "recorded_expected_unique": summary.get("unique_expected_count"),
            "recorded_known_real_unique": summary.get("known_real_unique_count", 0),
            "recorded_total": summary.get("verified_vulnerability_count"),
            "observation_rows": len(observations),
            "recorded_expected_observations": counts.get("expected_asan", 0),
            "recorded_expected_asan_observations": counts.get("expected_asan", 0),
            "recorded_expected_crash_observations": counts.get("expected_crash", 0),
            "recorded_expected_total_observations": counts.get("expected_asan", 0) + counts.get("expected_crash", 0),
            "summary_expected_signature_count": summary.get("expected_signature_count"),
            "aggregation_method": agg.get("method", "none"),
            "aggregation_route_count": len(agg.get("mapping", {})),
            "aggregation_expected_checked": agg.get("verified_expected"),
            "aggregation_expected_matched": agg.get("verified_expected_matched"),
            "metadata_path": str(path.relative_to(ROOT)),
        }
        projects.append(row)
        for verdict, count in sorted(counts.items()):
            verdicts.append({"project": project, "verdict": verdict,
                             "observation_rows": count,
                             "benchmark_seat": row["benchmark_seat"]})
        if row["benchmark_seat"] == "in_set":
            selected_details.append({
                "project": project,
                "metadata_path": row["metadata_path"],
                "summary": summary,
                "aggregation": agg,
                "known_real_records": data.get("known_real_vulnerabilities", []),
                "recorded_verdict_counts": dict(sorted(counts.items())),
            })

    selected = sorted([row for row in projects if row["benchmark_seat"] == "in_set"],
                      key=lambda row: (-row["recorded_total"], row["project"]))
    totals = [row["recorded_total"] for row in selected]
    assert all(row["recorded_total"] == row["recorded_expected_unique"]
               + row["recorded_known_real_unique"] for row in selected)
    selected_names = {row["project"] for row in selected}
    selected_verdicts: Counter = Counter()
    for row in verdicts:
        if row["project"] in selected_names:
            selected_verdicts[row["verdict"]] += row["observation_rows"]
    census = {
        "source_records": len(candidates),
        "core_screen_records": len(core),
        "core_screen_fraction": len(core) / len(candidates),
        "metadata_eligible_core_records": len(eligible),
        "legacy_global_site_keys": len({row["site_key"] for row in eligible}),
        "project_namespaced_site_keys": sum(map(len, project_sites.values())),
        "projects_above_ten_sites": sum(len(sites) > 10 for sites in project_sites.values()),
        "catalog_projects": len(catalog),
        "catalog_resolved_bases": sum(bool(row.get("base")) for row in catalog),
        "manual_projects": len(projects),
        "selected_projects": len(selected),
        "selected_recorded_expected_unique": sum(row["recorded_expected_unique"] for row in selected),
        "selected_recorded_known_real_unique": sum(row["recorded_known_real_unique"] for row in selected),
        "selected_recorded_total": sum(totals),
        "selected_recorded_total_mean": statistics.mean(totals),
        "selected_recorded_total_median": statistics.median(totals),
        "selected_recorded_total_min": min(totals),
        "selected_recorded_total_max": max(totals),
        "selected_identity_projects": sum(row["aggregation_method"].startswith("identity") for row in selected),
        "selected_prefix_projects": sum(row["aggregation_method"].startswith("prefix") for row in selected),
        "selected_routes": sum(row["aggregation_route_count"] for row in selected),
        "selected_observation_rows": sum(row["observation_rows"] for row in selected),
        "selected_recorded_verdict_counts": dict(sorted(selected_verdicts.items())),
        "selected_all_pending": all("pending" in row["catalog_admission"] for row in selected),
        "core_screen_groups": dict(sorted(Counter(row["group"] for row in core).items())),
        "core_screen_labels": dict(sorted(Counter(row["label"] for row in core).items())),
        "interpretation": (
            "Recorded metadata snapshot plus 2026-09-17 operator admission. "
            "Identity is the final-entry five-tuple. "
            "catalog_admission=admitted does not change catalog group columns."
        ),
    }
    source_paths = [census_path, catalog_path, *manual_paths,
                    ROOT / "memvul/taxonomy.py", ROOT / "memvul/candidates.py",
                    ROOT / "memvul/arvo.py", ROOT / "docs/known-real.md",
                    ROOT / "docs/build-progress.md", ROOT / "docs/catalog.md"]
    manifest = [{"path": str(path.relative_to(ROOT)),
                 "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                 "bytes": path.stat().st_size} for path in sorted(source_paths)]
    write_json("summary.json", census)
    write_json("source_manifest.json", manifest)
    write_json("selected_recorded_details.json", selected_details)
    write_csv("all_manual_projects.csv", projects)
    write_csv("selected_projects.csv", selected)
    write_csv("recorded_verdicts.csv", verdicts)
    write_csv("census_labels.csv", [
        {"label": label, "records": count} for label, count in
        Counter(row["label"] for row in core).most_common()
    ])
    table = ["| 项目 | 历史版本 | 入口 / 路由数 | expected 去重 | KR | 合计 |",
             "|---|---|---|---:|---:|---:|"]
    for row in selected:
        method = "identity" if row["aggregation_method"].startswith("identity") else "prefix"
        table.append(f"| {row['project']} | `{row['source_commit'][:12]}` | "
                     f"{method} / {row['aggregation_route_count']} | "
                     f"{row['recorded_expected_unique']} | {row['recorded_known_real_unique']} | "
                     f"{row['recorded_total']} |")
    (OUT / "selected_projects.md").write_text("\n".join(table) + "\n")
    print(json.dumps(census, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
