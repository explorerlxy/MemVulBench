"""Sanitizer report parsing.

Turns raw ASan/MSan/UBSan stderr into a structured record whose *signature*
is stable enough to match the same bug across two different builds of the
same project. Signatures deliberately exclude line/column numbers: a bug
re-introduced onto a newer base commit sits at the same function in the same
file, but rarely at the same line.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Iterable

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

_ERROR_RE = re.compile(
    r"==\d+==\s*ERROR:\s*(?P<san>\w+Sanitizer):\s*(?P<kind>[a-zA-Z0-9_-]+)"
    r"(?:\s+on (?:unknown )?address\s+(?P<addr>0x[0-9a-fA-F]+))?"
)
_SUMMARY_RE = re.compile(
    r"^SUMMARY:\s*(?P<san>\w+Sanitizer):\s*(?P<kind>[a-zA-Z0-9_-]+)", re.M
)
_UBSAN_RE = re.compile(
    r"^(?P<file>[^\s:]+):(?P<line>\d+):(?P<col>\d+):\s*runtime error:\s*(?P<msg>.+)$",
    re.M,
)
_ACCESS_RE = re.compile(r"^(?P<op>READ|WRITE) of size (?P<size>\d+) at", re.M)
_FRAME_RE = re.compile(r"^\s*#(?P<idx>\d+)\s+0x[0-9a-fA-F]+\s+in\s+(?P<rest>.+?)\s*$", re.M)
_LOC_RE = re.compile(
    r"^(?P<func>.*?)\s+(?P<file>[^\s]+\.(?:c|cc|cpp|cxx|cp|h|hh|hpp|hxx|inc|ipp|S|s))"
    r":(?P<line>\d+)(?::(?P<col>\d+))?$"
)
_OBJ_RE = re.compile(r"^(?P<func>.*?)\s+\((?P<obj>[^)]+?)\+0x[0-9a-fA-F]+\)$")

# Section headers that start a new frame group inside one report.
_SECTIONS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("alloc", re.compile(r"^(?:previously )?allocated by thread .* here:", re.I)),
    ("free", re.compile(r"^freed by thread .* here:", re.I)),
    ("alloc", re.compile(r"^allocated by thread .* here:", re.I)),
)

# Frames belonging to the runtime, the harness, or libc carry no information
# about *which* project bug fired; skip them when picking the crash site.
_NOISE = (
    "/compiler-rt/",
    "/llvm-project/",
    "sanitizer_common",
    "/libfuzzer/",
    "/fuzzer/",
    "asan_interceptors",
    "asan_rtl",
    "msan_interceptors",
    "interception/",
)
_NOISE_FUNC = (
    "__asan_",
    "__msan_",
    "__ubsan_",
    "__sanitizer",
    "__interceptor_",
    "LLVMFuzzerTestOneInput",
    "fuzzer::",
    "operator new",
    "operator delete",
    "malloc",
    "calloc",
    "realloc",
    "free",
    "memcpy",
    "memmove",
    "memset",
    "strcpy",
    "strlen",
)


@dataclass(frozen=True)
class Frame:
    idx: int
    func: str
    file: str | None = None
    line: int | None = None

    @property
    def is_project_code(self) -> bool:
        if self.file is None:
            return False
        if any(n in self.file for n in _NOISE):
            return False
        if any(self.func.startswith(n) or self.func == n for n in _NOISE_FUNC):
            return False
        return True

    def __str__(self) -> str:
        loc = f" {self.file}:{self.line}" if self.file else ""
        return f"#{self.idx} {self.func}{loc}"


@dataclass
class Report:
    """One parsed sanitizer report."""

    sanitizer: str | None = None
    kind: str | None = None
    access: str | None = None  # READ / WRITE
    access_size: int | None = None
    crash_frames: list[Frame] = field(default_factory=list)
    alloc_frames: list[Frame] = field(default_factory=list)
    free_frames: list[Frame] = field(default_factory=list)
    ubsan_msg: str | None = None

    @property
    def crash_site(self) -> Frame | None:
        return _first_project_frame(self.crash_frames)

    @property
    def alloc_site(self) -> Frame | None:
        return _first_project_frame(self.alloc_frames)

    @property
    def free_site(self) -> Frame | None:
        return _first_project_frame(self.free_frames)

    def signature(self) -> tuple[str, str, str, str]:
        """Build-independent identity of the bug.

        (kind, access, crash function, crash file basename). Line numbers are
        excluded on purpose so a bug matches across base commits.
        """
        site = self.crash_site
        return (
            self.kind or "unknown",
            self.access or "-",
            _norm_func(site.func) if site else "-",
            site.file.rsplit("/", 1)[-1] if site and site.file else "-",
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["signature"] = list(self.signature())
        for key in ("crash_site", "alloc_site", "free_site"):
            frame = getattr(self, key)
            d[key] = str(frame) if frame else None
        return d


def _first_project_frame(frames: Iterable[Frame]) -> Frame | None:
    for f in frames:
        if f.is_project_code:
            return f
    for f in frames:  # fall back to anything with a source location
        if f.file:
            return f
    return None


def _norm_func(func: str) -> str:
    """Drop C++ template/overload noise so the same function matches itself."""
    func = re.sub(r"<[^<>]*>", "<>", func)
    func = re.sub(r"\((?:anonymous namespace)\)::", "", func)
    return func.split("(")[0].strip()


def _parse_frame(idx: int, rest: str) -> Frame:
    if (m := _LOC_RE.match(rest)) is not None:
        return Frame(idx, m["func"].strip(), m["file"], int(m["line"]))
    if (m := _OBJ_RE.match(rest)) is not None:
        return Frame(idx, m["func"].strip())
    return Frame(idx, rest.strip())


def parse(raw: str, max_chars: int = 200_000) -> Report:
    """Parse the first sanitizer report found in ``raw``."""
    text = ANSI_RE.sub("", raw.replace("\r\n", "\n").replace("\r", "\n"))[:max_chars]
    rep = Report()

    if (m := _ERROR_RE.search(text)) is not None:
        rep.sanitizer, rep.kind = m["san"], m["kind"].lower()
    elif (m := _SUMMARY_RE.search(text)) is not None:
        rep.sanitizer, rep.kind = m["san"], m["kind"].lower()
    elif (m := _UBSAN_RE.search(text)) is not None:
        rep.sanitizer, rep.kind = "UndefinedBehaviorSanitizer", "runtime-error"
        rep.ubsan_msg = m["msg"].strip()
        rep.crash_frames = [Frame(0, "-", m["file"], int(m["line"]))]
        return rep
    else:
        return rep

    if (m := _ACCESS_RE.search(text)) is not None:
        rep.access, rep.access_size = m["op"], int(m["size"])

    # Frames arrive as "#0 #1 #2 ... #0 #1 ..."; a reset to #0 or a section
    # header starts a new group. Sections are labelled by the nearest header.
    bucket = "crash"
    buckets: dict[str, list[Frame]] = {"crash": [], "alloc": [], "free": []}
    for line in text.split("\n"):
        for name, pat in _SECTIONS:
            if pat.match(line.strip()):
                bucket = name
                break
        else:
            if (m := _FRAME_RE.match(line)) is not None:
                idx = int(m["idx"])
                if idx == 0 and buckets[bucket]:
                    # A second #0 with no header in between: ASan prints the
                    # shadow/thread trace after the main one. Keep the first.
                    bucket = "_drop"
                    buckets.setdefault("_drop", [])
                buckets[bucket].append(_parse_frame(idx, m["rest"]))

    rep.crash_frames = buckets["crash"]
    rep.alloc_frames = buckets["alloc"]
    rep.free_frames = buckets["free"]
    return rep
