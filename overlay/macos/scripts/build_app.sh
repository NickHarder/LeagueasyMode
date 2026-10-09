#!/bin/sh
# Builds LeagueasyMode.app, the overlay app with the engine inside, so that it runs without a clone:
#
#     overlay/macos/scripts/build_app.sh [output directory]
#
# The output directory (dist/ at the repository's root unless named) gets LeagueasyMode.app and
# LeagueasyMode-<version>.zip, the app as a download. The app holds:
#
#     Contents/MacOS/LeagueasyOverlay                  the app, built for release
#     Contents/Helpers/uv                              a copy of uv: UV_BINARY, or the uv on PATH
#     Contents/Resources/engine/leagueasymode-*.whl    the engine, with its overlay pages
#     Contents/Resources/engine/constraints.txt        the versions uv.lock pins
#     Contents/Resources/engine/python-version         the Python version .python-version names
#
# and runs `uv tool run --from <wheel> leagueasymode run` (OverlayCore's BundledEngine). The first
# start downloads the engine's dependencies, and Python when none suitable is installed, into uv's
# cache; later starts reuse them.
#
# The app is signed ad hoc only, which is not a Developer ID: macOS asks before opening it the first
# time (docs/references/macos-app.md says how). It is built for this Mac's architecture.
#
# Exit 0: built. Exit 1: a step failed. Exit 64: bad arguments. Exit 69: not on a Mac, or no uv.
#
# POSIX sh.
set -eu

[ $# -le 1 ] || { echo "build_app: usage: overlay/macos/scripts/build_app.sh [output directory]" >&2; exit 64; }
[ "$(uname -s)" = Darwin ] || { echo "build_app: the app is built on a Mac" >&2; exit 69; }

script_directory=$(cd "$(dirname "$0")" && pwd)
macos_directory=$(dirname "$script_directory")
repository_root=$(cd "$macos_directory/../.." && pwd)
output_directory=${1:-$repository_root/dist}
mkdir -p "$output_directory"
output_directory=$(cd "$output_directory" && pwd)

uv_binary=${UV_BINARY:-$(command -v uv || true)}
[ -n "$uv_binary" ] && [ -x "$uv_binary" ] || { echo "build_app: no uv: install it, or set UV_BINARY" >&2; exit 69; }
# A shim that finds uv elsewhere (asdf, mise) would not run inside the app: the copy must be uv itself.
case $(file -b "$uv_binary") in
  *Mach-O*) ;;
  *) echo "build_app: $uv_binary is not uv's program itself; set UV_BINARY to it" >&2; exit 69 ;;
esac

version=$(cd "$repository_root" && uv version --short --frozen)
app="$output_directory/LeagueasyMode.app"
contents="$app/Contents"
engine_directory="$contents/Resources/engine"
archive="$output_directory/LeagueasyMode-$version.zip"

echo "build_app: LeagueasyMode $version into $output_directory"
rm -rf "$app" "$archive"
mkdir -p "$contents/MacOS" "$contents/Helpers" "$engine_directory"

swift build --package-path "$macos_directory" -c release --product LeagueasyOverlay
binary_directory=$(swift build --package-path "$macos_directory" -c release --show-bin-path)
cp "$binary_directory/LeagueasyOverlay" "$contents/MacOS/LeagueasyOverlay"

(
  cd "$repository_root"
  uv build --wheel --out-dir "$engine_directory" .
  uv export --frozen --no-dev --no-emit-project --no-hashes --no-header --no-annotate \
    --format requirements-txt -o "$engine_directory/constraints.txt" -q
)
cp "$repository_root/.python-version" "$engine_directory/python-version"
# uv build leaves a .gitignore beside the wheel; the bundle needs only the wheel.
rm -f "$engine_directory/.gitignore"

cp "$uv_binary" "$contents/Helpers/uv"
chmod 755 "$contents/Helpers/uv"

sed "s/@VERSION@/$version/g" "$macos_directory/Info.plist.in" > "$contents/Info.plist"
plutil -lint "$contents/Info.plist"

# Ad hoc: the inner program first, then the app, whose seal covers it and the resources.
codesign --force --sign - "$contents/Helpers/uv"
codesign --force --sign - "$app"
codesign --verify --strict --deep "$app"

ditto -c -k --keepParent "$app" "$archive"
echo "build_app: $app"
echo "build_app: $archive"
