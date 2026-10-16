#!/usr/bin/env bash
# Approach 3: FLUX.1-schnell via mflux in its own virtualenv. Stops at the first download until
# a Hugging Face account that has accepted the model's access conditions is logged in.
set -euo pipefail

CACHE="${SIMILE_STUDY_CACHE:-$HOME/.cache/simile-style-study}"
OUT="$(cd "$(dirname "$0")" && pwd)/out/flux"
mkdir -p "$CACHE" "$OUT"
[ -x "$CACHE/venv/bin/mflux-generate" ] || {
  uv venv --python 3.12 "$CACHE/venv"
  uv pip install --python "$CACHE/venv/bin/python" mflux==0.22.0
}
export HF_HUB_CACHE="$CACHE/hf/hub"

STYLE="isometric 2:1 pre-rendered game art, modern Shenzhen, muted palette, neon accents, \
soft baked shadows, plain background"
generate() {
  "$CACHE/venv/bin/mflux-generate" --model schnell -q 8 --steps 4 --seed "$1" \
    --width "$2" --height "$3" --prompt "$4, $STYLE" --output "$OUT/$5.png"
}

generate 1 1024 768 "a small coffee shop with a green roof, striped awnings and a COFFEE sign" cafe
generate 2 512 512 "one square tile of warm sandstone plaza paving, seamless" plaza_a
generate 2 512 512 "one square tile of warm sandstone plaza paving with a brass inlay, seamless" plaza_b
INGRID="a slim woman with a dark ponytail, cyan top, plum trousers and an amber backpack"
generate 3 512 768 "$INGRID, standing, facing south-west" ingrid_stand
generate 3 512 768 "$INGRID, mid-stride walking east" ingrid_walk
