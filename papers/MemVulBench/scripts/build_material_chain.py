"""Reconstruct recorded material chains. Never build, replay, or admit targets.

This script only transcribes already-recorded associations: observation rows,
catalog bug fields, aggregation routes, and local path existence. It does not
parse sanitizer logs, invent group identities, or fill verified counts.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

PAPER = Path(__file__).resolve().parents[1]
ROOT = PAPER.parents[1]
OUT = PAPER / "evidence"
EXPECTED = {"expected_asan", "expected_crash"}
EXTRA = {"known_real"}


def write_json(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def write_csv(name: str, rows: list[dict]) -> None:
    if not rows:
        return
    with (OUT / name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_catalog_bugs(text: str) -> dict[int, dict]:
    bugs: dict[int, dict] = {}
    current: dict | None = None
    in_bugs = False
    for line in text.splitlines():
        if line.startswith("bugs:"):
            in_bugs = True
            continue
        if in_bugs and line and not line[0].isspace():
            break
        if not in_bugs:
            continue
        stripped = line.strip()
        if stripped.startswith("- oss_id:"):
            if current and "oss_id" in current:
                bugs[int(current["oss_id"])] = current
            current = {"oss_id": int(stripped.split(":", 1)[1].strip())}
            continue
        if current is None or ":" not in stripped:
            continue
        key, raw = stripped.split(":", 1)
        value = raw.strip()
        if value.startswith("[") and value.endswith("]"):
            current[key] = [item.strip() for item in value[1:-1].split(",") if item.strip()]
        elif len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            current[key] = value[1:-1]
        else:
            current[key] = value
    if current and "oss_id" in current:
        bugs[int(current["oss_id"])] = current
    return bugs


def load_json_if_present(path: Path):
    if path.is_file():
        return json.loads(path.read_text())
    return None


def path_state(path: str | None) -> dict:
    if not path:
        return {"recorded": False, "exists": False, "path": None, "kind": None, "bytes": None}
    target = Path(path)
    if target.is_file():
        return {"recorded": True, "exists": True, "path": path, "kind": "file", "bytes": target.stat().st_size}
    if target.is_dir():
        return {"recorded": True, "exists": True, "path": path, "kind": "dir",
                "bytes": None, "entries": sum(1 for _ in target.iterdir())}
    return {"recorded": True, "exists": False, "path": path, "kind": None, "bytes": None}


def association_key(signature) -> str | None:
    if not signature:
        return None
    return "|".join(str(part) for part in signature)


def type_hint_from_catalog(bug: dict | None) -> str | None:
    if not bug:
        return None
    group = str(bug.get("group") or "").lower()
    cwe = str(bug.get("cwe") or "").upper()
    label = str(bug.get("label") or "").lower()
    if any(token in label for token in ("unknown-crash", "overlapping", "negative-size", "segv")):
        return "X"
    if "double-free" in label or "invalid-free" in label or cwe in {"CWE-415", "CWE-590"}:
        return "C"
    if "uninitial" in label or cwe == "CWE-457":
        return "D"
    if "null" in label or cwe == "CWE-476":
        return "E"
    if group == "temporal" or "use-after" in label or cwe == "CWE-416":
        return "B"
    if group == "spatial" or cwe in {"CWE-125", "CWE-787", "CWE-119"}:
        return "A"
    if any(token in label for token in ("unknown-crash", "overlapping", "negative-size", "segv")):
        return "X"
    return None


def type_hint_from_signature(signature) -> str | None:
    if not signature:
        return None
    kind = str(signature[0]).lower()
    if any(token in kind for token in ("use-after-free", "use-after-poison", "use-after-return", "use-after-scope")):
        return "B"
    if any(token in kind for token in ("double-free", "invalid-free", "bad-free")):
        return "C"
    if "uninitial" in kind:
        return "D"
    if any(token in kind for token in ("overflow", "underflow", "buffer", "oob")):
        return "A"
    if any(token in kind for token in ("segv", "unknown-crash", "memcpy-param-overlap", "negative-size", "null")):
        return "X"
    return None


def combine_type_hint(catalog_hint: str | None, signature_hint: str | None) -> dict:
    if catalog_hint and signature_hint and catalog_hint != signature_hint:
        return {"hint": None, "status": "catalog_and_signature_disagree",
                "catalog_hint": catalog_hint, "signature_hint": signature_hint}
    hint = catalog_hint or signature_hint
    if hint is None:
        return {"hint": None, "status": "unknown", "catalog_hint": None, "signature_hint": None}
    return {"hint": hint, "status": "recorded_hint_only",
            "catalog_hint": catalog_hint, "signature_hint": signature_hint}


def find_original_poc(poc_root: Path | None, oss_id: int, index: dict | None) -> Path | None:
    if poc_root is None:
        return None
    record = None
    if isinstance(index, dict):
        record = index.get(str(oss_id)) or index.get(oss_id)
    if isinstance(record, dict) and record.get("file"):
        candidate = poc_root / record["file"]
        if candidate.is_file():
            return candidate
    for candidate in (poc_root / str(oss_id), poc_root / "raw" / str(oss_id)):
        if candidate.is_file():
            return candidate
    return None


def find_agg_poc(poc_root: Path | None, oss_id: int, agg_index: dict | None) -> Path | None:
    if poc_root is None:
        return None
    agg_dir = poc_root / "agg"
    if isinstance(agg_index, dict):
        for item in agg_index.get("pocs") or []:
            if int(item.get("oss_id", -1)) == oss_id and item.get("file"):
                candidate = agg_dir / item["file"]
                if candidate.is_file():
                    return candidate
    candidate = agg_dir / str(oss_id)
    if candidate.is_file():
        return candidate
    return None


def find_log(directory: str | None, names: list[str]) -> Path | None:
    if not directory:
        return None
    root = Path(directory)
    for name in names:
        if not name:
            continue
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def resolve_harness(observation: dict, catalog: dict | None, data: dict, mapping: dict) -> str | None:
    if observation.get("harness"):
        return observation["harness"]
    if catalog and catalog.get("harness"):
        return catalog["harness"]
    if isinstance(data.get("harness"), str):
        return data["harness"]
    harnesses = data.get("harnesses")
    if isinstance(harnesses, str):
        return harnesses
    if isinstance(harnesses, list) and len(harnesses) == 1:
        item = harnesses[0]
        return item.get("name") if isinstance(item, dict) else item
    if len(mapping) == 1:
        return next(iter(mapping.values()))
    return None


def route_for_harness(mapping: dict, harness: str | None) -> str | None:
    if not mapping:
        return None
    if harness:
        for route, name in mapping.items():
            aliases = [part.strip() for part in str(name).split("/")]
            if harness == name or harness in aliases:
                return str(route)
    if len(mapping) == 1:
        return next(iter(mapping))
    return None


def existing_file(path: Path | None) -> dict:
    if path is None:
        return {"exists": False, "path": None, "bytes": None}
    return {"exists": True, "path": str(path), "bytes": path.stat().st_size}


def main() -> None:
    selected = list(csv.DictReader((OUT / "selected_projects.csv").open()))
    rereplay_path = OUT / "rereplay_fingerprint_ledger.json"
    rereplay = json.loads(rereplay_path.read_text()) if rereplay_path.is_file() else None
    rereplay_units = {row["project"]: row for row in rereplay["units"]} if rereplay else {}
    units = []
    groups = []
    observations = []
    missing = []
    hdf5_rows = []

    for row in selected:
        data = json.loads((ROOT / row["metadata_path"]).read_text())
        project = data["project"]
        catalog_bugs = parse_catalog_bugs((ROOT / "catalog" / project / "target.yaml").read_text())
        agg = data.get("aggregation") or {}
        replay = data.get("replay") or {}
        mapping = {str(key): value for key, value in (agg.get("mapping") or {}).items()}
        poc_root = Path(data["poc_archive_root"]) if data.get("poc_archive_root") else None
        poc_index = load_json_if_present(poc_root / "index.json") if poc_root else None
        agg_index = load_json_if_present(poc_root / "agg" / "index.json") if poc_root else None
        extra_records = [item for item in data.get("known_real_vulnerabilities") or []
                         if item.get("unique_outside_expected")]
        extra_by_id = {}
        for item in extra_records:
            for oss_id in item.get("oss_ids") or []:
                extra_by_id[int(oss_id)] = item

        unit_obs = []
        for index, observation in enumerate(data.get("observations") or []):
            oss_id = observation.get("oss_id")
            signature = observation.get("signature")
            catalog = catalog_bugs.get(int(oss_id)) if oss_id is not None else None
            extra = extra_by_id.get(int(oss_id)) if oss_id is not None else None
            harness = resolve_harness(observation, catalog, data, mapping)
            route = route_for_harness(mapping, harness)
            original_poc = find_original_poc(poc_root, int(oss_id), poc_index) if oss_id is not None else None
            agg_poc = find_agg_poc(poc_root, int(oss_id), agg_index) if oss_id is not None else None
            original_log = find_log(replay.get("logs"), [observation.get("log") or ""])
            agg_log = find_log(agg.get("logs"), [observation.get("log") or "", f"{oss_id}.log"])
            type_info = combine_type_hint(type_hint_from_catalog(catalog), type_hint_from_signature(signature))
            recorded = {
                "project": project,
                "source_commit": data.get("source_commit"),
                "record_pointer": f"{row['metadata_path']}#/observations/{index}",
                "oss_id": oss_id,
                "verdict": observation.get("verdict"),
                "exit_code": observation.get("exit_code"),
                "original_harness": harness,
                "final_route": route,
                "final_harness_name": mapping.get(route) if route is not None else None,
                "association_key": association_key(signature),
                "signature": signature,
                "catalog_cwe": None if catalog is None else catalog.get("cwe"),
                "catalog_label": None if catalog is None else catalog.get("label"),
                "catalog_group": None if catalog is None else catalog.get("group"),
                "catalog_status": None if catalog is None else catalog.get("status"),
                "catalog_fix_commit": None if catalog is None else catalog.get("fix_commit"),
                "extra_fingerprint_id": None if extra is None else extra.get("fingerprint_id"),
                "type_hint": type_info["hint"],
                "type_hint_status": type_info["status"],
                "original_poc": existing_file(original_poc),
                "aggregated_poc": existing_file(agg_poc),
                "original_log": existing_file(original_log),
                "aggregated_log": existing_file(agg_log),
                "identity_status": "pending",
                "verified_member": False,
            }
            unit_obs.append(recorded)
            observations.append(recorded)
            if project == "hdf5" and observation.get("verdict") in EXPECTED:
                hdf5_rows.append(recorded)

        expected_rows = [item for item in unit_obs if item["verdict"] in EXPECTED]
        extra_rows = [item for item in unit_obs if item["verdict"] in EXTRA]
        expected_by_key: dict[str, list] = defaultdict(list)
        unsigned = []
        for item in expected_rows:
            if item["association_key"]:
                expected_by_key[item["association_key"]].append(item)
            else:
                unsigned.append(item)
        reconstructed = len(expected_by_key) + len(unsigned)
        recorded_unique = int(row["recorded_expected_unique"])
        extra_unique = int(row["recorded_known_real_unique"])

        harness_keys: dict[str, set[str]] = defaultdict(set)
        for item in expected_rows:
            if item["association_key"] and item["original_harness"]:
                harness_keys[item["original_harness"]].add(item["association_key"])
        dmax = max((len(keys) for keys in harness_keys.values()), default=None)
        dunion = len({item["association_key"] for item in expected_rows if item["association_key"]}) or None

        def add_group(members: list[dict], layer: str, locator: str, extra_id: str | None = None) -> None:
            keys = {member["association_key"] for member in members if member["association_key"]}
            hints = {member["type_hint"] for member in members if member["type_hint"]}
            groups.append({
                "locator": locator,
                "project": project,
                "source_commit": data.get("source_commit"),
                "layer": layer,
                "association_keys": sorted(keys),
                "extra_fingerprint_id": extra_id,
                "member_oss_ids": [member["oss_id"] for member in members],
                "member_count": len(members),
                "original_harnesses": sorted({member["original_harness"] for member in members if member["original_harness"]}),
                "final_routes": sorted({member["final_route"] for member in members if member["final_route"] is not None}),
                "type_hint": next(iter(hints)) if len(hints) == 1 else None,
                "type_hint_status": "pending" if len(hints) != 1 else "recorded_hint_only",
                "catalog_cwes": sorted({member["catalog_cwe"] for member in members if member["catalog_cwe"]}),
                "any_original_poc": any(member["original_poc"]["exists"] for member in members),
                "any_aggregated_poc": any(member["aggregated_poc"]["exists"] for member in members),
                "any_original_log": any(member["original_log"]["exists"] for member in members),
                "any_aggregated_log": any(member["aggregated_log"]["exists"] for member in members),
                "identity_status": "pending",
                "verified_memory_bug": False,
            })

        for ordinal, key in enumerate(sorted(expected_by_key), start=1):
            add_group(expected_by_key[key], "catalog_associated", f"{project}:expected:{ordinal:03d}")
        for ordinal, item in enumerate(unsigned, start=1):
            add_group([item], "catalog_associated_unsigned", f"{project}:unsigned:{ordinal:03d}")
        for ordinal, item in enumerate(extra_records, start=1):
            members = [row_item for row_item in extra_rows
                       if row_item["oss_id"] in set(item.get("oss_ids") or [])]
            if not members:
                continue
            add_group(members, "extra_report", f"{project}:extra:{ordinal:03d}", item.get("fingerprint_id"))

        image = path_state(data.get("image_archive"))
        agg_image = path_state(agg.get("image_archive"))
        manual = data.get("manual_archive")
        manual_path = manual.get("path") if isinstance(manual, dict) else manual
        unit = {
            "project": project,
            "source_commit": data.get("source_commit"),
            "configuration_index": row["metadata_path"],
            "interface_method": agg.get("method"),
            "routes": mapping,
            "recorded_expected_unique": recorded_unique,
            "reconstructed_expected_association_keys": reconstructed,
            "association_count_matches_summary": reconstructed == recorded_unique,
            "recorded_extra_report_groups": extra_unique,
            "verified_memory_bug_count": (rereplay_units.get(project) or {}).get("final_entry_known_five_tuples"),
            "recorded_dmax_association_keys": dmax,
            "recorded_dunion_association_keys": dunion,
            "aggregation_checked": agg.get("verified_expected"),
            "aggregation_matched": agg.get("verified_expected_matched"),
            "expected_observations": len(expected_rows),
            "expected_with_original_poc": sum(item["original_poc"]["exists"] for item in expected_rows),
            "expected_with_aggregated_poc": sum(item["aggregated_poc"]["exists"] for item in expected_rows),
            "expected_with_original_log": sum(item["original_log"]["exists"] for item in expected_rows),
            "expected_with_aggregated_log": sum(item["aggregated_log"]["exists"] for item in expected_rows),
            "expected_with_route": sum(item["final_route"] is not None for item in expected_rows),
            "expected_with_type_hint": sum(item["type_hint"] is not None for item in expected_rows),
            "image_archive": image,
            "aggregated_image_archive": agg_image,
            "manual_archive": path_state(manual_path),
            "final_binary_sha256_recorded": bool(agg.get("binary_sha256")),
            "wrapper_sha256_recorded": bool(agg.get("source_sha256")),
            "admission_recorded": row["catalog_admission"],
        }
        units.append(unit)

        def add_missing(kind: str, detail: str | None = None, oss_id=None) -> None:
            missing.append({
                "project": project,
                "kind": kind,
                "oss_id": "" if oss_id is None else oss_id,
                "detail": detail or "",
            })

        if reconstructed != recorded_unique:
            add_missing("association_count_mismatch",
                        f"reconstructed {reconstructed} != recorded {recorded_unique}")
        if not image["exists"]:
            add_missing("image_archive_missing", image["path"])
        if agg.get("image_archive") and not agg_image["exists"]:
            add_missing("aggregated_image_missing", agg_image["path"])
        if not agg.get("binary_sha256"):
            add_missing("final_binary_hash_unrecorded", agg.get("binary"))
        if not agg.get("source_sha256"):
            add_missing("wrapper_hash_unrecorded", agg.get("source"))
        for item in expected_rows + extra_rows:
            if not item["original_poc"]["exists"] and not item["aggregated_poc"]["exists"]:
                add_missing("no_local_poc", item["original_harness"], item["oss_id"])
            if not item["original_log"]["exists"] and not item["aggregated_log"]["exists"]:
                add_missing("no_local_log", item["verdict"], item["oss_id"])
            if item["final_route"] is None:
                add_missing("route_unmapped", item["original_harness"], item["oss_id"])
            if item["type_hint_status"] == "catalog_and_signature_disagree":
                add_missing("type_hint_conflict",
                            f"{item['catalog_cwe']} vs {item['association_key']}", item["oss_id"])

    expected_groups = [item for item in groups if item["layer"] == "catalog_associated"]
    extra_groups = [item for item in groups if item["layer"] == "extra_report"]
    expected_obs = [item for item in observations if item["verdict"] in EXPECTED]
    type_counts = Counter(item["type_hint"] for item in expected_groups)
    summary = {
        "units": len(units),
        "recorded_expected_groups": sum(item["recorded_expected_unique"] for item in units),
        "reconstructed_expected_association_keys": len(expected_groups),
        "association_count_matches_all_units": all(item["association_count_matches_summary"] for item in units),
        "recorded_extra_report_groups": sum(item["recorded_extra_report_groups"] for item in units),
        "reconstructed_extra_report_groups": len(extra_groups),
        "verified_memory_bug_count": None if rereplay is None else rereplay.get("unique_known_five_tuples"),
        "final_entry_rereplay": None if rereplay is None else {
            "audit_date": rereplay.get("audit_date"),
            "ledger": "evidence/rereplay_fingerprint_ledger.json",
            "observations": rereplay.get("computed_observations"),
            "unique_expected_five_tuples": rereplay.get("unique_expected_five_tuples"),
            "unique_extra_five_tuples_outside_expected": rereplay.get("unique_extra_outside_expected"),
            "unique_known_five_tuples": rereplay.get("unique_known_five_tuples"),
            "catalog_admission": "admitted",
        },
        "expected_observations": len(expected_obs),
        "expected_with_original_poc": sum(item["original_poc"]["exists"] for item in expected_obs),
        "expected_with_aggregated_poc": sum(item["aggregated_poc"]["exists"] for item in expected_obs),
        "expected_with_any_poc": sum(item["original_poc"]["exists"] or item["aggregated_poc"]["exists"] for item in expected_obs),
        "expected_with_original_log": sum(item["original_log"]["exists"] for item in expected_obs),
        "expected_with_aggregated_log": sum(item["aggregated_log"]["exists"] for item in expected_obs),
        "expected_with_any_log": sum(item["original_log"]["exists"] or item["aggregated_log"]["exists"] for item in expected_obs),
        "expected_with_route": sum(item["final_route"] is not None for item in expected_obs),
        "units_with_local_image": sum(item["image_archive"]["exists"] for item in units),
        "units_with_local_aggregated_image": sum(item["aggregated_image_archive"]["exists"] for item in units),
        "units_missing_final_binary_hash": [item["project"] for item in units if not item["final_binary_sha256_recorded"]],
        "recorded_type_hint_counts_expected_groups": dict(sorted((key or "unknown", value) for key, value in type_counts.items())),
        "missing_item_counts": dict(sorted(Counter(item["kind"] for item in missing).items())),
        "interpretation": (
            "Recorded association reconstruction and local path existence only. "
            "Association keys are the existing four-tuple report features, not audited group_id values. "
            "Type hints are catalog/signature labels, not verified CWE membership. "
            "verified_memory_bug_count is the admitted final-entry five-tuple total."
        ),
    }
    result = {
        "schema_version": "1.0",
        "audit_date": "2026-09-17",
        "scope": (
            "Metadata and local-path inventory for the 20 selected units. "
            "No build, replay, sanitizer-log parse, new identity, or admission."
        ),
        "summary": summary,
        "units": units,
        "groups": groups,
        "hdf5_expected_route_ledger": [
            {
                "oss_id": item["oss_id"],
                "original_harness": item["original_harness"],
                "final_route": item["final_route"],
                "association_key": item["association_key"],
                "original_log": item["original_log"]["path"],
                "aggregated_poc": item["aggregated_poc"]["path"],
                "aggregated_log": item["aggregated_log"]["path"],
                "catalog_cwe": item["catalog_cwe"],
                "type_hint": item["type_hint"],
            }
            for item in hdf5_rows
        ],
        "missing": missing,
        "source_files": [
            {"path": "evidence/selected_projects.csv", "sha256": digest(OUT / "selected_projects.csv")},
            {"path": "catalog/<project>/target.yaml", "note": "read per selected project"},
            {"path": "data/measure/manual/<project>/<commit>.json", "note": "read per selected project"},
        ],
    }
    write_json("material_chain.json", result)
    write_csv("material_chain_units.csv", [{
        "project": item["project"],
        "source_commit": item["source_commit"],
        "interface_method": item["interface_method"],
        "recorded_expected_unique": item["recorded_expected_unique"],
        "reconstructed_expected_association_keys": item["reconstructed_expected_association_keys"],
        "association_count_matches_summary": item["association_count_matches_summary"],
        "recorded_extra_report_groups": item["recorded_extra_report_groups"],
        "verified_memory_bug_count": "",
        "recorded_dmax_association_keys": item["recorded_dmax_association_keys"],
        "recorded_dunion_association_keys": item["recorded_dunion_association_keys"],
        "expected_observations": item["expected_observations"],
        "expected_with_original_poc": item["expected_with_original_poc"],
        "expected_with_aggregated_poc": item["expected_with_aggregated_poc"],
        "expected_with_original_log": item["expected_with_original_log"],
        "expected_with_aggregated_log": item["expected_with_aggregated_log"],
        "expected_with_route": item["expected_with_route"],
        "image_archive_exists": item["image_archive"]["exists"],
        "aggregated_image_exists": item["aggregated_image_archive"]["exists"],
        "final_binary_sha256_recorded": item["final_binary_sha256_recorded"],
        "admission_recorded": item["admission_recorded"],
    } for item in units])
    write_csv("material_chain_groups.csv", [{
        "locator": item["locator"],
        "project": item["project"],
        "layer": item["layer"],
        "association_key": item["association_keys"][0] if item["association_keys"] else "",
        "member_oss_ids": " ".join(str(value) for value in item["member_oss_ids"]),
        "member_count": item["member_count"],
        "original_harnesses": " ".join(item["original_harnesses"]),
        "final_routes": " ".join(item["final_routes"]),
        "type_hint": item["type_hint"] or "",
        "catalog_cwes": " ".join(item["catalog_cwes"]),
        "any_original_poc": item["any_original_poc"],
        "any_aggregated_poc": item["any_aggregated_poc"],
        "any_original_log": item["any_original_log"],
        "any_aggregated_log": item["any_aggregated_log"],
        "identity_status": item["identity_status"],
        "verified_memory_bug": item["verified_memory_bug"],
    } for item in groups])
    write_csv("missing_materials.csv", missing or [{"project": "", "kind": "none", "detail": "no missing rows"}])
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
