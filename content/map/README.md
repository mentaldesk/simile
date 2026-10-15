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
  marked and its id.

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

Each location object's `name` is its id, its `type` is its F2 `LocationKind`, and its rectangle is
its `area` in pixels. Its properties are `label` (the location's `name`) and `entry_x`, `entry_y`
(the entry tile). Every entry is a walkable tile inside its area, in front of the door for
buildings, and every walkable tile can reach every other.

| Ids | |
|---|---|
| `house_1` … `house_10` | Homes on Lychee Lane, Kapok Walk and Banyan Row |
| `coffee_shop` | The Daily Grind, on the north side of the square |
| `square` | The town square |
| `terminal_1` … `terminal_3` | News terminals on the square, at the park gate and by the river |
| `park`, `noodle_bar`, `maker_space` | Amenities |

**Scale.** The sprites are 1.5 tiles tall, so a tile is about 1.1 m, and walking at 1.4 m/s is about
1.3 tiles/s. At that pace, crossing from west to east takes about 50 s and the farthest two
locations are about 55 s apart.

## Loading it

Server: `simile.world.map.load_map()` returns a `TownMap` with `width`, `height`, `walkable(x, y)`
(false off the map), `blocked[y][x]`, `locations` (F2 `Location`s) and `location(id)`.

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
