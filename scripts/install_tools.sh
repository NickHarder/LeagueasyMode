#!/bin/sh
# The tools the gate needs that uv cannot install, on Linux:   make tools
#
#     scripts/install_tools.sh gitleaks [oasdiff] [ffmpeg]
#
# Puts each tool named into ~/.local/bin, at the version CI pins, once its download matches the
# checksum written here. A tool already on PATH is left alone. On a Mac it installs nothing: Homebrew
# is the way there. ffmpeg, with the ffprobe that comes with it, is for the demo layer, and is not
# part of `make tools`. Every CI job that installs one of these tools runs this script, so their
# versions and checksums are written in this one place.
#
# Exit 0: every tool named is there. Exit 3: one is not, and could not be installed. Exit 64: bad
# arguments.
#
# POSIX sh.
set -u

GITLEAKS_VERSION=8.28.0
OASDIFF_VERSION=1.33.0
# A static build of ffmpeg 7.0.2, as the ffmpeg-static project republishes it under its release b6.1.1:
# two files from GitHub's release servers, where a distribution's package brings a hundred.
FFMPEG_RELEASE=b6.1.1
BIN_DIR="$HOME/.local/bin"

[ $# -ge 1 ] || { echo "tools: usage: scripts/install_tools.sh gitleaks [oasdiff] [ffmpeg]" >&2; exit 64; }
for tool in "$@"; do
  case "$tool" in
    gitleaks | oasdiff | ffmpeg) ;;
    *) echo "tools: '$tool' is not one of the tools this script installs (gitleaks, oasdiff, ffmpeg)" >&2; exit 64 ;;
  esac
done

# The programs a tool puts on PATH: ffmpeg brings ffprobe, which reads a video back.
programs_of() {
  case "$1" in
    ffmpeg) echo "ffmpeg ffprobe" ;;
    *) echo "$1" ;;
  esac
}

missing=""
for tool in "$@"; do
  absent=""
  for program in $(programs_of "$tool"); do
    command -v "$program" >/dev/null 2>&1 || absent="$absent $program"
  done
  if [ -z "$absent" ]; then
    echo "tools: $tool is there ($(command -v "$tool"))"
  else
    missing="$missing $tool"
  fi
done
[ -n "$missing" ] || exit 0

system=$(uname -s)
if [ "$system" = "Darwin" ]; then
  echo "tools: on a Mac, Homebrew installs them:  brew install$missing" >&2
  exit 3
fi
if [ "$system" != "Linux" ]; then
  echo "tools: this script installs on Linux only, and this is $system; install$missing yourself" >&2
  exit 3
fi
case "$(uname -m)" in
  x86_64 | amd64) arch=x64 ;;
  aarch64 | arm64) arch=arm64 ;;
  *) echo "tools: no pinned build for $(uname -m); install$missing yourself" >&2; exit 3 ;;
esac

# Each program's download and its SHA-256: the projects' own for gitleaks and oasdiff, computed here
# for ffmpeg and ffprobe, whose release publishes none.
release_of() {
  case "$1-$2" in
    gitleaks-x64) echo "https://github.com/gitleaks/gitleaks/releases/download/v$GITLEAKS_VERSION/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz a65b5253807a68ac0cafa4414031fd740aeb55f54fb7e55f386acb52e6a840eb" ;;
    gitleaks-arm64) echo "https://github.com/gitleaks/gitleaks/releases/download/v$GITLEAKS_VERSION/gitleaks_${GITLEAKS_VERSION}_linux_arm64.tar.gz eff65261156100e5d94a6b3dec313d532fddfe19ae1590bf7a2b4f2699128356" ;;
    oasdiff-x64) echo "https://github.com/oasdiff/oasdiff/releases/download/v$OASDIFF_VERSION/oasdiff_${OASDIFF_VERSION}_linux_amd64.tar.gz 43a4e328e2d13ba1552d760aa68d2485c75c5621f309f6ff64ae895188345247" ;;
    oasdiff-arm64) echo "https://github.com/oasdiff/oasdiff/releases/download/v$OASDIFF_VERSION/oasdiff_${OASDIFF_VERSION}_linux_arm64.tar.gz 4ae3c362d6074d919aada2dea82d0ee84366591600384455d0bdc658ddf8f7ae" ;;
    ffmpeg-x64) echo "https://github.com/eugeneware/ffmpeg-static/releases/download/$FFMPEG_RELEASE/ffmpeg-linux-x64.gz bfe8a8fc511530457b528c48d77b5737527b504a3797a9bc4866aeca69c2dffa" ;;
    ffmpeg-arm64) echo "https://github.com/eugeneware/ffmpeg-static/releases/download/$FFMPEG_RELEASE/ffmpeg-linux-arm64.gz 754a678672298bc68156adff58aa7385a592c2b30b1d0ae8750c45c915c4bac0" ;;
    ffprobe-x64) echo "https://github.com/eugeneware/ffmpeg-static/releases/download/$FFMPEG_RELEASE/ffprobe-linux-x64.gz 25d9b6ccb05e3d9de9e04e31e2506d8dd7f9f0418981965ac6df12e8d3afd067" ;;
    ffprobe-arm64) echo "https://github.com/eugeneware/ffmpeg-static/releases/download/$FFMPEG_RELEASE/ffprobe-linux-arm64.gz 2ab6aba60ee84412dff9188720703376cb4e7aaf7e0b5e43aa8249f2acae5bf8" ;;
  esac
}

work=$(mktemp -d) || exit 3
trap 'rm -rf "$work"' EXIT
mkdir -p "$BIN_DIR" || exit 3
for tool in $missing; do
  for program in $(programs_of "$tool"); do
    # shellcheck disable=SC2046  # two words: the address and the checksum
    set -- $(release_of "$program" "$arch")
    url=$1
    checksum=$2
    download="$work/$(basename "$url")"
    if ! curl -sSfL --retry 3 -o "$download" "$url"; then
      echo "tools: could not download $program from $url" >&2
      exit 3
    fi
    if ! echo "$checksum  $download" | sha256sum -c - >/dev/null 2>&1; then
      echo "tools: the download of $program does not match its checksum; nothing was installed" >&2
      exit 3
    fi
    case "$download" in
      *.tar.gz) tar -xzf "$download" -C "$work" "$program" || exit 3 ;;
      *.gz) gunzip -c "$download" >"$work/$program" || exit 3 ;;
    esac
    chmod 0755 "$work/$program"
    mv "$work/$program" "$BIN_DIR/$program" || exit 3
    echo "tools: installed $program into $BIN_DIR"
  done
done
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "tools: $BIN_DIR is not on PATH; add it, for example in ~/.profile" >&2 ;;
esac
