#!/bin/bash
# SessionStart hook for Claude Code cloud sessions (docs/workflow.md §6).
#
# 1. Installs the API's and the web app's dependencies when a lockfile changed since the last
#    install, so the gates (CLAUDE.md, Tooling) run at once.
# 2. Prints where this branch stands against main and what other sessions have in flight: the
#    other session branches, and the decision number and method version this branch would take.
#    Parallel sessions each take "the next free" number on their own branch, and the second to
#    merge renumbers (docs/workflow.md §5; D20–D23 were each renumbered so); knowing at the
#    start is cheaper than at merge.
#
# Its stdout reaches the session as context, so it prints only branch names, counts and
# numbers, never commit messages or file contents.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"
hook=.claude/hooks/session-start.sh

# --- Dependencies: each install runs only if a file that decides it changed since it last
# succeeded. The hash file lives in the git-ignored directory the install fills, and is written
# only after a successful install, so a failed one runs again next time. A failure is reported
# and makes the hook exit non-zero, after the coordination report below.
failed=()
api_hashes=apps/api/.venv/.session-start.sha256
if ! sha256sum --check --status "$api_hashes" 2>/dev/null; then
  rm -f "$api_hashes"
  if (cd apps/api && uv sync --locked --quiet) >&2; then
    sha256sum "$hook" apps/api/pyproject.toml apps/api/uv.lock apps/api/.python-version \
      > "$api_hashes"
  else
    failed+=("API dependencies (cd apps/api && uv sync --locked)")
  fi
fi

web_hashes=apps/web/node_modules/.session-start.sha256
if ! sha256sum --check --status "$web_hashes" 2>/dev/null; then
  rm -f "$web_hashes"
  if (cd apps/web && pnpm install --frozen-lockfile --reporter=silent) >&2; then
    sha256sum "$hook" apps/web/package.json apps/web/pnpm-lock.yaml > "$web_hashes"
  else
    failed+=("web dependencies (cd apps/web && pnpm install --frozen-lockfile)")
  fi
fi

# --- Coordination report: best effort. A network failure must not hold up the session, so
# every remote call has a timeout and its failure is reported, not fatal.
branch=$(git rev-parse --abbrev-ref HEAD)
echo "Session coordination (.claude/hooks/session-start.sh, docs/workflow.md §6):"

if ! timeout 30 git fetch --quiet origin main 2>/dev/null; then
  echo "- Could not fetch origin/main; the numbers below may be stale."
fi
if git rev-parse --verify --quiet origin/main >/dev/null; then
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

# The highest decision number on a tree, from docs/decisions/Dnn-<slug>.md.
highest_decision() {
  grep -oE 'D[0-9]{2}-' | sort -u | tail -1 | tr -dc '0-9' | sed 's/^0*//'
}
decision_files() { find docs/decisions -maxdepth 1 -name 'D[0-9][0-9]-*.md' -printf '%f\n'; }
here=$(decision_files | highest_decision)
on_main=
if git rev-parse --verify --quiet origin/main >/dev/null; then
  on_main=$(git ls-tree --name-only origin/main docs/decisions/ | highest_decision)
fi
next=$(( ${here:-0} > ${on_main:-0} ? ${here:-0} : ${on_main:-0} ))
echo "- Decisions: D${here:-0} is the highest here, D${on_main:-?} on origin/main;" \
  "a new one takes D$(( next + 1 )) unless an open branch has it."
if [ -n "$on_main" ]; then
  # A number this branch added that main has since given to another decision.
  for n in $(seq $(( ${on_main:-0} < ${here:-0} ? ${on_main:-0} : ${here:-0} )) "${here:-0}"); do
    [ "$n" -gt 0 ] || continue
    nn=$(printf 'D%02d-' "$n")
    mine=$(decision_files | grep "^${nn}" || true)
    theirs=$(git ls-tree --name-only origin/main docs/decisions/ | sed 's|.*/||' \
      | grep "^${nn}" || true)
    if [ -n "$mine" ] && [ -n "$theirs" ] && [ "$mine" != "$theirs" ]; then
      echo "  Collision: ${mine} here, ${theirs} on origin/main. Renumber this branch's."
    fi
  done
fi

version_file=apps/api/src/opensolve_pipe/services/solver/version.py
method_version() { grep -oE '^METHOD_VERSION = "[0-9.]+"' | grep -oE '[0-9.]+[0-9]'; }
v_here=$(method_version < "$version_file")
if git rev-parse --verify --quiet origin/main >/dev/null; then
  v_main=$(git show "origin/main:${version_file}" 2>/dev/null | method_version || true)
  echo "- METHOD_VERSION: ${v_here} here, ${v_main:-unknown} on origin/main."
  # Both sides moved it since they parted (to the same number or not): this branch's changes
  # need the next version after main's, with its own changelog entry.
  base=$(git merge-base origin/main HEAD 2>/dev/null || true)
  v_base=
  if [ -n "$base" ]; then
    v_base=$(git show "${base}:${version_file}" 2>/dev/null | method_version || true)
  fi
  if [ -n "$v_base" ] && [ -n "${v_main:-}" ] && [ "$v_base" != "$v_main" ] \
    && [ "$v_base" != "$v_here" ]; then
    echo "  Both this branch and main moved it from ${v_base}: renumber this branch's."
  fi
else
  echo "- METHOD_VERSION: ${v_here}."
fi

if [ "${#failed[@]}" -gt 0 ]; then
  for f in "${failed[@]}"; do echo "- Install failed: ${f}. Run it and read its output."; done
  exit 1
fi
