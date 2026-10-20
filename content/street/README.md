# Street

The side-view village (#306): a Tiled map per street, and one per floor of every building with a
way in. They're built by `server/simile/street/` and replace W1's `content/map/` at the cut-over
(#314). Until then nothing loads them by default: `load_maps(STREET_DIR)` reads them.

Don't edit them by hand or save them from Tiled: change the builder and run

```bash
cd server && uv run simile street
```

Output is deterministic, and `tests/street` fails if a file drifts from the builder.

- `<street>.tmj`: the four streets.
- `floors/<building>_floor_<n>.tmj`: each floor of each building, `0` for the ground floor.
- `markers.png`: the tiny tileset the tile layers use, so Tiled shows them.
- [`preview.png`](preview.png): every street with its buildings' floors drawn in place. Ground is
  brown, walls and floors grey, cells you can stand on cream, stairs yellow, ladders orange. Green
  squares are doors, yellow and orange lines stairs and ladders between floors, pink lines the
  lift. Violet dots are spots, with a tick the way they face (up for `north`, down for `south`).
  Yellow squares are entries, teal boxes locations, orange boxes things to use, cyan boxes mural
  walls from `bottom` to `top`, and thin grey boxes furniture.

## The grid

A map is a hidden grid, as today's are, read the other way up: **x runs along the street and y
counts rows down from the top.** A tile is about 1.1 m, as today, so every distance in tiles keeps
its meaning.

- **A standing cell** is open, with something solid under it. Residents stop on these.
- **A climbable cell** is a cell of a run of stairs or a ladder. A run joins a standing cell at its
  bottom to one at its top, and a resident can stop anywhere on it. Nothing solid is directly
  under a climbable cell.
- **Walkable** cells are the standing and climbable ones: `TownMap.walkable` keeps meaning "someone
  can be here". Everything else is solid, or open air with nothing under it.
- A floor map is four rows: three of room (the standing row is `2`) over a row of floor, with a
  wall at each end. Its floors stack in place: floor `n`'s top-left cell is at the street cell
  `(street_x, street_y)`, and its standing row is four rows above floor `n - 1`'s. The ground floor's
  standing row is level with the street's.
- A street is 20 rows, standing on row `15` with the ground below. Banyan Row drops to row `18` at
  the river.

## Layers

Every map has every layer, bottom to top:

| Layer | |
|---|---|
| `solid` | Tiles. The `solid` marker on ground, floors, walls and ledges. Nothing reads it yet: it keeps open air known for when jumping comes. |
| `climbable` | Tiles. The `stairs` or `ladder` marker on each climbable cell. Its kind is the marker tile's `name` property, a `DoorKind`. |
| `collision` | Tiles, hidden. The `blocked` marker on every cell that isn't walkable. |
| `buildings` | Objects, on streets. One rectangle per building front, named by its building: a location id, or `corner_shop`, `tower` or `garden_flats` for the three with no way in. It covers the building's storeys down to the street's standing row. Properties: `label`, `storeys`, and `interior`, whether it has floor maps. |
| `furniture` | Objects. One rectangle per piece of furniture or street prop, where it's drawn. Its `name` and `type` are what it's painted as (below). Nothing walks round furniture: residents pass in front of it. |
| `locations` | Objects, as today. A building's location is on its ground floor (below). |
| `murals` | Objects, on streets only (below). |
| `doors` | Objects. One tile per link with an end on this map (below). |
| `interactables` | Objects, as today, on floors. |
| `spots` | Objects, as today. |

The furniture names are `bar_counter`, `bed`, `bench`, `bookshelf`, `bush`, `cafe_table`,
`counter`, `espresso_machine`, `fountain`, `grinder`, `kitchen`, `kitchen_counter`, `lamp`,
`laser_cutter`, `lift`, `loom`, `menu_board`, `news_terminal`, `noodle_counter`, `noodle_table`,
`pegboard`, `plant`, `plinth`, `printer_3d`, `sewing_machine`, `shelf`, `sofa`, `stool`, `stove`,
`table`, `tree`, `wardrobe` and `workbench`. A table is drawn with a chair either side.

## Map properties

| Property | | |
|---|---|---|
| `view` | Every map | `side`. Today's maps have no properties. |
| `kind` | Every map | `street` or `floor`. |
| `label` | Streets | Its name, e.g. `High Street`. |
| `building` | Floors | Its building's location id. |
| `floor` | Floors | Its number, `0` for the ground floor. |
| `room` | Floors | What the room is, for its papers: `living_room`, `bedroom`, `cafe`, `cafe_upstairs`, `flat`, `noodle_bar`, `dining_room`, `workshop`, `loft` or `gallery`. |
| `street`, `street_x`, `street_y` | Floors | The street its building stands on, and the street cell under the floor map's top-left cell, so its dollhouse is drawn in place. |

## Objects

As in [`content/map/`](../map/README.md), with these additions.

- **Locations.** A location object's optional `floors` property lists its building's other
  floors as `map:x,y,width,height` separated by spaces, e.g.
  `coffee_shop_floor_1:1,0,18,3 coffee_shop_floor_2:1,0,18,3`. A building is one `Location`. Its
  `map`, `area` and `entry` are on the ground floor, where its front door arrives, and its area
  on each floor is the room, `(1, 0)` to the wall at the other end.
- **Links.** Each door object has a `kind` property: `door`, `stairs`, `ladder` or `lift`. `side`
  and `to_*` are as today. No two links share an end tile, so a lift serving three floors has a
  separate end on each floor for each floor it goes to.
  - A **front door** joins the street (`outside`, the cell in front of it) and the ground floor
    (`inside`, at the same x within the building). Its id is the building's location id.
  - A **street door** joins two streets, `outside` on the one whose id comes first. Its id is
    `<outside>_to_<inside>`. It's a lane or steps between buildings, at a street's end or partway
    along it, so the square can be the middle of the village.
  - **Stairs, a ladder or a lift** join two floors of a building, `outside` the lower.
- **Mural walls** face `south`, the camera. A wall's `x`, `y` is the standing cell at its west end
  on the street in front, and its rectangle is the `width` cells along the street from there. Its
  painter's `stand` is the cell in front of its middle. `bottom` and `top` are in storeys above the
  street, as today, and keep today's values.
- **Spots** face `north` at terminals, desks, the bar, paintings and murals (their backs to the
  camera), `east` or `west` at tables, facing each other, and `south` on the street's benches
  (their fronts to the camera). The gallery's benches and the noodle bar's stools face `north`.
  `dx` and `dy` are always 0. The stools keep `dz` 0.25.

## The village

Four streets. Kapok Walk and Lychee Lane lead off the west end of the square on the High Street,
and steps go down to Banyan Row off its east end. The farthest two places are about 70 s' walk
apart, against today's 47 s.

| Street | Width | West to east (x) |
|---|--:|---|
| `high_street` High Street | 84 | `maker_space` (2–17), `corner_shop` (19–24, a mural), `coffee_shop` (25–44, a mural) with `cafe_terrace` in front, `square` (45–64) with `terminal_1` at 59 and the doors to Kapok Walk (45), Lychee Lane (46) and Banyan Row (63), `noodle_bar` (65–81) |
| `lychee_lane` Lychee Lane | 68 | `house_1` (2–8), `house_2` (9–15), the door to the High Street (17), `house_3` (19–25), `house_4` (26–32), `terminal_2` at the park gate (34), `park` (36–59) with a lookout up a ladder at 45, `tower` (61–66, a mural) |
| `kapok_walk` Kapok Walk | 34 | a garden (1–8), `house_5` (9–15), `house_6` (16–22), `house_7` (23–29), the door to the High Street (32) |
| `banyan_row` Banyan Row | 68 | `house_8` (2–8), `house_9` (9–15), `house_10` (16–22, a mural), the door to the High Street (24), `gallery` (26–43), `garden_flats` (45–50, a mural), then two stairs down from 53 to the river's promenade, row 18, with `terminal_3` at 60 |

| Building | Street | Width | Floors | Links between floors |
|---|---|--:|---|---|
| `house_1` … `house_10` | as above | 7 | 0 `living_room`, 1 `bedroom` | `house_<n>_stairs`, 0 → 1 |
| `coffee_shop` The Daily Grind | `high_street` | 20 | 0 `cafe`, 1 `cafe_upstairs`, 2 `flat` | `coffee_shop_stairs` 0 → 1, `coffee_shop_flat_stairs` 1 → 2 |
| `noodle_bar` Golden Bowl Noodles | `high_street` | 17 | 0 `noodle_bar`, 1 `dining_room` | `noodle_bar_stairs` 0 → 1 |
| `maker_space` Spark Maker Space | `high_street` | 16 | 0 and 1 `workshop`, 2 `loft` | `maker_space_stairs` 0 → 1, `maker_space_ladder` 1 → 2 |
| `gallery` The Gallery | `banyan_row` | 18 | 0, 1 and 2 `gallery` | `gallery_lift_0_1`, `gallery_lift_0_2`, `gallery_lift_1_2` |

- **Houses** have the front door and the foot of the stairs at opposite ends of the living room,
  and the entry in the middle, at x 3. Houses 2, 4, 6, 9 and 10 have their door at the west end.
- **The Daily Grind**, ground floor, west to east: behind the counter the grinder (1), the espresso
  machine (2), the till (3, `coffee_shop_staff`'s entry) and the hand-over (4); then on the
  customers' side the pickup (5), the queue from its front (6, the café's entry and the counter's
  stand) running east to 9 (`coffee_shop_queue`), the standing bar (10–14), the foot of the stairs
  (15), just inside the door (17) and the mat (18). Its eight tables are upstairs. The barista's
  flat is the top floor.
- **Golden Bowl Noodles**: the foot of the stairs (1), the mat (2), two tables, the entry (7), the
  five stools at the counter (8–12) and the kitchen behind it (13–15). Seven tables upstairs.
- **Spark Maker Space**: the foot of the stairs (1), a workbench, the laser cutter, 3D printer, loom
  and sewing machine (6–11), the entry (13) and the mat (14). Three workbenches on the first floor,
  two in the loft up the ladder from x 6.
- **The Gallery**: the mat (2), the entry (3), paintings 1 to 3 and a bench on the ground floor,
  4 to 8 and two benches on the first, 9 to 13 and a bench on the second. The lift is at the east
  end: on each floor, x 15 and 16 go to the other two floors.

## Ids

Every location, door, spot, interactable and mural wall id in `content/map/` is here, and no map id
is one of today's (`village`, `coffee_shop`, `gallery`, `maker_space`, `noodle_bar`), so a saved
position's map says which world it's from.

| Today | Here |
|---|---|
| A location on `village` | The same id on a street. The houses are on their ground floors. |
| A location on an interior | The same id on its building's ground floor. |
| A door | The same id, from the street to the building's ground floor. The houses have new doors, `house_1` … `house_10`. |
| An interactable | The same id, on a floor of its building. |
| A mural wall | The same id, on a street. |
| A spot on `village` | The same id on a street, near the same things. |
| A spot on an interior | The same id on a floor of the same building. |

Spot ids keep today's names (`seat-27-19`), though they no longer match their cells. They're unique
on each map, and within each building across its floors, as today's were on each map:
`seat-3-8` is both a café seat and a noodle-bar seat. Every spot is in the locations it was in.

## Moving

`simile.street.moves.moves(town, cell)` is the side-view neighbour rule, and
`simile.world.paths.steps` uses it on side-view maps, so `find_route`, `nearby` and `Movement`
follow it:

- left and right between walkable cells on one row, a step (cost 1)
- up and down only along a climbable run: straight on a ladder (cost 1 a rung), and diagonally on
  stairs (cost √2 a stair), along the flight to the cells at its ends
- no other diagonals, and never into open air

A ladder is climbed from the standing cell under it and stepped off sideways at the top, onto the
ledge beside its top rung. Stairs run between the standing cells diagonally beyond each end. A
resident can stop on any cell of a run. A move comes with its cost, so a jump of a set reach can
join the rule later.

## Loading them

`simile.world.map` reads them alongside today's maps.

- `STREET_DIR` is this folder. `load_maps(STREET_DIR)` returns every street (by file name) and
  then every floor, by map id. `load_maps()` still reads `content/map/`, exactly as before.
- `TownMap` has, after its old fields, `side_view`, `kind` (`MapKind.STREET` or `FLOOR`, `None` on
  today's maps), `building` and `floor` (on floors), and `climbable`, rows of `DoorKind` or `None`
  (empty on today's maps). `climb(x, y)` is the climbable kind on a cell and `standing(x, y)`
  whether it's a standing cell.
- `with_every_location(maps)` carries every map's locations, doors and mural walls. Without a
  village it's on the first street, `banyan_row`.
- `movement.inside(location, where)` counts a location's floors, and a walk to a location looks for
  a free spot on every floor it covers, measuring the floors as stacked one above the other.

The loader rejects maps that break `docs/protocol.md`'s rules, with a `ValueError`:

- two links that share an end tile, on one map (`load_map`) or across them (`load_maps`)
- a link that isn't the same from both ends, leads to a missing map, or ends off a standing cell
- a street door whose `outside` isn't the street whose id comes first
- a door that doesn't join two streets or a street and a ground floor
- stairs, a ladder or a lift that doesn't join a floor to a higher one of the same building
- a floor its building's location doesn't list, or a listed floor that isn't its building's
