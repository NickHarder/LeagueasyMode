#!/bin/sh
# What a session in Claude Code's cloud needs before its first turn. The SessionStart hook in
# .claude/settings.json runs this script; anywhere but the cloud it does nothing and prints nothing.
#
# The cloud starts each session from a fresh clone, in a container that has no gitleaks, no
# virtualenv and no git hooks, and none of the owner's ~/.claude/CLAUDE.md. So, there, this script
# runs `make tools` and `make bootstrap`, which ready the gate and turn the pre-push hook on, and
# prints the owner's standing rules (.claude/owner-rules.md, a copy of the kit's global/CLAUDE.md);
# Claude Code adds what it prints to the session. What the two make commands print goes to a log.
#
# POSIX sh. Exit 0 always: a session starts even when its setup did not finish.
set -u

[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0

ROOT=$(cd "$(dirname "$0")/.." && pwd)
log="${TMPDIR:-/tmp}/cloud-start.log"
if (cd "$ROOT" && make tools && make bootstrap) >"$log" 2>&1; then
  echo "cloud start: make tools and make bootstrap are done; make gate and the pre-push hook are ready."
else
  echo "cloud start: the setup did not finish; read $log, then run make tools and make bootstrap."
fi
echo
cat "$ROOT/.claude/owner-rules.md"
exit 0
