#!/bin/bash
# PreToolUse hook on Bash (docs/workflow.md §6): before a `git push`, the coordination report
# (coordination.sh) runs again, so a long session learns what main took since it started.
#
# - Not a push: exits at once, silently (this runs before every Bash call, about 7 ms).
# - A collision (a decision number or METHOD_VERSION that both HEAD and origin/main added since
#   they parted): blocks the push, exit 2, with the report as the reason. Renumber, then push.
#   A push of work in progress that must not be lost (the container is ephemeral) may go ahead
#   by prefixing the command with OPENSOLVE_PUSH_ANYWAY=1; say so to the user.
# - Otherwise: lets the push run and adds the report to the session's context. The report names
#   generated files a merge kept this branch's copy of (merge-generated.sh), once: regenerating
#   them is the session's job, and CI's generated-types check is the stop, not this hook.
#
# The command is matched here rather than with the hook's `if` field, whose matching of a bare
# `git push` the documentation leaves open; quoted text (a commit message) is ignored.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ] || ! command -v jq >/dev/null; then
  exit 0
fi

command=$(jq -r '.tool_input.command // empty' 2>/dev/null || true)
# Drop quoted strings, then look for `git push`, also after `cd … &&`, `;`, a pipe or
# `git -C <dir>` / `-c <key=value>` options.
unquoted=$(sed -E "s/'[^']*'//g; s/\"([^\"\\\\]|\\\\.)*\"//g" <<<"$command")
push='(^|[;&|({[:space:]])git([[:space:]]+-[Cc][[:space:]]+[^[:space:]]+)*[[:space:]]+push([[:space:]]|$)'
[[ "$unquoted" =~ $push ]] || exit 0

cd "${CLAUDE_PROJECT_DIR:-.}"
status=0
report=$(.claude/hooks/coordination.sh 2>/dev/null) || status=$?

if [ "$status" -eq 3 ] && [[ "$unquoted" != *OPENSOLVE_PUSH_ANYWAY=1* ]]; then
  {
    echo "Push blocked by .claude/hooks/pre-push.sh: this branch and origin/main added the same"
    echo "number since they parted. Merge origin/main and renumber this branch's decision and"
    echo "method version (docs/workflow.md §5), then push. To push work in progress unchanged,"
    echo "prefix the command with OPENSOLVE_PUSH_ANYWAY=1 and tell the user."
    echo
    echo "$report"
  } >&2
  exit 2
fi

# The kept-generated-files reminder is in this report; give it once.
rm -f "$(git rev-parse --git-dir)/opensolve-generated-merged"
jq -n --arg report "$report" \
  '{hookSpecificOutput: {hookEventName: "PreToolUse", additionalContext: $report}}'
