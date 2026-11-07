#!/usr/bin/env bash
# Regenerates the README images in docs/readme/ from real runs of aih on synthetic data.
#
#   scripts/readme-visuals.sh             capture, then render every image
#   scripts/readme-visuals.sh --render    render again from the last capture
#
# 1. Capture (scripts/readme-capture.sh). scripts/demo-data.py builds a made-up user's setup:
#    "alex" on a hub called "server", plus a desktop and a laptop. It runs inside a private
#    user, mount and hostname namespace, mounted at /home/alex on a machine named "server", so
#    every path in the images is exactly what aih printed. The real `aih collect`, `search`,
#    `stats`, `show` and `check` run on it and their output is saved as-is, ANSI colours
#    included. A second synthetic archive of 100,000 messages is built to time searches.
# 2. Render (scripts/readme-visuals.py). The captures become HTML scenes, headless Chrome
#    screenshots them, and ImageMagick converts them to WebP.
#
# Needs: Linux with unprivileged user namespaces (unshare), python3, rsync,
# google-chrome-stable and ImageMagick.
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
cache="$repo/docs/readme/.capture"

if [ "${1:-}" != "--render" ]; then
  work="$(mktemp -d "${TMPDIR:-/tmp}/aih-visuals.XXXXXX")"
  trap 'rm -rf "$work"' EXIT
  mkdir -p "$work/src" "$work/out"
  cp "$repo/aih.py" "$repo/scripts/demo-data.py" "$repo/scripts/readme-capture.sh" "$work/src/"
  # /home is replaced by an empty tmpfs inside the namespace, so nothing real is visible there.
  WORK="$work" unshare --user --map-root-user --mount --uts --fork bash "$work/src/readme-capture.sh"
  rm -rf "$cache" && mkdir -p "$cache" && cp "$work/out/"* "$cache/"
fi

python3 "$repo/scripts/readme-visuals.py" "$cache" "$repo/docs/readme"
