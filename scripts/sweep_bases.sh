#!/bin/bash
# Empirical natural-density curve: for each candidate base, build the project
# *unpatched* and count how many PoCs still crash. This replaces the SZZ
# estimate with a measurement -- a bug is latent at a base if and only if its
# PoC fires there.
#
# Runs inside an ARVO container. usage: sweep_bases.sh <base-sha>...
set -u
SRCDIR=${SRCDIR:-/src/assimp}
RESULTS=/reports/sweep.tsv
printf 'base\tdate\tcrash\tclean\tcrashers\n' > "$RESULTS"

for base in "$@"; do
    cd "$SRCDIR" || exit 1
    git checkout -q --force --detach "$base" 2>/dev/null || { echo "SKIP $base"; continue; }
    git reset --hard --quiet "$base"
    day=$(git show -s --format=%cs "$base")

    export OUT=/out/sweep FUZZING_ENGINE=libfuzzer SANITIZER=address \
           FUZZING_LANGUAGE=c++ ARCHITECTURE=x86_64
    rm -rf /out/sweep && mkdir -p /out/sweep
    if ! compile > "/tmp/compile_${base}.log" 2>&1; then
        printf '%s\t%s\tBUILD_FAIL\t-\t-\n' "$base" "$day" >> "$RESULTS"
        echo "BUILD_FAIL $base $day"
        continue
    fi

    out=$(/replay.sh "/out/sweep/$(ls /out/sweep | grep -v llvm-symbolizer | head -1)" 25)
    crash=$(echo "$out" | awk 'NR>1 && ($3=="asan" || $3=="signal")' | wc -l)
    clean=$(echo "$out" | awk 'NR>1 && $3=="clean"' | wc -l)
    who=$(echo "$out" | awk 'NR>1 && ($3=="asan" || $3=="signal"){printf "%s,",$1}')
    printf '%s\t%s\t%s\t%s\t%s\n' "$base" "$day" "$crash" "$clean" "$who" >> "$RESULTS"
    echo "$base $day crash=$crash clean=$clean"
done

echo "--- results ---"
cat "$RESULTS"
