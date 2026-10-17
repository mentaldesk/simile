# simile.jobs

Slow, machine-bound asset work for the character creator, run as server jobs. Each job is a
subprocess, so it can't block the sim, and a job keeps going when the client that started it
disconnects. Only one job of a kind runs at a time; later ones wait in order, at most 4 of them.

## Routes

| Route | What it does |
|---|---|
| `GET /api/jobs/capabilities` | What this machine can run (below). |
| `POST /api/jobs` | Starts a job from `{"kind": "sprite", "params": {...}}`. 202 with the job, 422 with `{"error": reason}` for a bad request, 429 when too many of that kind are waiting. |
| `GET /api/jobs`, `GET /api/jobs/{id}` | The jobs since the server started (the latest 100 that finished), or one of them. |
| `POST /api/jobs/{id}/cancel` | Stops a waiting or running job, killing its subprocess and anything it started, and returns it. 409 once it has finished. |
| `WS /ws/jobs/{id}` | Sends the job as JSON now and after every change, then closes once it has finished. Close code 4404 for an unknown job. Leaving early doesn't stop the job. |
| `GET /api/jobs/files/{kind}/{name}` | A file a job published, named in its `result`. |

A job looks like this. `state` is `queued`, `running`, `succeeded`, `failed` or `cancelled`, and
`error` says why a job failed.

```json
{
  "id": "3f9c2a7d1b6e4c08",
  "kind": "sprite",
  "state": "succeeded",
  "progress": 1.0,
  "message": "Drawn",
  "error": null,
  "result": {
    "image": "/api/jobs/files/sprite/new_face.png",
    "atlas": "/api/jobs/files/sprite/new_face.json"
  },
  "created": "2026-10-18T09:30:00Z",
  "started": "2026-10-18T09:30:00Z",
  "finished": "2026-10-18T09:30:01Z"
}
```

## Capabilities

The server checks once at startup whether Blender is found (`$BLENDER`, the `PATH`, then the macOS
app), whether it's on Apple Silicon, and whether `voice-lab/.venv` and `voice-lab/.venv-mlx` exist.
`/api/jobs/capabilities` reports those under `machine`, and under `kinds` whether each kind can run
here, so the creator can hide what can't:

```json
{
  "machine": {"blender": true, "apple_silicon": true, "voice_lab": false, "voice_lab_mlx": true},
  "kinds": {"sprite": {"available": true, "reason": null}}
}
```

A job whose kind needs something missing fails as soon as it's submitted, with the same `reason`.

## Sprite jobs

`{"kind": "sprite", "params": {"character": "new_face", "appearance": {...}}}` draws the character's
pixel-art sprite sheet from its `Appearance` with A1's generator, seeded by its id as `simile art`
seeds an NPC's. The result has the sheet's `image` and its Phaser `atlas`, in the same format as
`content/art/characters/`. Drawing a character again replaces its sprite. A character id that has a
sprite or an NPC file in `content/` is refused.

## Where jobs write

Under `$SIMILE_JOBS`, or `server/data/jobs/` (ignored by git), and never in `content/`: the runner
refuses a directory there. A job runs in `work/<id>/`, which is deleted when it ends. Only when it
succeeds are its outputs moved to `<kind>/`, and only names its kind declares are served from there.

## Adding a kind

Make a `Kind` and register it in your module's lifespan. `jobs_of(app)` works before or after
`jobs` starts.

```python
from simile.jobs import Kind, jobs_of, url

DESIGN = Kind(
    "voice_design",
    VoiceDesign,  # a pydantic model: the job's params
    command=lambda params, work: [VENV_PYTHON, str(SCRIPT), str(work)],
    publish=publish,  # (params, work, out) -> result: moves outputs from work into out
    requires=("apple_silicon", "voice_lab", "voice_lab_mlx"),
    files=r"[a-z0-9_]+\.wav",
)


@asynccontextmanager
async def lifespan(app):
    unregister = jobs_of(app).register(DESIGN)
    yield
    unregister()
```

The command runs in `work`, where the runner has written the params as `params.json`. It reports
progress by printing `simile.jobs.report.progress(fraction, message)`'s line, `JOB {"progress": 0.5,
"message": "..."}`. Anything else it prints is kept, and the last 20 lines are the error if it exits
with a non-zero code. Cancelling sends its process group SIGTERM, then SIGKILL after 5 s.
