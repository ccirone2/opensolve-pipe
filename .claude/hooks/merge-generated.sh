#!/bin/bash
# The `generated` merge driver (.gitattributes, docs/workflow.md §6), configured by
# session-start.sh as `merge-generated.sh %P`. Git calls it only for a file both sides changed.
# It keeps this branch's copy, which git already holds in the result file, and appends the path
# to a note in the git directory, so that pre-push.sh regenerates the file on the merged tree
# before the next push. A generated file is never merged line by line: its two halves would
# be neither side's output.
set -euo pipefail
path=$1
note="$(git rev-parse --git-dir)/opensolve-generated-merged"
grep -qxF -- "$path" "$note" 2>/dev/null || echo "$path" >> "$note"
