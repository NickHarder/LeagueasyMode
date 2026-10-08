#!/usr/bin/env bash
# Set a fresh clone up to run the gate:   make bootstrap   (from the repo root), then   make gate
#
# Installs the Python environment the lock file pins (scripts/kit.conf says where the project lives),
# readies the bundle check (scripts/okf_bundle.py, which uv runs from its own lock file), writes the
# index files of docs/ when there are none, and turns on the repo's git hooks. Needs network once,
# for PyPI. It needs no API key and no .env.
#
# Safe to run again. Written for bash 3.2 (macOS).
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck source=/dev/null
. "$ROOT/scripts/kit.conf"

# Every project needs uv: it runs the bundle check, with or without a Python layer.
if ! command -v uv >/dev/null 2>&1; then
  echo "bootstrap: 'uv' is not installed. Install it, then run this again:" >&2
  echo "    curl -LsSf https://astral.sh/uv/install.sh | sh        (https://docs.astral.sh/uv/)" >&2
  exit 3
fi

# The first run fetches what scripts/okf_bundle.py.lock pins; the gate then runs it offline.
if ! bundle_check_version=$("$ROOT/scripts/okf_bundle.py" --version); then
  echo "bootstrap: the bundle check (scripts/okf_bundle.py) could not be readied; it needs PyPI once" >&2
  exit 3
fi
echo "bootstrap: the bundle check is ready ($bundle_check_version)"

# An index is written from the concepts in its directory, so a new project has none yet.
if [ ! -f "$ROOT/docs/index.md" ]; then
  (cd "$ROOT" && scripts/okf_bundle.py index docs >/dev/null)
  echo "bootstrap: no docs/index.md yet; wrote the index files of the bundle in docs/ (commit them)"
fi

if [ "${PYTHON_SERVICE:-0}" = "1" ]; then
  cd "$ROOT/${SERVICE_DIR:-.}"
  # A virtualenv from another project must not be mistaken for this one's.
  unset VIRTUAL_ENV
  if [ -f uv.lock ]; then
    echo "bootstrap: installing the locked environment into ${SERVICE_DIR:-.}/.venv"
    uv sync --frozen
  else
    echo "bootstrap: no uv.lock yet; resolving and writing one (commit it)"
    uv sync
  fi
  echo "bootstrap: $(.venv/bin/python --version), $(.venv/bin/ruff --version), $(.venv/bin/mypy --version)"
  if [ "${API_PROJECT:-0}" = "1" ] && [ ! -f schemas/openapi.json ]; then
    echo "bootstrap: no schemas/openapi.json yet; exporting it from the code (commit it)"
    ".venv/bin/${OPENAPI_EXPORT}"
  fi
fi

if [ -d "$ROOT/.githooks" ]; then
  if git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
    git -C "$ROOT" config core.hooksPath .githooks
    echo "bootstrap: git hooks on (core.hooksPath=.githooks); a push now runs the gate first"
  else
    echo "bootstrap: not a git repository yet; run 'git init', then 'make bootstrap' again for the hooks" >&2
  fi
fi

echo "bootstrap: done. Next:  make gate"
