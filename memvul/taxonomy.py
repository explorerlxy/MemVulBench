"""Vulnerability classification.

Maps an OSS-Fuzz / ASan ``crash_type`` string onto the class hierarchy
MemVulBench selects on. ``CORE`` is the benchmark's subject matter: spatial
and temporal memory-safety violations. ``EXTENDED`` is memory-related but
either not a safety violation (uninitialised reads) or not reliably a
memory-safety bug at the C abstract-machine level (wild SEGV, bad cast).
Everything else is out of scope.
"""

from __future__ import annotations

import re
from typing import NamedTuple


class VulnClass(NamedTuple):
    tier: str  # core | extended | out
    group: str  # spatial | temporal | uninit | typeconf | nullptr | other
    cwe: str
    label: str


_RULES: tuple[tuple[re.Pattern[str], VulnClass], ...] = (
    # --- core: spatial ------------------------------------------------------
    (re.compile(r"^Heap-buffer-overflow WRITE", re.I),
     VulnClass("core", "spatial", "CWE-787", "heap-oob-write")),
    (re.compile(r"^Heap-buffer-overflow READ", re.I),
     VulnClass("core", "spatial", "CWE-125", "heap-oob-read")),
    (re.compile(r"^Stack-buffer-(?:over|under)flow WRITE", re.I),
     VulnClass("core", "spatial", "CWE-787", "stack-oob-write")),
    (re.compile(r"^Stack-buffer-(?:over|under)flow READ", re.I),
     VulnClass("core", "spatial", "CWE-125", "stack-oob-read")),
    (re.compile(r"^Dynamic-stack-buffer-overflow WRITE", re.I),
     VulnClass("core", "spatial", "CWE-787", "dynstack-oob-write")),
    (re.compile(r"^Dynamic-stack-buffer-overflow READ", re.I),
     VulnClass("core", "spatial", "CWE-125", "dynstack-oob-read")),
    (re.compile(r"^Global-buffer-overflow WRITE", re.I),
     VulnClass("core", "spatial", "CWE-787", "global-oob-write")),
    (re.compile(r"^Global-buffer-overflow READ", re.I),
     VulnClass("core", "spatial", "CWE-125", "global-oob-read")),
    (re.compile(r"^Container-overflow WRITE", re.I),
     VulnClass("core", "spatial", "CWE-787", "container-oob-write")),
    (re.compile(r"^Container-overflow READ", re.I),
     VulnClass("core", "spatial", "CWE-125", "container-oob-read")),
    (re.compile(r"^Negative-size-param", re.I),
     VulnClass("core", "spatial", "CWE-787", "negative-size")),
    (re.compile(r"^Memcpy-param-overlap", re.I),
     VulnClass("core", "spatial", "CWE-475", "overlapping-memcpy")),
    (re.compile(r"^Calloc-overflow|^Allocation-size-too-big", re.I),
     VulnClass("core", "spatial", "CWE-190", "alloc-size-overflow")),
    # --- core: temporal -----------------------------------------------------
    (re.compile(r"^Heap-use-after-free", re.I),
     VulnClass("core", "temporal", "CWE-416", "use-after-free")),
    (re.compile(r"^Use-after-poison", re.I),
     VulnClass("core", "temporal", "CWE-416", "use-after-poison")),
    (re.compile(r"^Stack-use-after-(?:return|scope)", re.I),
     VulnClass("core", "temporal", "CWE-562", "stack-use-after-return")),
    (re.compile(r"^Heap-double-free|^Attempting double-free", re.I),
     VulnClass("core", "temporal", "CWE-415", "double-free")),
    (re.compile(r"^Invalid-free|^Bad-free", re.I),
     VulnClass("core", "temporal", "CWE-590", "invalid-free")),
    (re.compile(r"^Unknown-crash", re.I),
     VulnClass("core", "spatial", "CWE-787", "unknown-crash")),
    # --- extended -----------------------------------------------------------
    (re.compile(r"^Use-of-uninitialized-value", re.I),
     VulnClass("extended", "uninit", "CWE-457", "uninitialised-read")),
    (re.compile(r"^Bad-cast", re.I),
     VulnClass("extended", "typeconf", "CWE-843", "type-confusion")),
    (re.compile(r"^Null-dereference", re.I),
     VulnClass("extended", "nullptr", "CWE-476", "null-deref")),
    (re.compile(r"^Index-out-of-bounds", re.I),
     VulnClass("extended", "spatial", "CWE-125", "ubsan-bounds")),
    (re.compile(r"^Segv on unknown address|^UNKNOWN (?:READ|WRITE)", re.I),
     VulnClass("extended", "other", "CWE-787", "wild-access")),
    # --- out of scope -------------------------------------------------------
    (re.compile(r"leak|^Timeout|^Out-of-memory|^Stack-overflow|"
                r"^Integer-overflow|^Divide-by-zero|^Float-cast-overflow|"
                r"^Misaligned-address|^Undefined-shift|^Object-size|"
                r"^Non-positive-vla|^Invalid-bool-value|^Invalid-enum-value|"
                r"^Pointer-overflow|^Builtin-unreachable|^Missing-library|"
                r"^Security check failure|^ASSERT|^CHECK failure|^Fatal error",
                re.I),
     VulnClass("out", "other", "-", "out-of-scope")),
)

_UNKNOWN = VulnClass("out", "other", "-", "unclassified")


def classify(crash_type: str | None) -> VulnClass:
    if not crash_type:
        return _UNKNOWN
    for pat, cls in _RULES:
        if pat.search(crash_type.strip()):
            return cls
    return _UNKNOWN
