#!/bin/bash
# One sweep probe: checkout an unmodified upstream commit, compile, replay
# every PoC. Runs inside an ARVO container.
#
# usage: sweep_probe.sh <commit-sha>
# env:   SRCDIR  HARNESS  TMO  POCS
set -u
SHA="${1:?commit}"
SRCDIR=${SRCDIR:-/src/assimp}
HARNESS=${HARNESS:-assimp_fuzzer}
TMO=${TMO:-15}
POCS=${POCS:-/pocs}
DEST=/reports/sweep/${SHA}

mkdir -p "$DEST"
cd "$SRCDIR" || { echo BUILD_FAIL > "$DEST/status"; exit 0; }

git revert --quit >/dev/null 2>&1 || true
if ! git checkout -q --force --detach "$SHA"; then
    echo "SKIP checkout $SHA" | tee -a "$DEST/compile.log"
    echo BUILD_FAIL > "$DEST/status"
    exit 0
fi
git reset --hard --quiet "$SHA"
git clean -qfd
rm -rf CMakeCache.txt CMakeFiles lib bin build.ninja .ninja_deps .ninja_log

export OUT=/out/sweep FUZZING_ENGINE=libfuzzer SANITIZER=address \
       FUZZING_LANGUAGE=c++ ARCHITECTURE=x86_64
rm -rf /out/sweep && mkdir -p /out/sweep
if [ -x /out/llvm-symbolizer ]; then
    cp -f /out/llvm-symbolizer /out/sweep/
fi

if ! compile > "$DEST/compile.log" 2>&1; then
    echo BUILD_FAIL > "$DEST/status"
    echo "BUILD_FAIL $SHA"
    exit 0
fi

BIN=/out/sweep/$HARNESS
if [ ! -x "$BIN" ]; then
    cand=$(ls /out/sweep | grep -v llvm-symbolizer | head -1)
    BIN=/out/sweep/$cand
fi
if [ ! -x "$BIN" ]; then
    echo BUILD_FAIL > "$DEST/status"
    echo "BUILD_FAIL $SHA no harness"
    exit 0
fi

REPORTS="$DEST" POCS="$POCS" /replay.sh "$BIN" "$TMO" > "$DEST/replay.tsv"
echo OK > "$DEST/status"
echo "OK $SHA"
cat "$DEST/replay.tsv"
