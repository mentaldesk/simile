#!/usr/bin/env bash
# Regenerates every image in images/ from the W1 map, the residents' appearance and A1's art.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BLENDER="${BLENDER:-blender}"

for level in xcom fallout; do
  rm -f "$HERE/out/$level/timings.json"
  "$BLENDER" -b -P "$HERE/render3d.py" -- --level "$level" --part all | grep '^TIMINGS'
done
(cd "$HERE/../../server" && uv run python ../docs/style-study/pixel_iso.py)
(cd "$HERE" && uv run --no-project --with pillow --with numpy python compose.py xcom fallout)
du -sh "$HERE/images"
