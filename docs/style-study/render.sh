#!/usr/bin/env bash
# Regenerates every image in images/ from the W1 map, the residents' appearance and A1's art.
# `./render.sh lighting` regenerates lighting/ instead: the four times of day (#122).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BLENDER="${BLENDER:-blender}"

if [[ "${1:-}" == "lighting" ]]; then
  rm -f "$HERE"/out/xcom/{night,morning,afternoon,evening,neutral}/timings.json
  for time in night morning afternoon evening; do
    "$BLENDER" -b -P "$HERE/render3d.py" -- --level xcom --time "$time" --part all | grep '^TIMINGS'
  done
  for part in sprites walk; do
    "$BLENDER" -b -P "$HERE/render3d.py" -- --level xcom --time neutral --part "$part" | grep '^TIMINGS'
  done
  (cd "$HERE" && uv run --no-project --with pillow --with numpy python compose.py lighting costs)
  du -sh "$HERE/lighting"
  exit
fi

for level in xcom fallout; do
  rm -f "$HERE/out/$level/timings.json"
  "$BLENDER" -b -P "$HERE/render3d.py" -- --level "$level" --part all | grep '^TIMINGS'
done
(cd "$HERE/../../server" && uv run python ../docs/style-study/pixel_iso.py)
(cd "$HERE" && uv run --no-project --with pillow --with numpy python compose.py xcom fallout)
du -sh "$HERE/images"
