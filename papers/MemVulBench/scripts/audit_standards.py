"""Summarize existing evidence against four criteria; never execute targets."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

PAPER = Path(__file__).resolve().parents[1]
EVIDENCE = PAPER / "evidence"


def read_csv(name: str) -> list[dict[str, str]]:
    with (EVIDENCE / name).open() as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    selected = read_csv("selected_projects.csv")
    fields = {row["project"]: row for row in read_csv("field_audit.csv")}
    registry = json.loads((EVIDENCE / "observation_register.json").read_text())
    chain_path = EVIDENCE / "material_chain.json"
    chain = json.loads(chain_path.read_text()) if chain_path.is_file() else None
    chain_units = {row["project"]: row for row in chain["units"]} if chain else {}
    rereplay_path = EVIDENCE / "rereplay_fingerprint_ledger.json"
    rereplay = json.loads(rereplay_path.read_text()) if rereplay_path.is_file() else None
    rereplay_units = {row["project"]: row for row in rereplay["units"]} if rereplay else {}
    field_names = [key for key in next(iter(fields.values())) if key.endswith("_recorded")]
    field_names.append("core_instrumentation_explicitly_described")
    units = []
    for row in selected:
        project = row["project"]
        audit = fields[project]
        linked = chain_units.get(project, {})
        units.append({
            "project": project,
            "source_commit_recorded": row["source_commit"],
            "configuration_index": row["metadata_path"],
            "recorded_catalog_groups": int(row["recorded_expected_unique"]),
            "recorded_extra_report_groups": int(row["recorded_known_real_unique"]),
            "reconstructed_association_keys": linked.get("reconstructed_expected_association_keys"),
            "verified_memory_bug_count": (rereplay_units.get(project) or {}).get("final_entry_known_five_tuples"),
            "verified_count_status": "final_entry_five_tuple_admitted",
            "final_entry_expected_five_tuples": (rereplay_units.get(project) or {}).get("expected_five_tuples"),
            "final_entry_known_five_tuples": (rereplay_units.get(project) or {}).get("final_entry_known_five_tuples"),
            "checkout_matches_record": (rereplay_units.get(project) or {}).get("checkout_matches_record"),
            "admission_recorded": row["catalog_admission"],
            "fields_present": {key: audit[key] == "True" for key in field_names},
            "source_cleanliness": audit["core_source_cleanliness"],
            "identity_and_type": audit["group_type_identity_review"],
            "final_poc_group_chain": "recorded_association_reconstructed" if linked else "not_reconstructed",
            "local_image_archive_exists": bool((linked.get("image_archive") or {}).get("exists")),
            "local_aggregated_image_exists": bool((linked.get("aggregated_image_archive") or {}).get("exists")),
            "image_content_completeness": "not_independently_verified",
            "artifact_access": audit["artifact_access"],
            "raw_log_availability": audit["raw_log_availability"],
            "runtime_core_feedback": audit["runtime_core_feedback"],
            "normal_input_route_state_checks": audit["normal_input_route_state_checks"],
        })
    sources = ["selected_projects.csv", "field_audit.csv", "observation_register.json"]
    if chain_path.is_file():
        sources.append("material_chain.json")
    if rereplay_path.is_file():
        sources.append("rereplay_fingerprint_ledger.json")
    result = {
        "schema_version": "1.0",
        "criteria_version": "manuscript-v4",
        "record_snapshot_date": "2026-09-16",
        "audit_date": "2026-09-17",
        "scope": (
            "Metadata audit plus 2026-09-17 final-entry five-tuple identity and operator admission. "
            "verified_memory_bug_count is unique expected five-tuples plus unique extra five-tuples."
        ),
        "criteria": {
            "C1": "Authentic programs and memory vulnerabilities",
            "C2": "Memory-vulnerability count per test unit",
            "C3": "Complete PoC and fingerprint materials",
            "C4": "Complete build and runtime environment images",
        },
        "summary": {
            "units": len(units),
            "recorded_catalog_groups": sum(row["recorded_catalog_groups"] for row in units),
            "recorded_extra_report_groups": sum(row["recorded_extra_report_groups"] for row in units),
            "observation_rows": len(registry),
            "admission_recorded": dict(sorted(Counter(row["admission_recorded"] for row in units).items())),
            "fields_present": {key: sum(row["fields_present"][key] for row in units) for key in field_names},
            "missing_binary_or_wrapper_hash": [row["project"] for row in units if not (row["fields_present"]["binary_sha256_recorded"] and row["fields_present"]["wrapper_sha256_recorded"])],
            "historical_log_loss_reported": [row["project"] for row in units if row["raw_log_availability"] == "historical_loss_reported"],
            "material_chain": None if chain is None else chain.get("summary"),
        },
        "units": units,
        "source_files": [{"path": "evidence/" + name, "sha256": hashlib.sha256((EVIDENCE / name).read_bytes()).hexdigest()} for name in sources],
        "interpretation": {
            "known_verified_count_is_lower_bound": True,
            "recorded_groups_are_verified_lower_bound": False,
            "unknown_bugs_assumed_absent": False,
            "image_hash_proves_completeness": False,
            "effective_granularity_or_efficiency_measured": False,
            "cross_benchmark_systematic_audit_complete": False,
        },
    }
    output = EVIDENCE / "standards_gap_audit.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
