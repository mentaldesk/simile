# simile.world

The village, the interiors of its buildings, and how entities move around them and through their
doors. The maps are described in [`content/map/README.md`](../../../content/map/README.md);
`simile.world.map.load_maps()` loads them all by id, and `load_map()` the village.

## Movement

`movement_of(app)` returns the server's `Movement` over every map, creating it on first use, so any
module can get it from its lifespan. The `world` lifespan ticks it on the sim loop.

```python
from simile.world import Outcome, movement_of

movement = movement_of(app)
movement.place("mei", "house_1")
walk = movement.walk_to("mei", "coffee_shop_queue")
if await walk is Outcome.ARRIVED:
    ...
```

| | |
|---|---|
| `place(entity, target)` | Puts an entity on the target, ending any walk, and returns the `Tile` it's on. |
| `walk_to(entity, target)` | Starts a walk there, ending any walk already going, and returns a `Walk`. |
| `stop(entity)` | Cancels the entity's walk. |
| `position(entity)` | A `Point(x, y, map)` in tiles. Fractions are mid-step. |
| `entities()` | `{id: Point}` for every entity. |
| `distance(a, b)` | Straight-line distance between two entities, in tiles, or `math.inf` if they're on different maps. |
| `track(entity, point)` | Records where something the client moves is. The lifespan calls it with the player's position and map on every `player_move`, so `position("player")` raises `KeyError` until the first one. |
| `town` | The village's `TownMap`, carrying every map's locations, so `town.location(id)` finds any of them. An id on two maps is the village's. |
| `maps` | Every `TownMap` by id. |

`Movement(maps, bus)` takes the maps by id, or a single `TownMap`.

A `Point` unpacks, measures and compares with a plain `(x, y)` like a pair, so `math.dist` and
`x, y = point` work. Two points on different maps are never equal.

A target is a location id, a `MapTile`, or a `Tile`, which is on the village.

- **A location** means its entry tile. If someone else has that, it's the nearest free walkable tile
  in the location's area, or outside the area if that's full. An entity already in the area stays
  where it is.
- **A tile** means that tile or, if it's taken, the nearest free one on its map, on the walker's
  side. So walking to another NPC's tile ends next to them.
- **Taken** means another entity is standing on it or walking to it, so two entities never end up on
  the same tile. If someone steps onto a walker's destination, the walker picks another.
- A wall, a cut-off tile or a map with no door to it makes the walk `UNREACHABLE`, and `place`
  raises `ValueError`. Unknown entities, locations and maps raise `KeyError`.

### Walks

- `await walk` returns an `Outcome` and never raises: `ARRIVED`, `UNREACHABLE`, `CANCELLED` (by
  `stop` or `place`) or `SUPERSEDED` (by another `walk_to`). From a tick, poll `walk.outcome`, which
  is `None` until it ends, or use `walk.add_done_callback(callback)`. A callback that raises is
  logged and doesn't affect the others.
- `walk.destination` is the `Tile` it's heading for and `walk.distance` its length in tiles, on
  every map it crosses, so it takes `walk.distance / WALKING_SPEED` sim seconds.
- Entities walk at `simile.world.map.WALKING_SPEED`, 1.3 tiles per sim second, at any sim speed.
- Paths are A\* on each map's grid in 8 directions. A diagonal step needs both tiles beside it to be
  walkable, so nobody cuts a corner.
- Each door is an edge between its two tiles. Going through takes as long as a step
  (`simile.world.paths.DOOR`, 1 tile): the walker stands on the door's tile until it's through, then
  is on the tile at the other end.
- Entities only stop on whole tiles. A walk that ends early finishes the step it's on, or goes
  through the door it's in, and a new walk starts from that tile. If someone else has that tile,
  the entity steps on to the nearest free one.
- Walkers pass through each other.

## `EntityMoved`

The bus's `EntityMoved` reaches clients as `entity_moved`, with the map. Movement publishes it:

- when an entity is placed, and
- each time a walking entity reaches a tile, including the one it stops on and the far end of a
  door.

So positions are always whole tiles (`x=31.0, y=11.0, map='village'`), and consecutive positions of
a walking entity are neighbouring tiles on the same map, diagonals included, or the two ends of a
door. A walker sends one every 0.77 sim seconds (1.09 s on a diagonal), however many ticks that is:
13 a real second at 10x. Player moves aren't published back to the client.

To animate a walker, tween its sprite from where it's drawn to each new position over
`distance / WALKING_SPEED` sim seconds (real seconds under `simile serve`, which runs at 1x). The
next position arrives as the tween ends, so the sprite moves continuously, one tile behind the
server. A jump of more than a tile and a half, or onto another map, is a `place`: snap to it. Face
the direction of travel.

## Demo

```bash
cd server && SIMILE_DEMO_WALK=1 uv run simile headless --speed 10
```

Mei, F2's fixture NPC from `house_1`, walks into the Daily Grind to the front of the counter's
queue and back, resting 30 sim seconds at each end. The log shows every tile she reaches, the
jump through the door, and, for each trip, its length, time and speed. `simile serve` runs the
demo too when the variable is set.
