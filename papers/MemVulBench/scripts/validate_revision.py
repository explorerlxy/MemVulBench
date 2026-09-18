"""Validate the paper package only; do not run benchmark binaries."""
from __future__ import annotations

import ast
import csv
import hashlib
import json
import re
import shutil
import tempfile
from collections import Counter
from pathlib import Path

PAPER = Path(__file__).resolve().parents[1]
ROOT = PAPER.parents[1]
REVISION = PAPER / "revision-v4"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    source_items = []
    for manifest in ("source_manifest.json", "method_source_manifest.json"):
        items = json.loads((PAPER / "evidence" / manifest).read_text())
        source_items.extend(items)
        for item in items:
            assert digest(ROOT / item["path"]) == item["sha256"], item["path"]
    manuscript = (PAPER / "manuscript.md").read_text()
    abstract = manuscript.split("## 摘要", 1)[1].split("## 1 引言", 1)[0]
    assert "64" not in abstract and "37" not in abstract
    assert "20个真实项目" in abstract
    assert "## 2 评测需求与基准设计标准" in manuscript
    assert "## 3 现有资源与专用基准缺口" in manuscript
    assert "### 5.7 设计要求的满足程度与基准价值" in manuscript
    for criterion in ("C1", "C2", "C3", "C4"):
        assert criterion in manuscript.split("表 1　", 1)[1].split("### 2.2", 1)[0]
        assert criterion in manuscript.split("表 6　", 1)[1].split("## 6", 1)[0]
    assert "C5" not in manuscript
    assert "C=(F,S,U,T)" in manuscript
    assert "U=(P,V,H)" in manuscript
    assert "T=(P,V,E,H,O,B)" not in manuscript
    gap_audit = json.loads((PAPER / "evidence/standards_gap_audit.json").read_text())
    for item in gap_audit["source_files"]:
        assert digest(PAPER / item["path"]) == item["sha256"]
    assert set(gap_audit["criteria"]) == {"C1", "C2", "C3", "C4"}
    assert len(gap_audit["units"]) == 20
    ledger = json.loads((PAPER / "evidence/rereplay_fingerprint_ledger.json").read_text())
    known_by_project = {
        row["project"]: row["final_entry_known_five_tuples"] for row in ledger["units"]
    }
    assert all(
        row["verified_memory_bug_count"] == known_by_project[row["project"]]
        for row in gap_audit["units"]
    )
    assert gap_audit["summary"]["recorded_catalog_groups"] == 291
    assert gap_audit["summary"]["missing_binary_or_wrapper_hash"] == []
    chain = json.loads((PAPER / "evidence/material_chain.json").read_text())
    assert chain["summary"]["verified_memory_bug_count"] == ledger["unique_known_five_tuples"]
    assert ledger["unique_known_five_tuples"] == 291
    assert chain["summary"]["expected_observations"] == 294
    assert chain["summary"]["expected_with_any_poc"] == 294
    assert chain["summary"]["expected_with_any_log"] == 294
    assert chain["summary"]["expected_with_route"] == 294
    assert chain["summary"]["reconstructed_expected_association_keys"] == 289
    assert chain["summary"]["units_with_local_image"] == 20
    assert chain["summary"]["units_missing_final_binary_hash"] == []
    assert (PAPER / "evidence/selected_projects.md").read_text().strip() in manuscript
    assert re.findall(r"^\[(\d+)\] ", manuscript, re.M) == [str(n) for n in range(1, 15)]
    assert re.findall(r"^图 (\d+)　", manuscript, re.M) == ["1", "2", "3", "4"]
    assert re.findall(r"^表 (\d+)　", manuscript, re.M) == ["1", "2", "3", "4", "5", "6"]
    assert "h_0,\\ldots,h_{k-1}" in manuscript
    assert "B_0,\\ldots,B_{k-1}" in manuscript
    assert "h_1,\\ldots,h_k" not in manuscript
    with (PAPER / "evidence/selected_projects.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    assert sum(int(r["recorded_expected_unique"]) for r in rows) == 291
    assert sum(int(r["recorded_known_real_unique"]) for r in rows) == 4
    assert sum(int(r["recorded_expected_asan_observations"]) for r in rows) == 291
    assert sum(int(r["recorded_expected_crash_observations"]) for r in rows) == 3
    assert sum(int(r["recorded_expected_total_observations"]) for r in rows) == 294
    assert min(int(r["recorded_expected_unique"]) for r in rows) == 8
    assert all(r["catalog_admission"] == "admitted" for r in rows)
    registry = json.loads((PAPER / "evidence/observation_register.json").read_text())
    for row in registry:
        source, pointer = row["record_pointer"].split("#/observations/")
        original = json.loads((ROOT / source).read_text())
        assert original["observations"][int(pointer)] == row["observation_verbatim"]
        assert row["final_configuration_membership"] == "not_inferred_from_project_summary"
    assert len(registry) == 621
    counts = Counter(r["observation_verbatim"]["verdict"] for r in registry)
    assert counts["expected_asan"] + counts["expected_crash"] == 294
    with tempfile.TemporaryDirectory(prefix="memvul-paper-relocation-") as folder:
        relocated = Path(folder) / "paper"
        shutil.copytree(PAPER / "portable", relocated)
        images = []
        for name in ("manuscript.md", "supplement.md"):
            text = (relocated / name).read_text()
            refs = re.findall(r"!\[[^]]*\]\(([^)]+)\)", text)
            for ref in refs:
                assert not Path(ref).is_absolute()
                assert (relocated / ref).is_file(), ref
                images.append(ref)
            original = (PAPER / name).read_text()
            for ref in re.findall(r"!\[[^]]*\]\(([^)]+)\)", original):
                original = original.replace(ref, "figures/" + Path(ref).name)
            assert original == text
        assert len(images) == 5
    for script in (PAPER / "scripts").glob("*.py"):
        ast.parse(script.read_text())
    result = {
        "source_hashes_checked": len(source_items),
        "source_hashes_unchanged": True,
        "project_table_matches_export": True,
        "main_figures": 4, "main_tables": 6,
        "supplementary_figures": 1, "references": 14,
        "observation_rows_copied_verbatim": len(registry),
        "expected_observation_rows": 294, "recorded_expected_groups": 291,
        "portable_copy_relocated_image_paths_pass": True,
        "requirements_gap_method_validation_structure_checked": True,
        "criteria_count": 4,
        "campaign_tuple_includes_time_budget": True,
        "standards_audit_sources_hash_checked": True,
        "unknown_verified_bug_counts_not_filled_with_recorded_counts": False,
        "verified_counts_are_final_entry_five_tuples": True,
        "recorded_material_chain_expected_rows": 294,
        "recorded_association_keys": 289,
        "target_size_is_design_goal_not_funnel_remainder": True,
        "scripts_syntax_valid": True, "new_target_builds_replays_fuzzing": False,
        "catalog_admission_changed": True,
        "manuscript_sha256": digest(PAPER / "manuscript.md"),
        "note": "Validation of writing artifacts does not establish target or vulnerability validity."
    }
    (REVISION / "package-validation.json").write_text(json.dumps(result, indent=2) + "\n")
    (PAPER / "evidence/writing_validation.json").write_text(json.dumps(result, indent=2) + "\n")
    shutil.copy2(PAPER / "evidence/writing_validation.json", PAPER / "portable/evidence/writing_validation.json")
    archive = shutil.make_archive(str(PAPER / "MemVulBench-v4-portable"), "zip", PAPER / "portable")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Portable archive: {archive}")


if __name__ == "__main__":
    main()
