#!/bin/sh
# Starts the engine a built LeagueasyMode.app carries, the way the app does, and fetches its pages:
#
#     overlay/macos/scripts/smoke_test_app.sh <LeagueasyMode.app>
#
# The engine runs as a new player's would: from an empty home folder, so from an empty uv cache too,
# with no settings and no application files. It runs the bundled uv with the arguments OverlayCore's
# EngineCommand gives (its unit tests hold them), waits for the line with the overlay's address,
# then fetches the overlay, the last game and the settings, which must all come from the wheel.
#
# Exit 0: the engine started and served every page. Exit 1: it did not. Exit 64: bad arguments.
#
# POSIX sh.
set -eu

STARTUP_SECONDS=180
PAGES="/ summary.html settings.html state history preferences"

[ $# -eq 1 ] || { echo "smoke_test_app: usage: overlay/macos/scripts/smoke_test_app.sh <LeagueasyMode.app>" >&2; exit 64; }
app=$(cd "$1" && pwd)
contents="$app/Contents"
engine_directory="$contents/Resources/engine"
wheel=$(find "$engine_directory" -name '*.whl' | sort | tail -n 1)
[ -n "$wheel" ] || { echo "smoke_test_app: no wheel in $engine_directory" >&2; exit 1; }
python_version=$(cat "$engine_directory/python-version")

plutil -lint "$contents/Info.plist"
codesign --verify --strict --deep "$app"

work_directory=$(mktemp -d)
mkdir "$work_directory/home"
cd "$work_directory"
# Where uv keeps things follows the home folder, unless one of these says otherwise.
unset UV_CACHE_DIR UV_TOOL_DIR UV_PYTHON_INSTALL_DIR
HOME="$work_directory/home" "$contents/Helpers/uv" tool run --from "$wheel" \
  --constraints "$engine_directory/constraints.txt" --python "$python_version" \
  leagueasymode run > "$work_directory/engine.out" 2> "$work_directory/engine.err" &
engine_pid=$!
trap 'kill "$engine_pid" 2>/dev/null || true' EXIT

overlay_url=""
waited_seconds=0
while [ -z "$overlay_url" ]; do
  if ! kill -0 "$engine_pid" 2>/dev/null; then
    echo "smoke_test_app: the engine stopped before it announced its address" >&2
    cat "$work_directory/engine.err" >&2
    exit 1
  fi
  if [ "$waited_seconds" -ge "$STARTUP_SECONDS" ]; then
    echo "smoke_test_app: no address after ${STARTUP_SECONDS}s" >&2
    cat "$work_directory/engine.err" >&2
    exit 1
  fi
  sleep 1
  waited_seconds=$((waited_seconds + 1))
  overlay_url=$(sed -n 's/^LEAGUEASYMODE_OVERLAY_URL=//p' "$work_directory/engine.out")
done
echo "smoke_test_app: the engine announced $overlay_url after ${waited_seconds}s"

for page in $PAGES; do
  [ "$page" = / ] && page=""
  curl --fail --silent --show-error --output /dev/null "$overlay_url$page"
  echo "smoke_test_app: served /$page"
done
