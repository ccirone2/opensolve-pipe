#!/bin/bash
# PreToolUse hook on Bash (docs/workflow.md §6): before a `git push`, the coordination report
# (coordination.sh) runs again, so a long session learns what main took since it started.
#
# - Not a push: exits at once, silently (this runs before every Bash call).
# - A collision (a decision number or METHOD_VERSION that both HEAD and origin/main took):
#   blocks the push, exit 2, with the report as the reason. Renumber, then push. A push of work
#   in progress that must not be lost (the container is ephemeral) may go ahead by prefixing
#   the command with OPENSOLVE_ALLOW_COLLISION=1; say so to the user.
# - Otherwise: lets the push run and adds the report to the session's context.
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

status=0
report=$("${CLAUDE_PROJECT_DIR:-.}"/.claude/hooks/coordination.sh 2>/dev/null) || status=$?

if [ "$status" -eq 3 ] && [[ "$command" != *OPENSOLVE_ALLOW_COLLISION=1* ]]; then
  {
    echo "Push blocked by .claude/hooks/pre-push.sh: this branch and origin/main took the same"
    echo "number since they parted. Merge origin/main and renumber this branch's decision and"
    echo "method version (docs/workflow.md §5), then push. To push work in progress unchanged,"
    echo "prefix the command with OPENSOLVE_ALLOW_COLLISION=1 and tell the user."
    echo
    echo "$report"
  } >&2
  exit 2
fi

jq -n --arg report "$report" \
  '{hookSpecificOutput: {hookEventName: "PreToolUse", additionalContext: $report}}'
