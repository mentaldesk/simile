# simile.world

The village, the floors of its buildings, and how entities move along its streets, up and down,
and through its doors. The side-view maps are described in
[`content/street/README.md`](../../../content/street/README.md); `simile.world.map.load_maps()`
loads them all by id, and `load_map(path)` one. Positions saved on the isometric maps before #314
are moved onto them as they load (`simile.persistence`).

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
| `place(entity, target)` | Puts an entity on the target, ending any walk, and returns the `MapTile` it's on. |
| `walk_to(entity, target)` | Starts a walk there, ending any walk already going, and returns a `Walk`. |
| `stop(entity)` | Cancels the entity's walk. |
| `position(entity)` | A `Point(x, y, map)` in tiles. Fractions are mid-step. |
| `entities()` | `{id: Point}` for every entity. |
| `distance(a, b)` | Straight-line distance between two entities, in tiles, or `math.inf` if they're on different maps. For hearing and talking, `simile.voicing.distance.between` measures along the street. |
| `intend(entity, purpose)` | What they're at their next place for, which says which spots suit them (see *Spots*). `None` for nothing in particular. |
| `posture(entity)` | Their `(Pose, Facing)`. |
| `on_spot(entity)` | The `Spot` they've stopped on, or `None`. |
| `track(entity, point)` | Records where something the client moves is. The lifespan calls it with the player's position and map on every `player_move`, so `position("player")` raises `KeyError` until the first one. It logs and drops a move onto a map that isn't loaded, and on a side-view map one to where nobody could be, by `simile.street.moves.possible`: a jump or a fall in open air is kept where it is (`docs/protocol.md`). |
| `town` | The first street's `TownMap`, carrying every map's locations, doors and mural walls, so `town.location(id)` finds any of them. |
| `maps` | Every `TownMap` by id. `TownMap.street` says whether one is outdoors. |
| `crossings` | Each end of every link, its `DoorKind` and how long crossing it takes, in tiles of walking. |
| `rise(location)` | How far up each of its floors' maps is stacked, in tiles, so its floors measure as one picture. |

`Movement(maps, bus)` takes the maps by id, or a single `TownMap`.

A `Point` unpacks, measures and compares with a plain `(x, y)` like a pair, so `math.dist` and
`x, y = point` work. Two points on different maps are never equal.

A target is a location id, a `MapTile`, or a `Tile`, which is on `home`, the first street.

- **A location** means a free spot there that suits what the entity is there for (see *Spots*), or
  else its entry tile. If someone else has that, it's the nearest free walkable tile in the
  location's area that isn't a spot, then on each of its other floors in turn, or outside the area
  if they're all full. An entity already in the area, and not on a spot, stays where it is.
- Nobody is put partway up stairs or a ladder while there's a cell to stand on nearby, unless they
  walk there on purpose.
- **A tile** means that tile or, if it's taken, the nearest free one on its map, on the walker's
  side. So walking to another NPC's tile ends next to them.
- **Taken** means another entity is standing on it or walking to it, so two entities never end up on
  the same tile. If someone steps onto a walker's destination, the walker picks another.
- A wall, a cut-off tile or a map with no door to it makes the walk `UNREACHABLE`, and `place`
  raises `ValueError` for a tile off its map. Placed on a cell of a map where nobody can stand, as a
  saved one can be after the maps change, an entity goes to the nearest standing cell to it. Unknown
  entities, locations and maps raise `KeyError`.

### Walks

- `await walk` returns an `Outcome` and never raises: `ARRIVED`, `UNREACHABLE`, `CANCELLED` (by
  `stop` or `place`) or `SUPERSEDED` (by another `walk_to`). From a tick, poll `walk.outcome`, which
  is `None` until it ends, or use `walk.add_done_callback(callback)`. A callback that raises is
  logged and doesn't affect the others.
- `walk.destination` is the `MapTile` it's heading for and `walk.distance` its length in tiles, on
  every map it crosses, so it takes `walk.distance / WALKING_SPEED` sim seconds.
- Entities walk at `simile.world.map.WALKING_SPEED`, 1.3 tiles per sim second, at any sim speed.
- Paths are A\* on each map's grid by its neighbour rule, `simile.street.moves`: left and right
  along a row, and up and down only along stairs and ladders. `jumps=True` on `steps`, `nearby`
  and `find_route` adds the player's jumps; residents never jump.
- Each link is an edge between its two tiles. Going through a door takes as long as a step
  (`simile.world.paths.DOOR`, 1 tile). Stairs, a ladder or a lift to another floor take as long as
  the climb or ride, at `CROSSING_SPEED` (1.3, 1 and 2.4 tiles a second) with the floors stacked,
  as the client plays it, so a lift goes straight to the floor wanted. The walker stands on the
  link's tile until it's through, then is on the tile at the other end.
- Entities only stop on whole tiles. A walk that ends early finishes the step it's on, or goes
  through the door it has started through, and a new walk starts from that tile. If someone else has that tile,
  the entity steps on to the nearest free one.
- Walkers pass through each other.

## Spots

Each place has spots: somewhere to spend a stay, each a walkable tile with a kind and a way to
face, in the maps' `spots` layer ([`content/street/README.md`](../../../content/street/README.md#objects)).
`TownMap.spots` has a map's, and `spot_at(x, y)` the one on a tile.

| Kind | Pose | Where |
|---|---|---|
| `seat` | `sitting` | Beside each café and noodle-bar table, on the noodle bar's stools, on the benches on the square, in the park and in the gallery |
| `bar` | `sitting` | On the stools along the Daily Grind's bar |
| `desk` | `working` | Both sides of the maker space's workbenches, and in front of its machines |
| `terminal` | `reading` | In front of each news terminal's screen |
| `viewing` | `looking` | In front of each painting in the gallery and each mural wall |
| `standing` | `standing` | Around the square's fountain and by its lamps |
| `bed` | `sleeping` | On the head of the bed in each house and in the barista's flat |

**Taking one.** `intend(entity, purpose)` says what they're at their next place for, a
`simile.world.spots.Purpose`. The world's lifespan sets it from B1's `GoalChosen`, which behaviour
publishes before it starts the walk (`purpose_of`): the coffee shop is for a drink, the noodle bar
for eating, a terminal for reading, the maker space and making something for making, the gallery for
looking, the park for relaxing, the square for lingering and home at bedtime for sleeping. At work
it's what the place is for, except at the café and the noodle bar, whose staff serve rather than
take a spot. A walk to a location then ends on a free spot that suits the purpose
(`SpotConfig.fits`):

| Purpose | Spots |
|---|---|
| eat | a seat |
| drink | the bar or a seat |
| read | a terminal |
| make | a desk, or a seat at the café |
| look | a viewing spot, or a bench |
| relax | a seat |
| linger | a standing spot or a bench |
| sleep | a bed, on any floor of their home |

Of the free ones they take the best: near people they like and away from people they dislike, by
`movement.affinity(a, b)`, each person's liking counting more the nearer they sit, within `near` (3)
tiles of the seat; then their own taste, a liking for each spot that's the same every time, so
residents have their usual; then the shortest walk. The lifespan plugs B1's affinity in, read when
it's used, the way places score it. Someone already on a suitable spot there stays on it. With no
spot free, they stand nearby as before, on a tile that isn't a spot.

**Poses.** Stopped on a spot, an entity takes its pose and faces its way, however they got there:
the café seats its customers itself. A muralist on a mural wall's viewing spot is `working`.
Partway up stairs or a ladder they're `climbing`. Anywhere else they're `standing`, facing the way
they last stepped. On their way they're `walking`, facing each step, or `climbing` on stairs and a
ladder, facing `north` on a ladder. At the end of stairs, a ladder or a lift to another floor
they're `climbing` or `riding` until they're through. `posture(entity)` is their `(pose, facing)`,
for the snapshot, and `on_spot(entity)` the spot they've stopped on, if any.

**Taste** is keyed by the place a spot is in (`choose(..., place=)`), so the regulars of the café,
the noodle bar, the gallery and the maker space, whose maps were named after their places on the
isometric maps, keep their usual spots.

## `EntityMoved`

The bus's `EntityMoved` reaches clients as `entity_moved`, with the map, the pose and the facing.
Movement publishes it:

- when an entity is placed,
- each time a walking entity reaches a tile, including the one it stops on and the far end of a
  link,
- as one sets off from the end of stairs, a ladder or a lift to another floor, `climbing` or
  `riding`, and
- when an entity stops without a step, as when a walk is cancelled, if that changes its pose or
  facing.

So positions are always whole tiles (`x=43.0, y=15.0, map='high_street'`), and consecutive
positions of a walking entity are neighbouring tiles on the same map, or the two ends of a link. A
walker sends one every 0.77 sim seconds (1.09 s a stair), however many ticks that is: 13 a real
second at 10x. Player moves aren't published back to the client; one without a map is ignored.

To animate a walker, tween its doll from where it's drawn to each new position over
`distance / WALKING_SPEED` sim seconds (real seconds under `simile serve`, which runs at 1x). The
next position arrives as the tween ends, so the doll moves continuously, one tile behind the
server. A jump of more than a tile and a half, or onto another map, is a `place`: snap to it. Face
the direction of travel. Once it has stopped, draw its pose facing the way it's given, on the spot's
seat if it's on one.
