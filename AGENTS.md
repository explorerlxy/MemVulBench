# Repository Guidelines

## Project Structure & Module Organization

`memvul/` contains the Python 3 CLI and catalog/data utilities. `catalog/` is
the phase-one, human- and machine-readable target catalog; `data/` stores
census, candidate, download, and manually recorded measurement artifacts.
`docs/` contains design and data-contract notes. `targets/` is reserved for
materialized benchmark targets. Keep clones, PoCs, images, builds, and logs on
ext4 under `/tmp/memvul` or the persistent archive directories, never in Git.

## Build, Test, and Development Commands

There is no package or build-system configuration. Use these local checks:

```bash
python3 -m memvul --help
python3 -m compileall -q memvul
python3 -m memvul --db /path/to/arvo.db census
```

The first two commands validate CLI wiring and Python syntax; `census` checks
ARVO ingestion. PoC and image acquisition may use the dedicated background
downloader, but it must not compile targets or execute PoCs.

## Manual Compilation and Replay

Compilation, PoC replay, ASan signature analysis, and catalog admission are
operator-only activities. Do not add or invoke scripts, batch runners, or CLI
subcommands that automate them. Execute one command at a time inside the
selected ARVO container, inspect its output, and record the result under
`data/measure/` with logs outside Git. Confirm the exact source directory,
checked-out upstream commit, harness binary, PoC ID, exit status, and ASan
signature before accepting a result. Starting a foreground replay still
requires at least 8 catalog PoCs at the project level (across harnesses).
Final benchmark admission counts unique verified memory vulnerabilities:
unique expected fingerprints plus unique `known_real`. At least 8 enter
the benchmark; fewer than 6 is a direct pass; 6–7 is deferred unless
explicitly reviewed.

## Coding Style & Naming Conventions

Use four-space indentation, type hints, focused functions, `snake_case` for
functions and variables, and `PascalCase` for classes. Preserve deterministic
JSON/YAML output and existing field names. Keep changes `compileall`-clean;
no formatter or linter is configured.

## Commit & Pull Request Guidelines

Use concise imperative commit subjects, keep commits focused, and describe
data or methodological impact. PRs should list validation commands, generated
artifacts, and any Docker, network, or ARVO requirements.

## Data and Reproducibility

Derive catalog truth from ARVO metadata and manually reviewed observations.
Targets must remain unmodified upstream commits. Never commit PoCs,
credentials, container layers, or transient logs.
