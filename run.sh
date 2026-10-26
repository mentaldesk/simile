#!/usr/bin/env bash
set -euo pipefail
set -m

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
server_port=8000
client_port=5173
url="http://localhost:$client_port"

apple_silicon=false
[[ $(uname -s) == Darwin && $(uname -m) == arm64 ]] && apple_silicon=true

missing=()
command -v uv >/dev/null || missing+=("uv: brew install uv, or see https://docs.astral.sh/uv/")
command -v make >/dev/null || missing+=("make: xcode-select --install on a Mac, or your package manager")
if ! command -v node >/dev/null; then
  missing+=("Node 22.12 or later: brew install node, or see https://nodejs.org")
else
  IFS=. read -r major minor _ <<<"$(node --version | tr -d v)"
  if ((major < 22 || (major == 22 && minor < 12))); then
    missing+=("Node 22.12 or later (you have $(node --version)): brew upgrade node, or see https://nodejs.org")
  fi
fi
command -v claude >/dev/null ||
  missing+=("Claude Code: see https://claude.com/claude-code, then run claude once to log in")
if ((${#missing[@]})); then
  echo "Simile needs:" >&2
  printf '  - %s\n' "${missing[@]}" >&2
  exit 1
fi

taken() {
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null || (exec 3<>"/dev/tcp/localhost/$1") 2>/dev/null
}
for port in "$server_port" "$client_port"; do
  if taken "$port"; then
    echo "Port $port is taken, maybe by make dev or another ./run.sh. Stop that and try again." >&2
    exit 1
  fi
done

export SIMILE_VOICE="${SIMILE_VOICE:-0}"
extras=()
if [[ $SIMILE_VOICE == 1 ]] && $apple_silicon; then
  extras=(--extra voice)
fi

make -s -C "$root" client/node_modules/.package-lock.json
# --inexact keeps the voice extra installed while voices are off, for SIMILE_VOICE=1 make dev.
(cd "$root/server" && uv sync --inexact ${extras[@]+"${extras[@]}"})

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

(cd "$root/server" && exec uv run ${extras[@]+"${extras[@]}"} simile worlds serve --port "$server_port") &
server=$!
(cd "$root/client" && exec node_modules/.bin/vite --port "$client_port" --strictPort --clearScreen false </dev/null) &
client=$!

if [[ $SIMILE_VOICE == 1 ]] && $apple_silicon; then
  echo "Starting the village with voices. The first time, that downloads the voice model (about 3 GB)."
elif [[ $SIMILE_VOICE == 1 ]]; then
  echo "Voices need a Mac with Apple Silicon, so starting the village without them."
else
  echo "Starting the village without voices: residents only greet you out loud. SIMILE_VOICE=1 ./run.sh turns them on."
fi
until curl -sf "http://127.0.0.1:$server_port/api/health" >/dev/null && curl -sf "$url" >/dev/null; do
  kill -0 "$server" 2>/dev/null && kill -0 "$client" 2>/dev/null || exit 1
  sleep 1
done

if [[ $(uname -s) == Darwin ]]; then
  open "$url"
elif command -v xdg-open >/dev/null; then
  xdg-open "$url" >/dev/null 2>&1 || true
fi
echo
echo "Simile is running at $url. Ctrl-C stops it."
echo

while kill -0 "$server" 2>/dev/null && kill -0 "$client" 2>/dev/null; do sleep 1; done
