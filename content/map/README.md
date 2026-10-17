# Map

`village.tmj` is the village (map id `village`), and `interiors/<id>.tmj` are the insides of its
buildings (map id `<id>`). They're Tiled JSON maps built from A1's tileset by
`server/simile/world/build_map.py`. Don't edit them by hand or save them from Tiled: change the
builder and run

```bash
cd server && uv run simile map
```

Output is deterministic, and `tests/world` fails if a map or a preview drifts from the builder.
Tiled opens the maps for a look around.

- [`preview.png`](preview.png): the whole village at 2×.
- [`locations.png`](locations.png): the same, with each location's area outlined, its entry tile
  marked and its id, each door's tile outlined in green, and each mural wall in cyan: a bar along
  its face, its standing tile and its id.
- `interiors/<id>_preview.png` and `interiors/<id>_locations.png`: each interior at 3×, the same
  way. Interactables are outlined in orange, with their stand tiles marked and their ids.

## Layout

The village is 64 × 42 tiles of 16 px, orthogonal, with the `simile` tileset embedded (`firstgid`
1). Every map, village or interior, has the same layers, bottom to top:

| Layer | |
|---|---|
| `ground` | Terrain: pavement, plaza, grass, road, water, or an interior's floor. Every cell is filled. |
| `buildings` | Roofs and facades, or an interior's walls. |
| `decor` | Props, signs and awnings, or an interior's furniture, wall hangings and mat. |
| `above` | Tree crowns and the tops of lamps, palms and terminals. |
| `collision` | Hidden. A `blocked` tile marks every cell where some tile on another layer has `collides`. |
| `locations` | Objects, one rectangle per location. |
| `murals` | Objects, one rectangle per mural wall. Empty in interiors. |
| `doors` | Objects, one tile per door with an end on this map. |
| `interactables` | Objects, one rectangle per thing you can use. Empty on the village. |

Each location object's `name` is its id, its `type` is its F2 `LocationKind`, and its rectangle is
its `area` in pixels. Its properties are `label` (the location's `name`) and `entry_x`, `entry_y`
(the entry tile). Every entry is a walkable tile inside its area, in front of the door for
buildings, and every walkable tile can reach every other. A location's `map` is the map it's on.

| Ids | |
|---|---|
| `house_1` … `house_10` | Homes on Lychee Lane, Kapok Walk and Banyan Row |
| `coffee_shop` | The Daily Grind, on the north side of the square. Its area takes in the terrace. |
| `noodle_bar` | Golden Bowl Noodles, on Lychee Lane |
| `maker_space` | Spark Maker Space, on Lychee Lane |
| `square` | The town square |
| `terminal_1` … `terminal_3` | News terminals on the square, at the park gate and by the river |
| `park` | Lotus Lake Park, the one `amenity` |

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

## Interiors

An interior is bigger on the inside: its size has nothing to do with its building's footprint. The
shops are 20 × 14 tiles and the gallery is 32 × 20.

- **Walls.** The back (north) wall takes the top two rows, face on: `inwall_<finish>` with the
  wall's top, over `inwall_<finish>_base`. The side and front walls show only their tops
  (`inwall_top_w`, `_e`, `_s`, `_sw`, `_se`), with the dark outside beyond them. The finishes are
  `panel` (the café), `brick` (the noodle bar), `block` (the maker space) and `plaster` (the
  gallery). A free-standing wall is the same two rows, with `_l` and `_r` ends.
- **Floor.** Everything inside the walls, from `(1, 2)` down to the row above the front wall.
- **Doorway.** A gap in the front wall with the `mat` in it. The mat is the door's inside end.
- **Locations.** Each interior's own location, with the interior's id, covers its floor. Its entry
  is somewhere sensible inside.

| Map | Name | Inside |
|---|---|---|
| `coffee_shop` | The Daily Grind | A back counter with espresso machines and a grinder, then the counter with the till and the pastry cases, then tables. The counter turns north at its east end and leaves a gap by the west wall for the staff. |
| `noodle_bar` | Golden Bowl Noodles | A kitchen with stoves along the back wall, the counter with stools in front, and tables. No interactables yet. |
| `maker_space` | Spark Maker Space | Four machines along the back wall and two rows of workbenches. |
| `gallery` | The Gallery | 13 paintings, 7 on the back wall and 3 on each of two free-standing walls, with benches facing them and two plinths. |

**The Daily Grind's counter.** For G1 (#172) the coffee shop has two more locations. Both are of
kind `amenity`, so behaviour, which picks trips by kind, doesn't send residents there.

| Id | Area | Entry |
|---|---|---|
| `coffee_shop_staff` | The staff floor behind the counter: 8 × 2 from `(1, 3)` | `(5, 4)`, the barista's spot behind the till |
| `coffee_shop_queue` | The lane in front of the till: 1 × 4 from `(5, 6)`, running south | `(5, 6)`, the front of the queue |

The `coffee_shop_counter` interactable's `stand` is the front of the queue, and so is the entry of
`coffee_shop`. Walking to `coffee_shop_queue` takes the front if it's free, and otherwise the next
free tile down the lane.

**The buildings' locations are on two maps for now.** `coffee_shop`, `noodle_bar` and
`maker_space` are on the village, as before, and on their interiors. Movement plans through the
doors, but `movement.town` resolves these three ids to the village, so the game still sends
residents there. #169 removes the village copies and adds the terrace as `cafe_terrace` once the
player can go inside. `tests/world/test_interiors.py` checks that these three are the only ids on
two maps.

**The gallery isn't on the village yet.** A new building changes the iso scenery, which is rendered
from the village (`server/simile/art/iso/`), so the building lands in its own task with the
re-render. Until then `gallery.tmj` has its mat but no door, and nothing can reach it. This spot
keeps every mural wall in view of the iso camera, keeps the village connected, and leaves its
farthest places about 55 s apart:

- **Footprint.** 6 × 5 tiles from `(38, 28)`, in place of the garden between Garden Flats and the
  park: `town.building(38, 28, "cream", (".wwww.", ".sDss."), roof="roof_green")`, or the same with
  two roof rows and three storeys. One tile further west hides the `garden_flats` mural.
- **Door.** The shop door at `x = 40`, so the doorstep, the door's outside end, is `(40, 33)`. Its
  inside end is the mat at `(16, 19)`.
- **Location.** `gallery` stays on its interior, with its entry at `(16, 12)`.

## Doors

Each door is an object on both of its maps: on the village at the walkable tile in front of the
building's door, and on the interior at the mat. The object's `name` is the door's id (its
interior's id), its `type` is `door`, and its rectangle is the tile at this end. Its properties say
where it goes:

| Property | |
|---|---|
| `side` | `outside` or `inside`: which end of F2's `Door` this is. |
| `to_map`, `to_x`, `to_y` | The other end. Stepping onto this tile puts you there. |

| Door | Outside, on the village | Inside |
|---|---|---|
| `coffee_shop` | `(31, 11)` | `(10, 13)` |
| `noodle_bar` | `(16, 11)` | `(15, 13)` |
| `maker_space` | `(41, 11)` | `(14, 13)` |

## Interactables

Each interactable is an object. Its `name` is its id, its `type` is its F2 `InteractableKind`
(`counter`, `painting` or `machine`), and its rectangle is its `area`. Its properties are `label`,
the display name, and `stand`, the tiles you use it from as `x,y` pairs separated by spaces, e.g.
`"2,3 3,3"`. Stand tiles are walkable and in front of the thing: the front of the queue for the
counter, the tiles in front of a machine, and the two floor tiles in front of a painting's wall.

| Map | Ids |
|---|---|
| `coffee_shop` | `coffee_shop_counter` (`counter`) |
| `maker_space` | `laser_cutter`, `printer_3d`, `loom`, `sewing_machine` (`machine`) |
| `gallery` | `painting_1` … `painting_13` (`painting`), all labelled "Painting". Each frame is two tiles wide, on the upper row of a wall. |

## Loading it

Server: `simile.world.map.load_map()` returns the village as a `TownMap` with `width`, `height`,
`walkable(x, y)` (false off the map), `blocked[y][x]`, `locations` (F2 `Location`s),
`location(id)`, `murals`, `mural(id)`, `doors` (F2 `Door`s with an end on this map) and
`interactables` (F2 `Interactable`s). A `MuralWall` has the `id`, `x`, `y`, `width`, `face`,
`bottom` and `top` of M1's `Wall`, and `stand`, the F2 `Tile` its painter stands on.
`load_map(path)` reads any of the maps, and `load_maps()` returns them all by id, the village first.
`with_every_location(maps)` is the village carrying every map's locations, as `Movement.town` has
it. [`server/simile/world/README.md`](../../server/simile/world/README.md) covers walking between
maps.

Client: `village` in `client/src/world/assets.ts` is the village's JSON. The client doesn't load the
interiors yet: K5 (#171) does. The player collides with the village's `collision` layer, starts at
the square's entry and finds the news terminals in `locations`, and the iso scene reads the ground
tiles for how high feet stand. The village itself is drawn from the iso renders
([`server/simile/art/iso/README.md`](../../server/simile/art/iso/README.md)), not from these tiles.
