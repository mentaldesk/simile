# simile.world

The village map and how entities move around it. The map itself is described in
[`content/map/README.md`](../../../content/map/README.md); `simile.world.map.load_map()` loads it.

## Movement

`movement_of(app)` returns the server's `Movement`, creating it on first use, so any module can get
it from its lifespan. The `world` lifespan ticks it on the sim loop.

```python
from simile.world import Outcome, movement_of

movement = movement_of(app)
movement.place("mei", "house_1")
walk = movement.walk_to("mei", "coffee_shop")
if await walk is Outcome.ARRIVED:
    ...
```

| | |
|---|---|
| `place(entity, target)` | Puts an entity on the target, ending any walk, and returns the `Tile` it's on. |
| `walk_to(entity, target)` | Starts a walk there, ending any walk already going, and returns a `Walk`. |
| `stop(entity)` | Cancels the entity's walk. |
| `position(entity)` | A `Point(x, y)` in tiles. Fractions are mid-step. |
| `entities()` | `{id: Point}` for every entity. |
| `distance(a, b)` | Straight-line distance between two entities, in tiles. |
| `track(entity, point)` | Records where something the client moves is. The lifespan calls it with the player's position on every `player_move`. |
| `town` | The `TownMap`. |

A target is a `Tile` or a location id.

- **A location** means its entry tile. If someone else has that, it's the nearest free walkable tile
  in the location's area, or outside the area if that's full. An entity already in the area stays
  where it is.
- **A tile** means that tile or, if it's taken, the nearest free one, on the walker's side. So
  walking to another NPC's tile ends next to them.
- **Taken** means another entity is standing on it or walking to it, so two entities never end up on
  the same tile. If someone steps onto a walker's destination, the walker picks another.
- A wall or a cut-off tile makes the walk `UNREACHABLE`, and `place` raises `ValueError`. Unknown
  entities and locations raise `KeyError`.

### Walks

- `await walk` returns an `Outcome` and never raises: `ARRIVED`, `UNREACHABLE`, `CANCELLED` (by
  `stop` or `place`) or `SUPERSEDED` (by another `walk_to`). From a tick, poll `walk.outcome`, which
  is `None` until it ends, or use `walk.add_done_callback(callback)`.
- `walk.destination` is the `Tile` it's heading for and `walk.distance` its length in tiles, so it
  takes `walk.distance / WALKING_SPEED` sim seconds.
- Entities walk at `simile.world.map.WALKING_SPEED`, 1.3 tiles per sim second, at any sim speed.
- Paths are A\* on the map's grid in 8 directions. A diagonal step needs both tiles beside it to be
  walkable, so nobody cuts a corner.
- Entities only stop on whole tiles. A walk that ends early finishes the step it's on, and a new
  walk starts from that tile.
- Walkers pass through each other.

## `EntityMoved`

The bus's `EntityMoved` reaches clients as `entity_moved`. Movement publishes it:

- when an entity is placed, and
- each time a walking entity reaches a tile, including the one it stops on.

So positions are always whole tiles (`x=31.0, y=11.0`), and consecutive positions of a walking
entity are neighbouring tiles, diagonals included. A walker sends one every 0.77 sim seconds
(1.09 s on a diagonal), however many ticks that is: 13 a real second at 10x. Player moves aren't
published back to the client.

To animate a walker, tween its sprite from where it's drawn to each new position over
`distance / WALKING_SPEED` sim seconds (real seconds under `simile serve`, which runs at 1x). The
next position arrives as the tween ends, so the sprite moves continuously, one tile behind the
server. A jump of more than a tile and a half is a `place`: snap to it. Face the direction of
travel.

## Demo

```bash
cd server && SIMILE_DEMO_WALK=1 uv run simile headless --speed 10
```

Mei, F2's fixture NPC from `house_1`, walks to the coffee shop and back, resting 30 sim seconds at
each end. The log shows every tile she reaches and, for each trip, its length, time and speed.
`simile serve` runs the demo too when the variable is set.
