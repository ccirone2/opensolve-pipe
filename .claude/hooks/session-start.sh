#!/bin/bash
# SessionStart hook for Claude Code cloud sessions (docs/workflow.md §6).
#
# 1. Installs the API's and the web app's dependencies when a lockfile changed since the last
#    install, so the gates (CLAUDE.md, Tooling) run at once.
# 2. Configures the `generated` merge driver (.gitattributes, merge-generated.sh).
# 3. Prints the coordination report (coordination.sh): where this branch stands against main,
#    the other session branches, and the decision number and method version it would take.
#
# It runs on every SessionStart source (startup, resume, clear, compact): after /clear or a
# compaction the report goes back into the fresh context. Its stdout reaches the session as
# context, so it prints only branch names, counts and numbers.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"
hook=.claude/hooks/session-start.sh

# --- The `generated` merge driver (.gitattributes): a merge keeps this branch's copy of a
# generated file and the report says to regenerate it. Local git config, so set at every start.
git config merge.generated.name "keep this branch's generated file; regenerate it after the merge"
git config merge.generated.driver ".claude/hooks/merge-generated.sh %P %A %B"

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

# --- Coordination report (coordination.sh): at session start a collision is news, not an
# error (pre-push.sh blocks the push on it), and a report that fails must not fail the session.
.claude/hooks/coordination.sh || true

if [ "${#failed[@]}" -gt 0 ]; then
  for f in "${failed[@]}"; do echo "- Install failed: ${f}. Run it and read its output."; done
  exit 1
fi
