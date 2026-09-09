#!/bin/bash
# Replay every PoC under /pocs against one harness build and print a TSV of
# (bug id, exit code, sanitizer verdict). Runs inside an ARVO container, where
# the OSS-Fuzz toolchain and llvm-symbolizer already live.
#
# usage: replay_in_container.sh <harness-binary> [timeout-seconds]
set -u
BIN="${1:?harness binary}"
TMO="${2:-25}"

export ASAN_OPTIONS='alloc_dealloc_mismatch=0:allocator_may_return_null=1:allocator_release_to_os_interval_ms=500:check_malloc_usable_size=0:detect_container_overflow=1:detect_odr_violation=0:detect_leaks=0:detect_stack_use_after_return=1:fast_unwind_on_fatal=0:handle_abort=1:handle_segv=1:handle_sigill=1:max_uar_stack_size_log=16:print_scariness=1:quarantine_size_mb=10:strict_memcmp=1:symbolize=1:use_sigaltstack=1:dedup_token_length=3'
export ASAN_SYMBOLIZER_PATH=/out/llvm-symbolizer

mkdir -p /reports
printf 'id\trc\tverdict\tkind\n'
for d in /pocs/*/; do
    id=$(basename "$d")
    log=/reports/${id}.log
    timeout -s KILL "$TMO" setarch -R "$BIN" "$d/poc" > "$log" 2>&1
    rc=$?
    if grep -q 'ERROR: AddressSanitizer' "$log"; then
        verdict=asan
        kind=$(sed -n 's/.*ERROR: AddressSanitizer: \([a-zA-Z0-9_-]*\).*/\1/p' "$log" | head -1)
    elif [ "$rc" -ge 128 ]; then
        verdict=signal
        kind="sig$((rc - 128))"
    elif [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; then
        verdict=timeout
        kind=-
    else
        verdict=clean
        kind=-
    fi
    printf '%s\t%s\t%s\t%s\n' "$id" "$rc" "$verdict" "${kind:--}"
done
