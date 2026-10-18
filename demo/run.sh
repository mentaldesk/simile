#!/usr/bin/env bash
# Start the demo village afresh: rebuild its database from demo/, then run the voiced sim server
# and the client. The village holds still until the player's first step. Ctrl-C stops both.
set -euo pipefail
set -m

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export SIMILE_DB="${DEMO_DB:-$root/server/data/demo.db}"
[[ $SIMILE_DB == /* ]] || SIMILE_DB="$PWD/$SIMILE_DB"
export SIMILE_PORT="${SIMILE_PORT:-8000}"
CLIENT_PORT="${CLIENT_PORT:-5173}"
export SIMILE_VOICE="${SIMILE_VOICE:-1}"
export SIMILE_NEWS=0
unset SIMILE_FRESH SIMILE_NEWS_FEED

for port in "$SIMILE_PORT" "$CLIENT_PORT"; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $port is taken (make dev?). Stop it, or set SIMILE_PORT and CLIENT_PORT." >&2
    exit 1
  fi
done

make -s -C "$root" client/node_modules/.package-lock.json
cd "$root/server"
uv run --extra voice python ../demo/prepare.py --db "$SIMILE_DB"

server=""
client=""
stop() {
  trap - EXIT INT TERM
  # Only uv itself: it hands TERM to the server, which then closes its own Claude Code processes.
  [[ -z $server ]] || kill -TERM "$server" 2>/dev/null || true
  [[ -z $client ]] || kill -TERM -- "-$client" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap stop EXIT INT TERM

uv run --extra voice python ../demo/serve.py --port "$SIMILE_PORT" &
server=$!
(cd "$root/client" && exec node_modules/.bin/vite --config ../demo/vite.config.mts \
  --port "$CLIENT_PORT" --strictPort) &
client=$!

until curl -sf "http://127.0.0.1:$SIMILE_PORT/api/health" >/dev/null; do
  kill -0 "$server" 2>/dev/null && kill -0 "$client" 2>/dev/null || exit 1
  sleep 1
done
cat <<EOF

Open http://localhost:$CLIENT_PORT/?play now and hold the left arrow for about a second, the first
step of the walk-through in demo/README.md. The village holds still until you take a step, and that
key press is also what lets the browser play sound. To start over, press Ctrl-C here and run
demo/run.sh again.

EOF

while kill -0 "$server" 2>/dev/null && kill -0 "$client" 2>/dev/null; do sleep 1; done
