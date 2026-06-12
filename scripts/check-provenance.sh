#!/usr/bin/env bash
# Verify the production files are byte-identical to the recorded checksums.
# Run after any task to confirm nothing verbatim was touched accidentally;
# if a production fix was intentional, update PROVENANCE.md5 in the same
# commit and note the change flows back to the main program.
cd "$(dirname "$0")/.."
md5sum -c PROVENANCE.md5
