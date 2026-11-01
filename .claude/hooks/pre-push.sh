#!/bin/bash
# PreToolUse hook on Bash (docs/workflow.md §6), before a `git push`:
#
# 1. Generated files a merge kept this branch's copy of (merge-generated.sh, .gitattributes) are
#    regenerated on the merged tree. If that changes any, the push is blocked until they are
#    committed. docs/verified-state.md is not regenerated here (the gates take minutes); the
#    session is told to re-run scripts/record_history.py.
# 2. The coordination report (coordination.sh) runs again, so a long session learns what main
#    took since it started. A collision (a decision number or METHOD_VERSION that both HEAD and
#    origin/main took) blocks the push: renumber, then push.
#
# A blocked push exits 2 with the reason. A push of work in progress that must not be lost (the
# container is ephemeral) may go ahead by prefixing the command with OPENSOLVE_PUSH_ANYWAY=1;
# say so to the user. Otherwise the push runs with the report added to the session's context.
# Not a push: exits at once, silently (this runs before every Bash call).
#
# The command is matched here rather than with the hook's `if` field, whose matching of a bare
# `git push` the documentation leaves open.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ] || ! command -v jq >/dev/null; then
  exit 0
fi

command=$(jq -r '.tool_input.command // empty' 2>/dev/null || true)
# `git push`, also after `cd … &&`, `;`, a pipe or `git -C <dir>` / `-c <key=value>` options.
push='(^|[;&|({[:space:]])git([[:space:]]+-[Cc][[:space:]]+[^[:space:]]+)*[[:space:]]+push([[:space:]]|$)'
[[ "$command" =~ $push ]] || exit 0

cd "${CLAUDE_PROJECT_DIR:-.}"
anyway=false
[[ "$command" == *OPENSOLVE_PUSH_ANYWAY=1* ]] && anyway=true
problems=()
notes=()

# --- 1. Generated files a merge kept this branch's copy of.
note="$(git rev-parse --git-dir)/opensolve-generated-merged"
if [ -s "$note" ]; then
  mapfile -t kept < "$note"
  regenerate=()
  for f in "${kept[@]}"; do
    case "$f" in
      apps/web/*) regenerate+=("(cd apps/web && pnpm gen:types)") ;;
      apps/api/src/opensolve_pipe/data/pipe_materials.json)
        regenerate+=("(cd apps/api && uv run python scripts/generate_pipe_data.py)") ;;
      apps/api/src/opensolve_pipe/data/api526_orifices.json)
        regenerate+=("(cd apps/api && uv run python scripts/generate_relief_data.py)") ;;
      docs/verified-state.md)
        notes+=("docs/verified-state.md is this branch's copy from before a merge: re-run" \
          "cd apps/api && uv run python scripts/record_history.py on the merged tree.") ;;
    esac
  done
  failed=false
  while read -r step; do
    [ -n "$step" ] || continue
    if ! bash -c "$step" >/dev/null 2>&1; then
      problems+=("Regenerating failed: ${step}. Run it and read its output.")
      failed=true
    fi
  done < <(printf '%s\n' "${regenerate[@]+"${regenerate[@]}"}" | sort -u)
  changed=$(git status --porcelain -- "${kept[@]}" | grep -v ' docs/verified-state.md$' || true)
  if [ -n "$changed" ]; then
    problems+=("Generated files changed when regenerated after a merge; commit them, then push:"
      "$changed")
  elif ! $failed; then
    # Everything regenerates to what is committed. The verified-state note is given once.
    rm -f "$note"
  fi
fi

# --- 2. The coordination report.
status=0
report=$(.claude/hooks/coordination.sh 2>/dev/null) || status=$?
if [ "$status" -eq 3 ]; then
  problems+=("This branch and origin/main took the same number since they parted. Merge"
    "origin/main and renumber this branch's decision and method version (docs/workflow.md §5).")
fi

if [ "${#problems[@]}" -gt 0 ] && ! $anyway; then
  {
    echo "Push blocked by .claude/hooks/pre-push.sh:"
    printf '%s\n' "${problems[@]}"
    echo "To push work in progress unchanged, prefix the command with OPENSOLVE_PUSH_ANYWAY=1"
    echo "and tell the user."
    [ "${#notes[@]}" -eq 0 ] || printf '%s\n' "${notes[@]}"
    echo
    echo "$report"
  } >&2
  exit 2
fi

context=$(printf '%s\n' "${problems[@]+"${problems[@]}"}" "${notes[@]+"${notes[@]}"}" "$report")
jq -n --arg context "$context" \
  '{hookSpecificOutput: {hookEventName: "PreToolUse", additionalContext: $context}}'
