#!/bin/sh
# The secret scan, defined once: the gate's `secrets` group, the pre-push hook and the CI job all run it.
#
#     scripts/secrets_scan.sh [<git log arguments>]
#
# It scans commits, never the working tree, so an untracked .env holding real keys is not read.
#   with arguments (for example origin/main..HEAD)   those commits
#   with none                                        the commits a push would send: everything after
#                                                    the upstream branch, or the whole history when
#                                                    the repository has no remote yet
#
# Rules: gitleaks' defaults plus this repository's .gitleaks.toml. Findings are printed redacted.
# Exit 0: clean. Exit 1: at least one finding, or the scan read no commits when there were some to read.
# Exit 3: gitleaks is missing, this is not a repository, or git cannot read the range.
#
# POSIX sh: the CI job runs it inside the gitleaks image.
set -u

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT" || exit 3

if ! command -v gitleaks >/dev/null 2>&1; then
  if [ "$(uname -s)" = "Darwin" ]; then how="brew install gitleaks"; else how="make tools"; fi
  echo "secrets: gitleaks is not installed. Install it with:  $how" >&2
  exit 3
fi
if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "secrets: this is not a git repository yet; run 'git init'" >&2
  exit 3
fi
if ! git rev-parse --verify --quiet HEAD >/dev/null; then
  echo "secrets: no commits yet; nothing to scan"
  exit 0
fi

range="${1:-}"
if [ -z "$range" ]; then
  if upstream=$(git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null); then
    range="$upstream..HEAD"
  elif base=$(git merge-base HEAD origin/HEAD 2>/dev/null); then
    range="$base..HEAD"
  fi
fi

# How many commits there are to read. gitleaks reads the lines a commit adds, so a merge, and a commit
# that only deletes, renames or changes a mode, gives it nothing: only a commit that adds a line counts.
# Word splitting of $range is the point: it holds git log arguments.
# shellcheck disable=SC2086
if ! numstat=$(git log --no-merges --format='commit %H' --numstat ${range:-HEAD} 2>/dev/null); then
  echo "secrets: git cannot read the commits '${range:-HEAD}' (a shallow clone, or a base that is not fetched?)" >&2
  exit 3
fi
expected=$(printf '%s\n' "$numstat" | awk '
  $1 == "commit" { commit = $2; next }
  $1 ~ /^[0-9]+$/ && $1 > 0 { adds[commit] = 1 }
  END { count = 0; for (each in adds) count++; print count }')
if [ "$expected" = "0" ]; then
  echo "secrets: no commit in ${range:-the history} adds a line; nothing to scan"
  exit 0
fi

log=$(mktemp "${TMPDIR:-/tmp}/secrets-scan.XXXXXX")
trap 'rm -f "$log"' EXIT
if [ -n "$range" ]; then
  echo "secrets: scanning $range ($expected commits)"
  gitleaks git --config .gitleaks.toml --no-banner --no-color --verbose --redact --exit-code 1 --log-opts="$range" . >"$log" 2>&1
else
  echo "secrets: scanning the whole history ($expected commits; no remote yet)"
  gitleaks git --config .gitleaks.toml --no-banner --no-color --verbose --redact --exit-code 1 . >"$log" 2>&1
fi
code=$?
cat "$log"
[ "$code" -eq 0 ] || exit 1

# Fail closed: when git fails underneath it, gitleaks reports "0 commits scanned" and still exits 0.
# A scan that read nothing must not look like a scan that found nothing.
scanned=$(sed -n 's/.*[^0-9]\([0-9][0-9]*\) commits scanned.*/\1/p' "$log" | tail -1)
if [ "${scanned:-0}" -eq 0 ]; then
  echo "secrets: there were $expected commits to scan but gitleaks read none; treating that as a failure" >&2
  exit 1
fi
echo "secrets: no leaks found in $scanned commits"
