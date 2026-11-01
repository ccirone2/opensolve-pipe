#!/bin/bash
# The coordination report for parallel sessions (docs/workflow.md §6), run by
# session-start.sh and by pre-push.sh.
#
# Prints where HEAD stands against origin/main, the other session branches on origin, the next
# decision number and METHOD_VERSION on HEAD and on main. Parallel sessions each take "the next
# free" number on their own branch, and the second to merge renumbers (docs/workflow.md §5;
# D20–D23 were each renumbered so). Reads committed state (HEAD), which is what a push sends.
#
# Exit status: 0, or 3 when it found a collision, a decision number or a method version that
# both HEAD and origin/main took since they parted. Network failures are reported, never fatal.
#
# Its output reaches the session as context, so it prints only branch names, counts and
# numbers, never commit messages or file contents.
set -euo pipefail

cd "${CLAUDE_PROJECT_DIR:-.}"
collision=0
branch=$(git rev-parse --abbrev-ref HEAD)
echo "Session coordination (.claude/hooks/coordination.sh, docs/workflow.md §6):"

if ! timeout 30 git fetch --quiet origin main 2>/dev/null; then
  echo "- Could not fetch origin/main; the numbers below may be stale."
fi
have_main=false
git rev-parse --verify --quiet origin/main >/dev/null && have_main=true

if $have_main; then
  read -r behind ahead < <(git rev-list --left-right --count origin/main...HEAD)
  echo "- Branch ${branch}: ${ahead} commit(s) ahead of origin/main, ${behind} behind."
  if [ "$behind" -gt 0 ] && [ "$ahead" -eq 0 ]; then
    echo "  It holds no work of its own: fast-forward it first (git merge --ff-only origin/main)."
  elif [ "$behind" -gt 0 ]; then
    echo "  Merge origin/main before building on it, and again before asking for a merge."
  fi
fi

if heads=$(timeout 20 git ls-remote --heads origin 2>/dev/null); then
  others=$(awk '{sub("refs/heads/", "", $2); print $2}' <<<"$heads" \
    | grep -E '^(claude|web)/' | grep -vxF "$branch" || true)
  if [ -n "$others" ]; then
    echo "- Other session branches on origin (check their open PRs before taking a number):"
    while read -r b; do echo "    ${b}"; done <<<"$others"
  else
    echo "- No other claude/* or web/* branches on origin."
  fi
else
  echo "- Could not list origin's branches."
fi

# Decision files (Dnn-<slug>.md) on a commit, and the highest number among them.
decision_files() {
  git ls-tree --name-only "$1" docs/decisions/ | sed 's|.*/||' | grep -E '^D[0-9]{2}-.*\.md$' \
    || true
}
highest_decision() { grep -oE '^D[0-9]{2}' | sort -u | tail -1 | tr -dc '0-9' | sed 's/^0*//'; }
here=$(decision_files HEAD | highest_decision)
on_main=
$have_main && on_main=$(decision_files origin/main | highest_decision)
next=$(( ${here:-0} > ${on_main:-0} ? ${here:-0} : ${on_main:-0} ))
echo "- Decisions: D${here:-0} is the highest here, D${on_main:-?} on origin/main;" \
  "a new one takes D$(( next + 1 )) unless an open branch has it."
if [ -n "$on_main" ]; then
  # A number this branch holds that main has given to another decision.
  low=$(( on_main < ${here:-0} ? on_main : ${here:-0} ))
  for n in $(seq "$low" "${here:-0}"); do
    [ "$n" -gt 0 ] || continue
    nn=$(printf 'D%02d-' "$n")
    mine=$(decision_files HEAD | grep "^${nn}" || true)
    theirs=$(decision_files origin/main | grep "^${nn}" || true)
    if [ -n "$mine" ] && [ -n "$theirs" ] && [ "$mine" != "$theirs" ]; then
      echo "  Collision: ${mine} here, ${theirs} on origin/main. Renumber this branch's."
      collision=1
    fi
  done
fi

version_file=apps/api/src/opensolve_pipe/services/solver/version.py
method_version() { grep -oE '^METHOD_VERSION = "[0-9.]+"' | grep -oE '[0-9.]+[0-9]' || true; }
v_here=$(git show "HEAD:${version_file}" 2>/dev/null | method_version)
if $have_main; then
  v_main=$(git show "origin/main:${version_file}" 2>/dev/null | method_version)
  echo "- METHOD_VERSION: ${v_here:-unknown} here, ${v_main:-unknown} on origin/main."
  # Both sides moved it since they parted (to the same number or not): this branch's changes
  # need the next version after main's, with its own changelog entry.
  base=$(git merge-base origin/main HEAD 2>/dev/null || true)
  v_base=
  [ -n "$base" ] && v_base=$(git show "${base}:${version_file}" 2>/dev/null | method_version)
  if [ -n "$v_base" ] && [ -n "$v_main" ] && [ "$v_base" != "$v_main" ] \
    && [ "$v_base" != "${v_here:-}" ]; then
    echo "  Both this branch and main moved it from ${v_base}: renumber this branch's."
    collision=1
  fi
else
  echo "- METHOD_VERSION: ${v_here:-unknown}."
fi

[ "$collision" -eq 0 ] || exit 3
