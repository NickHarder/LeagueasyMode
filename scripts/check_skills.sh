#!/usr/bin/env bash
# Check every skill's frontmatter, so a skill can always be found and its version is always known.
#
#     scripts/check_skills.sh [skills-directory]        (default: .claude/skills)
#
# For each <skills-directory>/<name>/SKILL.md the frontmatter must have:
#   name                 equal to the folder name; lowercase letters, digits and single hyphens
#   description          present, at most 1024 characters, and containing "use when" (any case): the
#                        sentence an agent matches a request against
#   metadata.version     MAJOR.MINOR.PATCH; bump it whenever the skill's text changes
#
# A skill installed from somewhere else follows its own format. List its folder name, or a pattern
# such as `remotion-*`, one a line, in <skills-directory>/THIRD_PARTY, and it is skipped here.
#
# Exit 0: every skill passes (or there is no skills directory). Exit 1: at least one does not; each
# problem is printed with its file. The gate's lint group and the CI lint job both run this.
#
# Written for bash 3.2 (macOS); uses only awk, grep and tr.
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
DIR="${1:-$ROOT/.claude/skills}"

if [ ! -d "$DIR" ]; then
  echo "skills: no skills directory at ${DIR#"$ROOT"/}; nothing to check"
  exit 0
fi

problems=0
count=0
skipped=0

# Is the skill folder $1 listed in the THIRD_PARTY file?
is_third_party() {
  [ -f "$DIR/THIRD_PARTY" ] || return 1
  while IFS= read -r pattern || [ -n "$pattern" ]; do
    case "$pattern" in '' | '#'*) continue ;; esac
    # shellcheck disable=SC2254  # the pattern is meant to be matched as a pattern
    case "$1" in $pattern) return 0 ;; esac
  done <"$DIR/THIRD_PARTY"
  return 1
}

problem() {
  echo "skills: $1: $2" >&2
  problems=$((problems + 1))
}

for folder in "$DIR"/*/; do
  [ -d "$folder" ] || continue
  name=$(basename "$folder")
  if is_third_party "$name"; then
    skipped=$((skipped + 1))
    continue
  fi
  file="${folder}SKILL.md"
  shown="${file#"$ROOT"/}"
  count=$((count + 1))

  if [ ! -f "$file" ]; then
    problem "$shown" "the folder has no SKILL.md"
    continue
  fi

  # The lines between the first line (which must be ---) and the next --- line.
  front=$(awk 'NR == 1 { if ($0 != "---") exit; next } $0 == "---" { closed = 1; exit } { print } END { if (!closed) exit 1 }' "$file") || front=""
  if [ -z "$front" ]; then
    problem "$shown" "no frontmatter (the file must start with a --- line and close it with another)"
    continue
  fi

  declared=$(printf '%s\n' "$front" | awk '/^name:/ { sub(/^name:[[:space:]]*/, ""); gsub(/["'"'"']/, ""); sub(/[[:space:]]+$/, ""); print; exit }')
  if [ -z "$declared" ]; then
    problem "$shown" "frontmatter has no name"
  elif [ "$declared" != "$name" ]; then
    problem "$shown" "name is '$declared' but the folder is '$name'; they must match"
  fi
  if ! printf '%s' "$name" | grep -Eq '^[a-z0-9]+(-[a-z0-9]+)*$'; then
    problem "$shown" "the folder name must be lowercase letters, digits and single hyphens"
  fi

  # The description: its own line plus any indented continuation lines (a folded or literal block),
  # read as YAML reads it: without the block's marker or each line's indentation, one space between.
  description=$(printf '%s\n' "$front" | awk '
    /^description:/ { on = 1; sub(/^description:[[:space:]]*/, ""); sub(/^[>|][-+]?[[:space:]]*$/, ""); text = $0; next }
    on && /^[^[:space:]]/ { on = 0 }
    on { sub(/^[[:space:]]+/, ""); text = (text == "" ? $0 : text " " $0) }
    END { print text }')
  if [ -z "$(printf '%s' "$description" | tr -d '[:space:]')" ]; then
    problem "$shown" "frontmatter has no description"
  else
    if ! printf '%s' "$description" | grep -qi 'use when'; then
      problem "$shown" "the description must say when to use the skill: add a sentence starting \"Use when\""
    fi
    length=$(printf '%s' "$description" | wc -c | tr -d '[:space:]')
    if [ "$length" -gt 1024 ]; then
      problem "$shown" "the description is $length characters; the limit is 1024"
    fi
  fi

  # metadata.version: a version: line indented under metadata:.
  version=$(printf '%s\n' "$front" | awk '
    /^metadata:/ { on = 1; next }
    on && /^[^[:space:]]/ { on = 0 }
    on && /^[[:space:]]+version:/ { sub(/^[[:space:]]+version:[[:space:]]*/, ""); gsub(/["'"'"']/, ""); sub(/[[:space:]]+$/, ""); print; exit }')
  if [ -z "$version" ]; then
    problem "$shown" "frontmatter has no metadata.version (add: metadata, then an indented version: \"1.0.0\")"
  elif ! printf '%s' "$version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'; then
    problem "$shown" "metadata.version is '$version'; it must be MAJOR.MINOR.PATCH"
  fi
done

if [ "$problems" -gt 0 ]; then
  echo "skills: $problems problem(s) in $count skill(s)" >&2
  exit 1
fi
if [ "$skipped" -gt 0 ]; then
  echo "skills: $count skill(s) ok, $skipped third-party skipped"
else
  echo "skills: $count skill(s) ok"
fi
