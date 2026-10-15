# Simile

A 2D pixel-art village where LLM-driven NPCs talk to each other and to the player. The
[README](README.md) has the concept and [`docs/poc-plan.md`](docs/poc-plan.md) has the plan: every
task in it is one issue in mentaldesk/simile and one PR.

## Rules for every task

- **Change only the paths your issue's *Owns* section lists.** Two tasks in flight never own the
  same paths. Shared contracts (`server/simile/schema/`, `server/simile/protocol/`) change only in
  their own small PR. If you need to change something you don't own, stop and report it. The one
  exception: any task may add the dependencies it needs to `server/pyproject.toml` + `server/uv.lock`
  or `client/package.json` + `client/package-lock.json` (see *Dependencies* below), even though F1
  owns those files.
- **Never use the Claude API, the `anthropic` SDK or an `ANTHROPIC_API_KEY`.** Every LLM call goes
  through the L1 client (`server/simile/llm/`), which drives the local Claude Code login. Tests use
  L1's fake provider and never call Claude. Lint enforces this: ruff bans `import anthropic` and
  eslint bans `@anthropic-ai/*`.
- Run `make test` and `make lint` before pushing. Both must pass locally and in CI.
- Keep code comments to a minimum: one line, only for what the code can't say.
- Branch `task/<id>-<slug>` from `origin/main`. Integrate main with `git merge origin/main`, never
  rebase or force-push.

## Layout

```
server/simile/   schema/ protocol/ sim/ art/ world/ npc/ social/ memory/ llm/ voice/ news/
                 behaviour/ conversation/ reflection/ voicing/ persistence/ debug/
client/src/      net/ scenes/ world/ ui/ audio/ debug/
content/         art/ map/ npcs/ voices/
voice-lab/       the voice prototype; N2 extends it for batch voice design
```

- `server/`: the Python 3.12 package `simile`, managed with uv. Each module above is a subpackage
  that its task creates. Tests live in `server/tests/<module>/`.
- `client/`: Vite + Phaser 3 + TypeScript. Each area above is a folder under `client/src/`, with
  tests next to the code as `*.test.ts`.
- `content/`: generated assets (tileset, map, NPCs, reference voices), committed.
- `voice-lab/`: standalone scripts with their own virtualenvs. Not part of `make test` or `make lint`.
- F1 owns the top-level files, `server/pyproject.toml`, the root files of `server/simile/` and
  `server/tests/`, and the client scaffolding (`client/*` config files, `client/src/main.ts`,
  `client/src/areas.ts`).

## Running things

Needs [uv](https://docs.astral.sh/uv/) (`brew install uv`), Node 22.12+ (CI uses 24) and make. uv
installs Python 3.12 itself if it's missing, and `make` runs `npm ci` when `client/node_modules` is
stale.

```bash
make test     # server: uv run pytest; client: vitest run
make lint     # server: ruff check + ruff format --check; client: eslint + tsc
make format   # ruff --fix, ruff format, eslint --fix
make dev      # sim server on :8000 (auto-reload) + Vite on http://localhost:5173
```

One side at a time: `make server-test`, `make server-lint`, `make client-test`, `make client-lint`.
One module: `cd server && uv run pytest tests/<module>` or `cd client && npx vitest run src/<area>`.

The Vite dev server proxies `/api/*` and `/ws*` to the sim server, so the client talks to its own
origin.

## Adding to the server without editing shared files

The server finds each module's CLI commands, routes and startup hook by importing every
subpackage's `__init__.py`, `cli.py`, `routes.py` and `lifespan.py`. That happens on every `simile`
command and in Linux CI, so **none of those four files may import MLX, torch or any other optional or
heavy dependency at module level.** Import them inside the function that uses them. Otherwise one
module breaks the CLI and CI for everyone, and the server can no longer run without the voice
dependencies.

**CLI subcommands.** `uv run simile <command>` is a typer app. At startup it imports
`simile.<module>.cli` for every subpackage that has one and calls its `register(app)`. Add a command
by creating `server/simile/<module>/cli.py`; never edit `server/simile/cli.py`.

```python
import typer


def register(app: typer.Typer) -> None:
    @app.command()
    def headless(speed: float = 1.0) -> None:
        """Run the village without a client."""
        from simile.sim.runner import run  # heavy imports go inside the command

        run(speed=speed)
```

For a group of commands (`simile art tiles`), make a `typer.Typer()` and
`app.add_typer(group, name="art")`.

**HTTP and WebSocket routes.** `simile serve` builds a Starlette app from `/api/health` plus the
`routes` list of every `simile.<module>.routes` module. Add endpoints by creating
`server/simile/<module>/routes.py` with `routes: list[starlette.routing.BaseRoute]`, under `/api/`
or `/ws`.

**Startup and shutdown.** For anything that runs as long as the server does, such as a model loaded
once or a refresh interval, create `server/simile/<module>/lifespan.py` with a `lifespan(app)`
async context manager. The server enters every module's lifespan when it starts, in alphabetical
module order, and exits them in reverse when it stops. Modules share objects through `app.state`.
Since the order is alphabetical, don't read another module's `app.state` entry during startup. Look
it up when you use it. `simile headless` runs the same hooks without HTTP.

Work that needs every module set up, like the sim's tick loop, goes in a `running(app)` async
context manager in the same file. The server enters every module's `running` after all the
lifespans have started, and exits them before any lifespan exits. A module can define either hook
or both.

To tick on the sim loop or hear its events, register in your lifespan. The loop starts only once
every module is up. [`server/simile/sim/README.md`](server/simile/sim/README.md) has the details.

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    from simile.sim import EntityMoved, world_of

    world = world_of(app)
    movement = Movement(world)
    unregister = world.loop.register(movement)
    unsubscribe = world.bus.subscribe(EntityMoved, movement.on_moved)
    yield
    unsubscribe()
    unregister()
```

**Dependencies.** Any task may add its own: `cd server && uv add <pkg>` (or `uv add --dev <pkg>`),
then commit `pyproject.toml` and `uv.lock`. Apple Silicon-only packages need a marker so Linux CI
can still resolve and install them:
`uv add mlx-audio --marker "sys_platform == 'darwin' and platform_machine == 'arm64'"`.

## Adding to the client without editing shared files

`client/src/main.ts` collects the `scenes` export of every `client/src/<area>/index.ts`
(`export const scenes = [WorldScene]`) and adds them to the game in area order `scenes`, `world`,
`ui`, `debug`, then any others alphabetically. Later scenes draw on top. The first scene starts
automatically; give overlay scenes `active: true` in their scene config. Areas without scenes
(`net/`, `audio/`) don't export `scenes`.

**Dependencies.** Any task may add its own: `cd client && npm install <pkg>` (or `--save-dev`), then
commit `package.json` and `package-lock.json`. Vitest runs in Node; a test that needs a DOM adds
`jsdom` as a dev dependency and starts with `// @vitest-environment jsdom`.

## Tests that need Apple Silicon

Mark tests that need MLX, TTS or voice design with `@pytest.mark.mlx`. They run only on macOS arm64
with `mlx` importable and are skipped everywhere else, including CI (hosted runners have no Metal).
Import MLX inside the test or with `pytest.importorskip("mlx")`, never at module level, so the file
still collects on Linux. Run them locally on a Mac with `make server-test`.

## CI

`.github/workflows/server.yml` (*Server tests (pytest)*, *Server lint (ruff)*) and
`.github/workflows/client.yml` (*Client tests (vitest)*, *Client lint (eslint + tsc)*, *Client build
(vite)*) run the same make targets on every PR and on main, against the committed lockfiles
(`uv sync --locked`, `npm ci`).

New tests are found automatically (`server/tests/**/test_*.py`, `client/src/**/*.test.ts`), so most
tasks never touch CI. Don't edit the shared workflows for one module's needs. If a module needs
extra setup in CI (a system package, a check on generated assets), add its own
`.github/workflows/<module>.yml` with job names starting with the module, and reuse the setup
actions:

```yaml
name: Voice
on:
  pull_request:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  test:
    name: Voice tests (ffmpeg)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: ./.github/actions/setup-server   # or setup-client
      - run: sudo apt-get install -y ffmpeg
      - run: uv run pytest tests/voice
        working-directory: server
```

Tests that need that setup must skip cleanly without it (e.g.
`pytest.mark.skipif(shutil.which("ffmpeg") is None, reason=...)`) so the shared jobs stay green.

## Lockfile conflicts

After `git merge origin/main`, resolve `pyproject.toml` or `package.json` by hand, then regenerate
the lockfile from main's copy rather than merging it:

```bash
git checkout origin/main -- server/uv.lock && (cd server && uv lock) && git add server/uv.lock
git checkout origin/main -- client/package-lock.json && (cd client && npm install) && git add client/package-lock.json
```
