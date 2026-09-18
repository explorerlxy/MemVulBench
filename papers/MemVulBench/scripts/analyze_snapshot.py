"""Read-only analysis of recorded fields; no replay, ASan parsing or admission."""
from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

PAPER = Path(__file__).resolve().parents[1]
OUT = PAPER / "evidence"


def main() -> None:
    with (OUT / "selected_projects.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    details = json.loads((OUT / "selected_recorded_details.json").read_text())
    expected = [int(row["recorded_expected_unique"]) for row in rows]
    totals = [int(row["recorded_total"]) for row in rows]
    coverage_core = {"fluent-bit", "libxml2", "librawspeed"}
    audit = []
    for item in details:
        agg = item["aggregation"]
        row = next(row for row in rows if row["project"] == item["project"])
        audit.append({
            "project": item["project"],
            "source_commit_40hex_recorded": is_hex(row["source_commit"], 40),
            "image_archive_sha256_recorded": is_hex(agg.get("image_archive_sha256", ""), 64),
            "binary_sha256_recorded": is_hex(agg.get("binary_sha256", ""), 64),
            "wrapper_sha256_recorded": is_hex(agg.get("source_sha256", ""), 64),
            "route_mapping_recorded": bool(agg.get("mapping")),
            "checked_matched_recorded": all(isinstance(agg.get(k), int) for k in
                                            ("verified_expected", "verified_expected_matched")),
            "core_instrumentation_explicitly_described": item["project"] in coverage_core,
            "runtime_core_feedback": "not_independently_verified",
            "normal_input_route_state_checks": "not_independently_verified",
            "group_type_identity_review": "five_tuple_kind_cleared",
            "core_source_cleanliness": "not_independently_verified",
            "raw_log_availability": "historical_loss_reported" if item["project"] in {"pcl", "PcapPlusPlus", "gpac"} else "not_audited",
            "artifact_access": "local_path_recorded_not_verified",
            "public_access_and_redistribution": "not_confirmed",
            "configuration_index": row["metadata_path"],
            "coverage_text": agg.get("coverage", ""),
            "source": item["metadata_path"] + "#aggregation",
        })
    with (OUT / "field_audit.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(audit[0]))
        writer.writeheader()
        writer.writerows(audit)
    # Copy source records verbatim, without parsing signatures or inventing groups.
    register = []
    root = PAPER.parents[1]
    for item in details:
        original = json.loads((root / item["metadata_path"]).read_text())
        if item["project"] in {"hdf5", "assimp"}:
            examples = OUT / "configuration_examples"
            examples.mkdir(exist_ok=True)
            fields = {key: original[key] for key in
                      ("project", "source_dir", "source_commit", "image", "harnesses", "build",
                       "replay", "manual_archive", "aggregation") if key in original}
            fields["_interpretation"] = "Verbatim recorded configuration fields, not an independently validated recipe."
            fields["_source"] = item["metadata_path"]
            (examples / f"{item['project']}.json").write_text(
                json.dumps(fields, ensure_ascii=False, indent=2) + "\n")
        for index, observation in enumerate(original.get("observations", [])):
            register.append({
                "record_pointer": item["metadata_path"] + f"#/observations/{index}",
                "project": item["project"],
                "source_commit_recorded": original.get("source_commit"),
                "final_binary_hash_recorded": item["aggregation"].get("binary_sha256"),
                "final_configuration_membership": "not_inferred_from_project_summary",
                "observation_verbatim": observation,
            })
    (OUT / "observation_register.json").write_text(json.dumps(register, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    with (OUT / "all_manual_projects.csv").open() as handle:
        all_rows = list(csv.DictReader(handle))
    version_rows = [{"project": row["project"], "adopted_commit": row["source_commit"],
                     "selection_source": row["catalog_base_method"],
                     "candidate_score_recorded": row["catalog_candidate_score"],
                     "heuristic_candidate_before_override": "not_exported_in_current_index",
                     "search_scope_and_stop_rule": "not_recorded_in_current_index",
                     "source": row["metadata_path"]} for row in rows]
    with (OUT / "version_provenance.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(version_rows[0]))
        writer.writeheader(); writer.writerows(version_rows)
    result = {
        "scope": "Existing selected-project metadata only; not independent vulnerability or binary validation.",
        "expected_only": {"projects": len(rows), "groups": sum(expected),
                          "mean": statistics.mean(expected), "median": statistics.median(expected),
                          "min": min(expected), "max": max(expected),
                          "projects_at_least_8": sum(n >= 8 for n in expected)},
        "selected_version_sources": {mode: sum(r["catalog_base_method"] == mode for r in rows)
                                     for mode in ("wave_eve", "measured_sweep")},
        "nonselected_recorded_projects": sum(r["benchmark_seat"] != "in_set" for r in all_rows),
        "observation_register_rows": len(register),
        "extra_groups_removed": sum(totals) - sum(expected),
        "threshold_sensitivity": [{"threshold": k, "expected_only_projects": sum(n >= k for n in expected),
                                   "all_recorded_projects": sum(n >= k for n in totals)}
                                  for k in (8, 10, 12, 15, 20)],
        "interface_strata": [{"mode": mode, "projects": len(group),
                              "expected_groups": sum(int(r["recorded_expected_unique"]) for r in group),
                              "routes": sum(int(r["aggregation_route_count"]) for r in group)}
                             for mode in ("identity", "prefix")
                             for group in [[r for r in rows if r["aggregation_method"].startswith(mode)]]],
        "field_presence_counts": {key: sum(row[key] for row in audit)
                                  for key in audit[0] if isinstance(audit[0][key], bool)},
        "coverage_classification_rule": "Explicit library/core instrumentation stated in aggregation.coverage for fluent-bit, libxml2 and librawspeed; other 17 remain unestablished by this field, not proven uninstrumented.",
        "notes": ["Threshold sensitivity applies only to the fixed 20 selected projects and is not a new selection or admission decision.",
                  "Field presence does not prove artifact existence, hash correctness, reproducibility or functional feedback.",
                  "Core coverage description is a documentation category; none is promoted to campaign-ready."]
    }
    (OUT / "lightweight_analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def is_hex(value: str, length: int) -> bool:
    return len(value) == length and all(c in "0123456789abcdef" for c in value)


if __name__ == "__main__":
    main()
