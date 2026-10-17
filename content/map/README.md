# Map

`village.tmj` is the village (map id `village`), a Tiled JSON map built from A1's tileset by
`server/simile/world/build_map.py`. Don't edit it by hand or save it from Tiled: change the builder
and run

```bash
cd server && uv run simile map
```

Output is deterministic, and `tests/world` fails if the map or the previews drift from the builder.
Tiled opens the map for a look around.

- [`preview.png`](preview.png): the whole map at 2×.
- [`locations.png`](locations.png): the same with each location's area outlined, its entry tile
  marked and its id, and each mural wall in cyan: a bar along its face, its standing tile and its
  id.

## Layout

64 × 42 tiles of 16 px, orthogonal, with the `simile` tileset embedded (`firstgid` 1). Layers,
bottom to top:

| Layer | |
|---|---|
| `ground` | Terrain: pavement, plaza, grass, road, water. Every cell is filled. |
| `buildings` | Roofs and facades. |
| `decor` | Props, signs and awnings, drawn under characters. |
| `above` | Tree crowns and the tops of lamps, palms and terminals, drawn over characters. |
| `collision` | Hidden. A `blocked` tile marks every cell where some tile on another layer has `collides`. |
| `locations` | Objects, one rectangle per location. |
| `murals` | Objects, one rectangle per mural wall. |

Each location object's `name` is its id, its `type` is its F2 `LocationKind`, and its rectangle is
its `area` in pixels. Its properties are `label` (the location's `name`) and `entry_x`, `entry_y`
(the entry tile). Every entry is a walkable tile inside its area, in front of the door for
buildings, and every walkable tile can reach every other.

| Ids | |
|---|---|
| `house_1` … `house_10` | Homes on Lychee Lane, Kapok Walk and Banyan Row |
| `coffee_shop` | The Daily Grind, on the north side of the square. Its area takes in the terrace. |
| `square` | The town square |
| `terminal_1` … `terminal_3` | News terminals on the square, at the park gate and by the river |
| `park`, `noodle_bar`, `maker_space` | Amenities |

## Mural walls

The `murals` layer has the walls residents paint murals on, in the shape of M1's `murals` message
([`docs/protocol.md`](../../docs/protocol.md#murals)). Each object's `name` is the wall's id, its
`type` is `mural_wall`, and its rectangle covers the wall's tiles: part of a building's south row
for a wall facing `south`, or of its east column for one facing `east`. Its properties are:

| Property | |
|---|---|
| `face` | `south` or `east`, the faces the iso camera sees. The face runs along the rectangle's south or east edge. |
| `bottom`, `top` | The mural's lower and upper edges, in storeys above the ground. A storey is 3 m in the iso renders. |
| `stand_x`, `stand_y` | Where the painter stands: the walkable tile in front of the middle of the wall. |

Every wall is blank. The iso renders draw windows, doors and signs only on south faces, so east
faces are plain, and a south wall has none across the storeys it covers. Nothing stands between a
wall and the iso camera, so the whole mural shows, and no two walls share a building.
`tests/world/test_murals.py` checks all of this.

| Id | Where | Face | Tiles | Storeys |
|---|---|---|---|---|
| `corner_shop` | The 24-hour shop next to the noodle bar, facing the crossing | east | 4 | 0.7–2.85 |
| `daily_grind` | The Daily Grind, above its awnings on the square | south | 3 | 1.05–1.9 |
| `tower` | The tower at the east end of Lychee Lane, by the park | east | 5 | 0.15–3 |
| `garden_flats` | The flats on Banyan Row, facing the garden south of the square | east | 4 | 0.15–2.5 |
| `banyan_row` | 3 Banyan Row, a street up from the river | east | 3 | 0.15–1.85 |

**Scale.** The map is sized for `simile.world.map.WALKING_SPEED`, 1.3 tiles per sim second. The
sprites are 1.5 tiles tall, so a tile is about 1.1 m, and 1.3 tiles/s is a 1.4 m/s walk. At that
speed, crossing from west to east takes about 50 s and the farthest two locations are about 55 s
apart. W2 moves entities at `WALKING_SPEED` and B1 plans trips with it. At a typical game speed of
around 4 tiles/s the village would feel three times smaller.

## Loading it

Server: `simile.world.map.load_map()` returns a `TownMap` with `width`, `height`, `walkable(x, y)`
(false off the map), `blocked[y][x]`, `locations` (F2 `Location`s), `location(id)`, `murals` and
`mural(id)`. A `MuralWall` has the `id`, `x`, `y`, `width`, `face`, `bottom` and `top` of M1's
`Wall`, and `stand`, the F2 `Tile` its painter stands on.

Phaser (3.90 loads it as is):

```ts
this.load.image('tiles', 'art/tiles.png');
this.load.tilemapTiledJSON('village', 'map/village.tmj');
// later
const map = this.make.tilemap({ key: 'village' });
const tiles = map.addTilesetImage('simile', 'tiles')!;
for (const name of ['ground', 'buildings', 'decor']) map.createLayer(name, tiles);
// characters go here, then
map.createLayer('above', tiles);
const locations = map.getObjectLayer('locations')!.objects;
```
