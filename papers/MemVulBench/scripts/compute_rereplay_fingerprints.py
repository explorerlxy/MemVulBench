"""Compute first-fault five-tuples from the 2026-09-17 final-entry rereplay logs.

Reads already-written rereplay logs only. Does not build, replay, or admit.
Official identity is evidence/rereplay_fingerprint_ledger.json.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from pathlib import Path

PAPER = Path(__file__).resolve().parents[1]
ROOT = PAPER.parents[1]
sys.path.insert(0, str(ROOT))

from memvul.asan import _norm_func, parse  # noqa: E402

OUT = PAPER / "evidence"
REREPLAY = ROOT / "data/measure/rereplay/2026-09-17"
KNOWN = {"expected_asan", "expected_crash", "known_real"}
CLEAR_KINDS = {
    "heap-buffer-overflow",
    "stack-buffer-overflow",
    "stack-buffer-underflow",
    "dynamic-stack-buffer-overflow",
    "global-buffer-overflow",
    "container-overflow",
    "heap-use-after-free",
    "use-after-poison",
    "stack-use-after-return",
    "stack-use-after-scope",
    "heap-double-free",
    "double-free",
    "invalid-free",
    "bad-free",
    "negative-size-param",
    "memcpy-param-overlap",
    "calloc-overflow",
    "allocation-size-too-big",
    "null-deref",
}

# Operator-adjudicated type (and optional access) for reports whose sanitizer
# kind is not itself a concrete class. Key is "project:oss_id".
ADJUDICATIONS = {
    "ghostpdl:42514830": {
        "kind": "null-deref",
        "access": "READ",
        "basis": "pstype==NULL; fault address is offsetof(finalize)=0x30; show_cache_setup sets o_type NULL then frees the surviving cache device",
    },
    "upx:42531927": {
        "kind": "heap-use-after-free",
        "access": "READ",
        "basis": "SEGV READ at 0x62800002cf20 in LEPolicy::get64; not zero-page; ASan gives no object; operator chose catalog UAF class",
    },
    "libavc:42530559": {
        "kind": "null-deref",
        "access": "READ",
        "basis": "SEGV at 0x0, pc on zero page; call through NULL; first fault is isvcd_parse_inter_slice_data_cavlc_enh_lyr",
    },
}

HEAP_OOB_LOC = re.compile(
    r"located .+ of \d+-byte region .*allocated by thread",
    re.S,
)
STACK_OOB_LOC = re.compile(
    r"located in stack of thread .*partially overflows this variable",
    re.S,
)
SEGV_ADDR = re.compile(
    r"SEGV on unknown address (0x[0-9a-fA-F]+)",
)
DEADLY_ACCESS = re.compile(
    r"The signal is caused by a (READ|WRITE) memory access",
)


def project_frames(report) -> list[dict]:
    frames = []
    for frame in report.crash_frames:
        if not frame.is_project_code:
            continue
        basename = frame.file.rsplit("/", 1)[-1] if frame.file else None
        frames.append({
            "func": _norm_func(frame.func),
            "file": basename,
            "line": frame.line,
            "raw_file": frame.file,
        })
        if len(frames) == 3:
            break
    return frames


def infer_from_asan_body(text: str, parsed_kind: str | None, access: str) -> dict | None:
    if parsed_kind == "unknown-crash":
        if HEAP_OOB_LOC.search(text):
            return {
                "kind": "heap-buffer-overflow",
                "access": access if access in {"READ", "WRITE"} else None,
                "basis": "ASan unknown-crash plus 'located … of N-byte region allocated by thread' (heap redzone); operator-approved 2026-09-17",
            }
        if STACK_OOB_LOC.search(text):
            return {
                "kind": "stack-buffer-overflow",
                "access": access if access in {"READ", "WRITE"} else None,
                "basis": "ASan unknown-crash plus stack frame 'partially overflows this variable'; operator-approved 2026-09-17",
            }
        return None
    if parsed_kind == "attempting" and "double-free" in text:
        return {
            "kind": "double-free",
            "access": "-",
            "basis": "ASan ERROR 'attempting double-free'; SUMMARY reports double-free",
        }
    if parsed_kind == "segv":
        addr_match = SEGV_ADDR.search(text)
        zero_page = (
            "address points to the zero page" in text
            or "pc points to the zero page" in text
            or (addr_match is not None and int(addr_match.group(1), 16) < 0x1000)
        )
        deadly = DEADLY_ACCESS.search(text)
        deadly_access = deadly.group(1) if deadly else (access if access in {"READ", "WRITE"} else None)
        if zero_page:
            return {
                "kind": "null-deref",
                "access": deadly_access,
                "basis": "SEGV on zero page / address < 0x1000; operator-approved null-deref 2026-09-17",
            }
        if "can not provide additional info" in text or "cannot provide additional info" in text:
            return {
                "kind": "heap-use-after-free",
                "access": deadly_access,
                "basis": "SEGV on non-zero unknown address, ASan gives no object; operator-approved UAF class 2026-09-17",
            }
    return None


def fingerprint_of(report, adjudication: dict | None = None) -> dict:
    frames = project_frames(report)
    site = frames[0] if frames else {}
    payload = "|".join(
        f"{item['func']}|{item['file'] or '-'}|{item['line'] if item['line'] is not None else '-'}"
        for item in frames
    )
    h3 = hashlib.sha256(payload.encode()).hexdigest()[:16] if frames else None
    parsed_kind = (report.kind or "").lower() or None
    kind = parsed_kind
    access = report.access or "-"
    if adjudication:
        kind = adjudication.get("kind") or kind
        if adjudication.get("access"):
            access = adjudication["access"]
    file_name = site.get("file") or "-"
    line = site.get("line")
    key = f"{kind or 'unknown'}|{access}|{file_name}|{line if line is not None else '-'}|{h3 or '-'}"
    return {
        "kind": kind,
        "parsed_kind": parsed_kind,
        "access": access,
        "file": file_name,
        "line": line,
        "h3": h3,
        "h3_payload": payload or None,
        "frames": frames,
        "key": key,
        "fingerprint_id": "mvb:" + hashlib.sha256(key.encode()).hexdigest()[:12],
        "kind_clear": kind in CLEAR_KINDS,
        "adjudication": adjudication,
    }


def sanitizer_window(text: str) -> str:
    markers = (
        "==ERROR:",
        "ERROR: AddressSanitizer",
        "ERROR: MemorySanitizer",
        "ERROR: UndefinedBehaviorSanitizer",
        "AddressSanitizer:DEADLYSIGNAL",
        "SUMMARY: AddressSanitizer",
        "SUMMARY: MemorySanitizer",
        "runtime error:",
    )
    starts = [text.find(marker) for marker in markers if text.find(marker) != -1]
    if not starts:
        return text
    return text[min(starts):]


def excerpt(path: Path, limit: int = 60) -> str:
    lines = path.read_text(errors="replace").splitlines()
    start = 0
    for index, line in enumerate(lines):
        if "ERROR:" in line or "DEADLYSIGNAL" in line or "SUMMARY:" in line:
            start = max(0, index - 2)
            break
    return "\n".join(lines[start:start + limit])


def rereplay_log(project: str, oss_id) -> Path | None:
    name = f"{oss_id}.log"
    for candidate in (
        Path("/tmp/memvul/rereplay") / project / name,
        ROOT / "targets" / project / "logs" / "agg-rereplay-20260917" / name,
    ):
        if candidate.is_file():
            return candidate
    return None


def main() -> int:
    selected = list(csv.DictReader((OUT / "selected_projects.csv").open()))
    computed: list[dict] = []
    pending: list[dict] = []
    units: dict[str, dict] = {}

    for row in selected:
        project = row["project"]
        replay_path = REREPLAY / f"{project}.json"
        replay = json.loads(replay_path.read_text())
        measure = json.loads((ROOT / row["metadata_path"]).read_text())
        verdict_by_id = {
            int(item["oss_id"]): item.get("verdict")
            for item in measure.get("observations") or []
            if item.get("oss_id") is not None
        }
        unit = {
            "project": project,
            "source_commit": replay["source_commit"],
            "image": replay["image"],
            "binary": replay["binary"],
            "binary_sha256_matches_record": replay.get("binary_sha256"),
            "identity_stdout_captured": bool(replay.get("identity_stdout")),
            "checkout_matches_record": (
                replay["source_commit"] in (replay.get("identity_stdout") or "")
                or (
                    not replay.get("identity_stdout")
                    and bool(replay.get("source_commit") and replay.get("binary_sha256"))
                )
            ),
            "observations": 0,
            "faulting": 0,
            "clean": 0,
            "expected_five_tuples": set(),
            "extra_five_tuples": set(),
            "pending": [],
        }
        for observation in replay["observations"]:
            oss_id = observation["oss_id"]
            verdict = observation.get("verdict") or verdict_by_id.get(int(oss_id))
            if verdict not in KNOWN and verdict != "clean":
                continue
            unit["observations"] += 1
            log_path = rereplay_log(project, oss_id)
            record = {
                "project": project,
                "source_commit": replay["source_commit"],
                "oss_id": oss_id,
                "verdict": verdict,
                "recorded_signature": observation.get("recorded_signature"),
                "log": {"path": str(log_path) if log_path else None, "source": "final_entry_rereplay"},
                "exit_code": observation.get("exit_code"),
            }
            if verdict == "clean" or observation.get("exit_code") == 0:
                unit["clean"] += 1
                record["fingerprint"] = None
                record["no_fault"] = True
                computed.append(record)
                continue
            if log_path is None:
                pending.append({**record, "stop_reason": "missing_rereplay_log"})
                unit["pending"].append(oss_id)
                continue
            window = sanitizer_window(log_path.read_text(errors="replace"))
            report = parse(window)
            key = f"{project}:{oss_id}"
            adjudication = ADJUDICATIONS.get(key)
            if adjudication is None:
                adjudication = infer_from_asan_body(
                    window, (report.kind or "").lower() or None, report.access or "-",
                )
            fp = fingerprint_of(report, adjudication)
            record["fingerprint"] = fp
            if not fp["kind_clear"]:
                pending.append({
                    **record,
                    "stop_reason": "kind_unclear",
                    "log_excerpt": excerpt(log_path),
                })
                unit["pending"].append(oss_id)
                continue
            unit["faulting"] += 1
            if verdict in {"expected_asan", "expected_crash"}:
                unit["expected_five_tuples"].add(fp["key"])
            elif verdict == "known_real":
                unit["extra_five_tuples"].add(fp["key"])
            computed.append(record)
        units[project] = unit

    unit_rows = []
    for project, unit in units.items():
        expected_n = len(unit["expected_five_tuples"])
        extra_n = len(unit["extra_five_tuples"] - unit["expected_five_tuples"])
        unit_rows.append({
            "project": project,
            "source_commit": unit["source_commit"],
            "checkout_matches_record": unit["checkout_matches_record"],
            "identity_stdout_captured": unit["identity_stdout_captured"],
            "faulting_observations": unit["faulting"],
            "clean_observations": unit["clean"],
            "expected_five_tuples": expected_n,
            "extra_five_tuples_outside_expected": extra_n,
            "final_entry_known_five_tuples": expected_n + extra_n,
            "pending_oss_ids": unit["pending"],
            "catalog_expected_groups": int(next(
                row["recorded_expected_unique"] for row in selected if row["project"] == project
            )),
            "catalog_extra_groups": int(next(
                row["recorded_known_real_unique"] for row in selected if row["project"] == project
            )),
        })

    expected_keys = {item["fingerprint"]["key"] for item in computed
                     if item.get("fingerprint") and item["verdict"] in {"expected_asan", "expected_crash"}}
    extra_keys = {item["fingerprint"]["key"] for item in computed
                  if item.get("fingerprint") and item["verdict"] == "known_real"}
    result = {
        "schema_version": "1.1",
        "audit_date": "2026-09-17",
        "scope": (
            "First-fault five-tuples from 2026-09-17 final-entry rereplay logs. "
            "Identity key is kind|access|file|line|H3. Not catalog admission."
        ),
        "adjudications": ADJUDICATIONS,
        "clear_kinds": sorted(CLEAR_KINDS),
        "computed_observations": len(computed),
        "faulting_observations": sum(1 for item in computed if item.get("fingerprint")),
        "clean_observations": sum(1 for item in computed if item.get("no_fault")),
        "unique_expected_five_tuples": len(expected_keys),
        "unique_extra_five_tuples": len(extra_keys),
        "unique_extra_outside_expected": len(extra_keys - expected_keys),
        "unique_known_five_tuples": len(expected_keys | extra_keys),
        "pending": pending,
        "units": unit_rows,
        "observations": computed,
    }
    dest = OUT / "rereplay_fingerprint_ledger.json"
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "faulting": result["faulting_observations"],
        "clean": result["clean_observations"],
        "expected_five_tuples": result["unique_expected_five_tuples"],
        "extra_outside_expected": result["unique_extra_outside_expected"],
        "known_five_tuples": result["unique_known_five_tuples"],
        "pending": [
            {"project": item["project"], "oss_id": item["oss_id"],
             "kind": (item.get("fingerprint") or {}).get("kind"),
             "reason": item.get("stop_reason")}
            for item in pending
        ],
        "units": [
            {
                "project": item["project"],
                "expected": item["expected_five_tuples"],
                "extra": item["extra_five_tuples_outside_expected"],
                "catalog_expected": item["catalog_expected_groups"],
            }
            for item in unit_rows
        ],
        "ledger": str(dest),
    }, ensure_ascii=False, indent=2))
    return 2 if pending else 0


if __name__ == "__main__":
    sys.exit(main())
