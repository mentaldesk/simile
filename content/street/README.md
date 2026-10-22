# Street

The side-view village (#306): a Tiled map per street, and one per floor of every building with a
way in. They're built by `server/simile/street/` and, since the cut-over (#314), are the maps the
game runs on: `load_maps()` reads them.

Don't edit them by hand or save them from Tiled: change the builder and run

```bash
cd server && uv run simile street
```

Output is deterministic, and `tests/street` fails if a file drifts from the builder.

- `<street>.tmj`: the five streets, and the metro under them.
- `floors/<building>_floor_<n>.tmj`: each floor of each building, `0` for the ground floor.
- `markers.png`: the tiny tileset the tile layers use, so Tiled shows them.
- `jump.json`: the player's jump (#331), from `server/simile/street/jump.py`. The client plays it
  and the server checks the player's positions and paths by it (below).
- [`preview.png`](preview.png): every street with its buildings' floors drawn in place. Ground is
  brown, walls and floors grey, cells you can stand on cream, stairs yellow, ladders orange. Green
  squares are doors, yellow and orange lines stairs and ladders between floors, pink lines the
  lift. Violet dots are spots, with a tick the way they face (up for `north`, down for `south`).
  Yellow squares are entries, teal boxes locations, orange boxes things to use, cyan boxes mural
  walls from `bottom` to `top`, and thin grey boxes furniture. Dark stretches are shaded navy,
  places salvage can lie are green diamonds and secrets pink ones. Mural walls and doors to other
  streets are named in the ground under them.

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
| `solid` | Tiles. The `solid` marker on ground, floors, walls, ledges, flat roofs and bridges: what a jump lands on and bumps into. `TownMap.solid(x, y)` reads it. |
| `climbable` | Tiles. The `stairs` or `ladder` marker on each climbable cell. Its kind is the marker tile's `name` property, a `DoorKind`. |
| `collision` | Tiles, hidden. The `blocked` marker on every cell that isn't walkable. |
| `buildings` | Objects, on streets. One rectangle per building front, named by its building: a location id, or `corner_shop`, `tower` or `garden_flats` for the three with no way in. It covers the building's storeys down to the street's standing row. Properties: `label`, `storeys`, and `interior`, whether it has floor maps. |
| `furniture` | Objects. One rectangle per piece of furniture or street prop, where it's drawn. Its `name` and `type` are what it's painted as (below). Nothing walks round furniture: residents pass in front of it. |
| `locations` | Objects, as today. A building's location is on its ground floor (below). |
| `murals` | Objects, on streets only (below). |
| `doors` | Objects. One tile per link with an end on this map (below). |
| `interactables` | Objects, as today, on floors, and the metro's on its street. A `plug` charges the player's lamp while they stand on its stand tile (below). |
| `spots` | Objects, as today. |
| `light` | Objects. Rectangles, each a stretch of the map that's lit or dark, named by its id, with a `lit` property. A cell is dark where a dark stretch covers it and no lit one does, and lit everywhere else, so a map without any is lit all over. Only the metro has any yet, and every cell of it is in one. |
| `pickups` | Objects. One tile per standing cell where something lies to pick up, named by its id. Its type is `salvage`, a place salvage can lie, or `secret`, which holds `money`, or an item: `item` (its id), `item_kind`, `item_name` and `item_weight`, as `Item` has them. |

The furniture names are `bar_counter`, `bed`, `bench`, `bicycle`, `bin`, `bookshelf`, `bush`,
`cafe_table`, `counter`, `espresso_machine`, `fountain`, `grinder`, `kitchen`, `kitchen_counter`,
`lamp`, `laser_cutter`, `lift`, `loom`, `menu_board`, `news_terminal`, `noodle_counter`,
`noodle_table`, `palm_tree`, `pegboard`, `plant`, `plinth`, `printer_3d`, `rope_bridge`,
`sewing_machine`, `shelf`, `sofa`, `stool`, `stove`, `table`, `tree`, `wardrobe` and `workbench`,
and in the metro `bedroll`, `breaker_box`, `catwalk`, `crates`, `dead_terminal`, `freight_lift`,
`metro_bench`, `metro_steps`, `pipes`, `rubble`, `scrap_stall`, `ticket_machine`, `train_carriage`,
`tunnel_arch` and `turnstile`, with `metro_entrance` beside the stairway down on Banyan Row. A table
is drawn with a chair either side. A `rope_bridge` stands on the solid row under it, its deck. A
`catwalk` covers its solid row and the row above it, its deck on the solid row's top, and the
`train_carriage` its roof's solid row and everything under it. `metro_steps` covers a flight of stairs
and the cells at its ends, over the street's own steps.

## Map properties

| Property | | |
|---|---|---|
| `view` | Every map | `side`. Today's maps have no properties. |
| `kind` | Every map | `street` or `floor`. |
| `label` | Streets | Its name, e.g. `High Street`. |
| `building` | Floors | Its building's location id. |
| `floor` | Floors | Its number, `0` for the ground floor. |
| `room` | Floors | What the room is, for its papers: `living_room`, `bedroom`, `cafe`, `cafe_upstairs`, `flat`, `noodle_bar`, `dining_room`, `workshop`, `loft`, `gallery` or `clinic`. |
| `street`, `street_x`, `street_y` | Floors | The street its building stands on, and the street cell under the floor map's top-left cell, so its dollhouse is drawn in place. |
| `underground` | Streets under the village (`UNDERGROUND`) | `true`. Lit by its own lights, never the sky, so the time of day doesn't tint it. Left out elsewhere. |

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
  - **Stairs or a ladder** join a floor of a building to the one above it, and **a lift** any
    two of its floors, `outside` the lower.
  - Link ends on a street are at least 3 tiles apart, so no two openings are drawn side by side.
- **Mural walls** face `south`, the camera. A wall's `x`, `y` is the standing cell at its west end
  on the street in front, and its rectangle is the `width` cells along the street from there. Its
  painter's `stand` is the cell in front of its middle. `bottom` and `top` are in storeys above the
  street, as today, and keep today's values.
- **Spots** face `north` at terminals, desks, paintings and murals (their backs to the camera).
  Every seat faces `east` or `west`, as the side view draws a sitter: at tables, facing each
  other; on a counter's stools, the way it's served from (the Daily Grind's bar west to its
  counter, the noodle bar's east to its kitchen); and on a bench, at what its sitters look at (the
  square's at the fountain, the park's at the lookout, and in the gallery each at the nearest
  painting, so two can sit back to back). `dx` and `dy` are always 0. The stools keep `dz` 0.25.

## The village

Five streets. Kapok Walk and Lychee Lane lead off the square on the High Street, and steps go
down to Banyan Row off its east end. The Rooftops are behind Kapok Walk, through a lane at its
west end. The farthest two places are about 70 s' walk apart, against today's 47 s.

| Street | Width | West to east (x) |
|---|--:|---|
| `high_street` High Street | 84 | `maker_space` (2–17), `corner_shop` (19–24, a mural), `coffee_shop` (25–44, a mural) with `cafe_terrace` in front, `square` (45–64) with the fountain at 55–56, `terminal_1` at 60 and the doors to Kapok Walk (46), Lychee Lane (50) and Banyan Row (64), `noodle_bar` (65–81) |
| `lychee_lane` Lychee Lane | 68 | `house_1` (2–8), `house_2` (9–15), the door to the High Street (17), `house_3` (19–25), `house_4` (26–32), `terminal_2` at the park gate (34), `park` (36–59) with a lookout up a ladder at 45, `tower` (61–66, a mural) |
| `kapok_walk` Kapok Walk | 34 | a garden (1–8) with the lane to the Rooftops (2), `house_5` (9–15), `house_6` (16–22), `house_7` (23–29), the door to the High Street (32) |
| `banyan_row` Banyan Row | 68 | `house_8` (2–8), `house_9` (9–15), `house_10` (16–22, a mural), the door to the High Street (24), `gallery` (26–43), `garden_flats` (45–50, a mural), then two stairs down from 53 to the river's promenade, row 18, with `terminal_3` at 60 and the stairway down to the metro at 62 |
| `rooftops` The Rooftops | 60 | The door to Kapok Walk (1) on a back lane, a ladder (3) up onto the `bakery`'s roof (4–9, row 12), a gap, walkways up the alley (11–14, rows 12 and 10), the roofs of the `print_works` (15–21), the `tea_house` (24–30) and the `laundry` (34–39), all row 8, with gaps of two and three cells between them, a `palm_tree` in the second, a `rope_bridge` (40–47) to a balcony (48–49), and a ladder (49) up to the `clock_house`'s roof (50–56, row 4) |

| Building | Street | Width | Floors | Links between floors |
|---|---|--:|---|---|
| `house_1` … `house_10` | as above | 7 | 0 `living_room`, 1 `bedroom` | `house_<n>_stairs`, 0 → 1 |
| `coffee_shop` The Daily Grind | `high_street` | 20 | 0 `cafe`, 1 `cafe_upstairs`, 2 `flat` | `coffee_shop_stairs` 0 → 1, `coffee_shop_flat_stairs` 1 → 2 |
| `noodle_bar` Golden Bowl Noodles | `high_street` | 17 | 0 `noodle_bar`, 1 `dining_room` | `noodle_bar_stairs` 0 → 1 |
| `maker_space` Spark Maker Space | `high_street` | 16 | 0 and 1 `workshop`, 2 `loft` | `maker_space_stairs` 0 → 1, `maker_space_ladder` 1 → 2 |
| `gallery` The Gallery | `banyan_row` | 18 | 0, 1 and 2 `gallery` | `gallery_lift_0_1`, `gallery_lift_0_2`, `gallery_lift_1_2` |

- **No flight or ladder starts against an outer wall** (#325): there's a cell to stand on behind the
  foot of each flight, away from the flight, and either side of a ladder's. A flight's top can land
  against the far wall.
- **Houses** have the front door at one end of the living room and the foot of the stairs a step in
  from the other (x 2, or 4 where the door is west), rising to the bedroom over the door, and the
  entry in the middle, at x 3. Houses 2, 4, 6, 9 and 10 have their door at the west end.
- **The Daily Grind**, ground floor, west to east: behind the counter the grinder (1), the espresso
  machine (2), the till (3, `coffee_shop_staff`'s entry) and the hand-over (4); then on the
  customers' side the pickup (5), the queue from its front (6, the café's entry and the counter's
  stand) running east to 9 (`coffee_shop_queue`), the bar and its five stools (10–14), the foot of
  the stairs (15), rising east to 18 upstairs, just inside the door (17) and the mat (18). Its
  eight tables are upstairs, with the foot of the flat's stairs between them (11), rising east to
  14. The barista's flat is the top floor. A plug, `coffee_shop_plug`, is on the wall at 16.
- **Golden Bowl Noodles**: the entry (1), the mat (2), the foot of the stairs (3), rising east to 7
  upstairs, two tables, the five stools at the counter (8–12) and the kitchen behind it (13–15).
  Seven tables upstairs. A plug, `noodle_bar_plug`, is on the wall by the entry.
- **Spark Maker Space**: the foot of the stairs (2), a workbench, the laser cutter, 3D printer, loom
  and sewing machine (7–12), the entry (13) and the mat (14). Three workbenches on the first floor,
  two in the loft up the ladder from x 6. A plug, `maker_space_plug`, is on the wall at the entry,
  where the player wakes after collapsing (`simile.player`), since it's their home.
- **The Gallery**: the mat (2), the entry (3), paintings 1 to 3 and a bench on the ground floor,
  4 to 8 and two benches on the first, 9 to 13 and a bench on the second. The lift is at the east
  end: on each floor, x 15 and 16 go to the other two floors.
- **The Rooftops** are for jumping, so only the player gets all over them (`JUMPING` in
  `simile.street.village`). Its five buildings have no way in, and a flat roof along their top row
  to stand on. It has no locations or spots, so no resident has anywhere to go there, and its only
  door leads back to Kapok Walk, so no resident's way anywhere else passes through it. A fall
  anywhere lands in the lane, which runs under everything back to the door and the first
  ladder.

## The metro

`metro`, the Old Metro (#350), is an abandoned station under the village, 110 wide. Its stairway
down is a door like any other, `banyan_row_to_metro`, from Banyan Row's river promenade (62, row
18) to a landing at the top of the stairs (2, row 9). Like the Rooftops it's for the player alone
(`JUMPING`), and it's in `UNDERGROUND`, the streets under the village. Its locations, the clinic
and the scrap trader's stall (`scrap_stall`), are `amenity`s no resident's activity names, and its
only doors are the stairway and the clinic's, so no resident has anywhere to go there and no route
passes through it.

| x | |
|---|---|
| 0–19 | The landing (row 9), a flight down to the ticket hall (row 12) with the `turnstile` and `ticket_machine`, and a flight down to the platform (row 15). A catwalk over the first flight, at row 7, is a run jump from the landing. |
| 20–54 | The platform: the scrap trader's `scrap_stall`, benches, and a dead `train_carriage` (33–42) with a ladder (32) up to its roof, row 12. A catwalk along the vault (45–52, row 10) is a jump from the roof's east end. |
| 55–86 | The `tunnel_arch`, then the service tunnel, dark either side of the maintenance alcove (71–73) with the plug. In the east half a ladder (75) climbs to a pipe ledge (76–78, row 12), and a catwalk (81–82, row 10) and an alcove (85–86, row 8) go on up the wall, each a jump from the last. |
| 87–109 | The depot: the clinic (88–97), the `freight_lift` down to the sewers (100–101), a `dead_terminal` (104), and the high ledge (106–109, row 12) against the east wall. |

**What later tasks build on.** Each has an id that stays put; `simile.street.metro` names them.

| Task | Hook | Id, and where |
|---|---|---|
| S4 | Dark stretches, in `light` | `metro_vault` (19–57, rows 0–11), `metro_tunnel_west` (58–70), `metro_tunnel_east` (74–86). The rest is lit: `metro_entrance`, `metro_platform`, `metro_maintenance` and `metro_depot`. |
| S4 | The maintenance plug, a `plug` | `metro_plug`, stood at from (72, 15), in the lit alcove between the tunnel's two dark halves. The `breaker_box` there draws it. |
| S6 | Places salvage can lie, in `pickups` | `metro_salvage_1` on the train's roof (38, 12), `_2` (63, 15) and `_3` (68, 15) in the west tunnel, `_4` on the pipe ledge (77, 12), `_5` (83, 15), and `_6` on the high ledge (108, 12). |
| S6 | The scrap trader's stall, and its spot | The location `scrap_stall` (24–28, rows 13–15, entry 28). The spot is `metro_scrap_trader`, `standing` at (26, 15) facing `south`, at the `scrap_stall` piece. |
| S7 | The clinic, and the doctor's stall spot | `clinic`, an `amenity` on `clinic_floor_0` (room `clinic`, 10 wide), its door at (89, 15). The doctor's spot is `clinic_doctor`, `standing` at (6, 2) facing `south`. The room is bare for S7 to furnish. |
| S8 | The high ledge, a `machine` | `metro_high_ledge`, its four cells (106–109, row 12). It's three rows above the floor under it (`LEGS_ROWS`): out of reach of today's jump, two rows up (`rise` 2.3 tiles), and in reach of the legs if they jump three. Salvage waits on it. |
| S8 | The dead terminal, a `machine` | `metro_terminal`, stood at from (104, 15). |
| S8, S9 | The lift down to the sewers, a `machine` | `metro_lift`, stood at from (100, 15) and (101, 15). Its foot on the metro, where a link to the sewers would end, is (100, 15) (`LIFT_FOOT`). No link leads from it yet. |

**Secrets** are `secret` pickups, each a jump that walking and climbing alone don't reach:
`metro_secret_stairwell` (8, 7, 25 money), `metro_secret_catwalk` (52, 10, 40 money) and
`metro_secret_alcove` (86, 8, a `ration_pack`, food, 0.5 kg).

**Drawing it** (`server/simile/papercraft/`): the metro's layers, furniture, the clinic's front and
room paper are painted in #329's revised cartoon, a little dirty. Its catwalks are furniture over
their solid rows, which hides the street's wooden ledge under them, and the train's roof is its
picture's top edge.

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
resident can stop on any cell of a run. A move comes with its cost.

**Jumps are the player's alone.** `moves(town, cell, jumps=True)`, and `jumps=True` on
`simile.world.paths`' `steps`, `nearby` and `find_route`, add a run jump from a standing cell to
another up to `cells` (4) along the row and `rows` (2) up, or down any way, through open air: up
from where it takes off, along over the higher end with room for the head, and down onto where it
lands. Residents never jump, so their paths are as they were.

**The player's position.** `simile.street.moves.possible(town, x, y, last)` is the server's check
on a `player_move` (`docs/protocol.md`): somewhere to stand or climb, or mid-step, or in open air
over somewhere to land, either within the farthest jump from somewhere to stand, or lower than
`last`, the last position kept on that map, and within that jump's reach of it along the row.

`jump.json` is the jump both sides share. `rise` is how many tiles the feet rise with Space held,
in `rise_seconds`; `fall_gravity` how much stronger gravity is falling or once Space is let go;
`cut` how much of its speed up a jump keeps when Space is let go early; `coyote_seconds` and
`buffer_seconds` the grace after walking off a ledge and before landing; `foot` and `body` the
player's half-width and height; `cells` and `rows` the jump in the neighbour rule; and `reach` the
farthest jump's reach in tiles from the middle of the cell it takes off from: a run jump with
Space held, taking off as late as coyote time allows, at the client's longest step
(`frame_seconds`).

## Loading them

`simile.world.map` reads them alongside today's maps.

- `STREET_DIR` is this folder, and `MAP_DIR`. `load_maps()` returns every street (by file name)
  and then every floor, by map id. `load_maps(ISO_DIR)` still reads today's `content/map/` until
  #315.
- `TownMap` has, after its old fields, `side_view`, `kind` (`MapKind.STREET` or `FLOOR`, `None` on
  today's maps), `building` and `floor` (on floors), `climbable`, rows of `DoorKind` or `None`
  (empty on today's maps), and `solids`, rows of the `solid` layer (empty without one).
  `climb(x, y)` is the climbable kind on a cell, `standing(x, y)` whether it's a standing cell, and
  `solid(x, y)` whether it's solid: off the map always, and on a map without the layer anywhere
  nobody can walk. `light` is its `light` layer, each a `Light` (`id`, `area`, `lit`), and
  `lit(x, y)` whether a cell is lit, by the rule above.
- `with_every_location(maps)` carries every map's locations, doors and mural walls. Without a
  village it's on the first street, `banyan_row`.
- `movement.inside(location, where)` counts a location's floors, and a walk to a location looks for
  a free spot on every floor it covers, measuring the floors as stacked one above the other.

The loader rejects maps that break `docs/protocol.md`'s rules, with a `ValueError`:

- two links that share an end tile, on one map (`load_map`) or across them (`load_maps`)
- a link that isn't the same from both ends, leads to a missing map, or ends off a standing cell
- a street door whose `outside` isn't the street whose id comes first
- a door that doesn't join two streets or a street and a ground floor
- stairs, a ladder or a lift that doesn't join a floor to a higher one of the same building, or
  stairs or a ladder that skip a floor
- a floor its building's location doesn't list, or a listed floor that isn't its building's
