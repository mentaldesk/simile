# simile.sim

The world clock, the tick loop and the event bus. Every other part of the village runs on them.

## The world

A `World` holds a `clock`, a `loop` and a `bus`. `simile serve` and `simile headless` each run one,
on `app.state.world`. Get it in your module's lifespan with `world_of(app)`. It creates the world on
first use, so it works before or after `sim` in the alphabet.

```python
from contextlib import asynccontextmanager

from simile.sim import EntityMoved, world_of


@asynccontextmanager
async def lifespan(app):
    world = world_of(app)
    movement = Movement(world)
    unregister = world.loop.register(movement)
    unsubscribe = world.bus.subscribe(EntityMoved, movement.on_moved)
    yield
    unsubscribe()
    unregister()
```

In `simile serve`, the `sim` module's `running` hook runs the loop at 1x. It starts after every
module's lifespan has started and stops before any of them exits, so systems never tick while a
module is still setting up or has already shut down.

## Clock

- `clock.now` is sim time as a timezone-aware UTC `datetime`, and UTC is village-local time. Setting
  a naive datetime raises `ValueError`; any other time zone is converted to UTC.
- `clock.time_of_day` is the hours since midnight, from 0 up to 24.
- `clock.speed` is sim seconds per real second. Changing it takes effect from the next tick.
- A new clock starts at 08:00 UTC today unless you pass `start`.

## Tick loop

- `world.loop.register(system)` adds anything with a `tick(dt: float)` method and returns a
  function that unregisters it. `dt` is in sim seconds and is always `STEP` (0.1). The clock has
  already advanced when `tick` is called.
- Systems tick in the order they registered, which is lifespan order, so alphabetical by module.
  A system registered mid-run ticks from the next tick.
- `tick` must not block or await. Start an asyncio task for slow work like LLM calls or TTS.
- The step is fixed. At 10x the loop runs 100 ticks per real second instead of 10, so a run at 10x
  is the same sequence of ticks as at 1x, only faster. If the host can't keep up, the loop runs
  ticks back to back and the world falls behind real time rather than taking bigger steps. It drops
  any backlog beyond a second.
- A system that raises stops the loop. `simile serve` logs it; `simile headless` exits with the
  error.

## Event bus

- `world.bus.publish(event)` calls the matching handlers straight away, in the order they
  subscribed.
- `world.bus.subscribe(EntityMoved, handler)` returns a function that unsubscribes. Subscribe to
  `Event` to receive every event.
- A handler that raises is logged and doesn't affect the publisher or the other handlers.
- Handlers must not block. To pass events to async code such as a WebSocket, put them on an
  `asyncio.Queue` with `put_nowait`.

Events are frozen dataclasses. They refer to entities by id and carry the
[schema](../schema/) models:

| Event | Fields |
|---|---|
| `EntityMoved` | `entity` (an id), `x`, `y` (in tiles), `map` (the map's id), `pose` and `facing` (standing, facing south-east by default) |
| `ConversationStarted` | `conversation`: a `Conversation` |
| `LineSpoken` | `line`: a `Line`, with its id, speaker, text, timestamp and duration |
| `ConversationEnded` | `conversation`: a `Conversation`, with its lines and `ended` set |

Subscribers get the model you published, not a copy. If you'll keep changing it, as a conversation
gains lines, publish `model.model_copy(deep=True)`.

Define more in your own module by subclassing `Event`:

```python
@dataclass(frozen=True)
class NewsRead(Event):
    npc_id: str
    news_id: str
```

## Headless

`uv run simile headless --speed 10 --duration 24` starts every module's lifespan, as `simile serve`
does but without HTTP, and runs the loop for 24 sim hours, logging every event with its sim time.
Without `--duration` it runs until Ctrl-C or SIGTERM, which stop it after the current tick and
shut the modules down normally. A second Ctrl-C while they shut down exits at once, with code 130.
`app.state.headless` is `True`, so the `sim` module's `running` hook leaves the loop to the
headless runner.

## Tests

Give the world a `FakeWallClock` and a fixed start. Its `sleep` returns at once, so runs are
instant and deterministic:

```python
world = World(Clock(datetime(2026, 1, 1, 8, tzinfo=UTC), speed=10), FakeWallClock())
world.loop.register(movement)
asyncio.run(world.loop.run(timedelta(minutes=5)))
```

`world.loop.tick()` advances a single step without asyncio.
