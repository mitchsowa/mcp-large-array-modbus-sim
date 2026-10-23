#!/usr/bin/env bash
# HARNESS FILE -- not part of the main program.
#
# Verify every provenance-tracked production file here is byte-identical to
# its counterpart on the main program's dev branch (upstream/dev). This is
# the "are we testing exactly what's on dev?" check, complementing
# check-provenance.sh (which only checks against the recorded local md5s).
#
# The file list is read straight from PROVENANCE.md5 so it never drifts.
# Path mapping: the program keeps source under src/, so each provenance
# path gets an "src/" prefix -- EXCEPT resources/... which lives at the
# program's repo root.
#
# Usage:   ./scripts/check-dev-sync.sh [remote] [branch]    (default: upstream dev)
#          NO_FETCH=1 ./scripts/check-dev-sync.sh           (skip git fetch)
# Exit 0 = every file matches dev. Exit 1 = drift (or missing remote/file).
set -euo pipefail
cd "$(dirname "$0")/.."

REMOTE="${1:-upstream}"
BRANCH="${2:-dev}"
REF="$REMOTE/$BRANCH"

if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
    echo "ERROR: remote '$REMOTE' not configured." >&2
    echo "  git remote add $REMOTE git@github.com:NyleWaterHeatingSystems/mcp-large-array.git" >&2
    exit 1
fi

if [ "${NO_FETCH:-0}" != "1" ]; then
    echo "fetching $REMOTE ..."
    git fetch --quiet "$REMOTE"
fi

if ! git rev-parse --verify --quiet "$REF" >/dev/null; then
    echo "ERROR: ref '$REF' not found (try a different branch arg)." >&2
    exit 1
fi

echo "comparing against $REF ($(git log -1 --format='%h %s' "$REF"))"
echo

drift=0
missing=0
checked=0
# second column of PROVENANCE.md5 is the local path
while read -r _md5 local; do
    [ -z "${local:-}" ] && continue
    case "$local" in
        resources/*) up="$local" ;;   # program keeps resources/ at repo root
        *)           up="src/$local" ;;
    esac
    checked=$((checked + 1))
    if ! git cat-file -e "$REF:$up" 2>/dev/null; then
        echo "MISSING-ON-DEV  $local  (expected $REF:$up)"
        missing=$((missing + 1))
        continue
    fi
    if diff -q <(git show "$REF:$up") "$local" >/dev/null 2>&1; then
        echo "OK      $local"
    else
        echo "DRIFT   $local  <- $REF:$up"
        drift=$((drift + 1))
    fi
done < PROVENANCE.md5

echo
if [ "$drift" -eq 0 ] && [ "$missing" -eq 0 ]; then
    echo "dev-sync: ALL $checked FILES MATCH $REF"
    exit 0
fi
echo "dev-sync: $drift drifted, $missing missing of $checked (see DRIFT/MISSING above)"
echo "to resync a file:  git show $REF:src/<path> > <local path>   then update PROVENANCE.md5"
exit 1
