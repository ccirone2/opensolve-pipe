#!/bin/bash
# The `generated` merge driver (.gitattributes, docs/workflow.md §6), configured by
# session-start.sh as `merge-generated.sh %P %A %B`. Git calls it only for a file both sides
# changed. A generated file is never merged line by line (its two halves would be neither
# side's output): this keeps the branch's copy and notes the path in the git directory, and
# the coordination report then reminds the session to regenerate it on the merged tree.
#
# The branch's copy is %A (ours) in a merge, but %B in a rebase, where "ours" is the upstream
# the branch's commits are replayed onto.
set -euo pipefail
path=$1 ours=$2 theirs=$3
git_dir=$(git rev-parse --git-dir)
if [ -d "$git_dir/rebase-merge" ] || [ -d "$git_dir/rebase-apply" ]; then
  cp -- "$theirs" "$ours"
fi
note="$git_dir/opensolve-generated-merged"
grep -qxF -- "$path" "$note" 2>/dev/null || echo "$path" >> "$note"
