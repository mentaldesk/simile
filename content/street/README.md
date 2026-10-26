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
- `levels/<n>/sewers.tmj`: the sewers, one of a pool of generated levels (below), and
  `levels/preview.png`.
- `floors/<building>_floor_<n>.tmj`: each floor of each building, `0` for the ground floor.
- `markers.png`: the tiny tileset the tile layers use, so Tiled shows them.
- `jump.json`: the player's jump (#331) on each grade of legs and feet (#389, #408), from
  `server/simile/street/jump.py`. The client plays it and the server checks the player's positions
  and paths by it (below).
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
| `pickups` | Objects. One tile per standing cell where something lies to pick up, named by its id. Its type is `salvage`, a place salvage can lie, or `secret`, which holds `money`, or an item: `item` (its id), `item_kind`, `item_name` and `item_weight`, as `Item` has them. `needs` is what reaching it takes, on one scale for every map (`simile.street.jump.NEEDS`): `jump`, the player's own, or a grade of legs or feet, such as `spring_feet`. It's left out where walking and climbing get there. |

The furniture names are `bar_counter`, `bed`, `bench`, `bicycle`, `bin`, `bookshelf`, `bush`,
`cafe_table`, `counter`, `espresso_machine`, `fountain`, `grinder`, `kitchen`, `kitchen_counter`,
`lamp`, `laser_cutter`, `lift`, `loom`, `menu_board`, `news_terminal`, `noodle_counter`,
`noodle_table`, `palm_tree`, `pegboard`, `plant`, `plinth`, `printer_3d`, `rope_bridge`,
`sewing_machine`, `shelf`, `sofa`, `stool`, `stove`, `table`, `tree`, `wardrobe` and `workbench`,
and in the metro `bedroll`, `breaker_box`, `catwalk`, `crates`, `dead_terminal`, `freight_lift`,
`metro_bench`, `metro_steps`, `pipes`, `rubble`, `scrap_stall`, `ticket_machine`, `train_carriage`,
`tunnel_arch` and `turnstile`, with `metro_entrance` beside the stairway down on Banyan Row, and in
the sewers `maintenance_hatch`, `sewer_lamp`, `sewer_outfall`, `sewer_pier`, `sewer_pipe`,
`sewer_vault`, `sewer_walkway` and `sewer_weir`. A table is drawn with a chair either side. A
`rope_bridge` stands on the solid row under it, its deck. A
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
| 55–86 | The `tunnel_arch`, then the service tunnel, dark either side of the maintenance alcove (71–73) with the plug. In the east half a ladder (75) climbs to a pipe ledge (76–78, row 12), and a catwalk (81–82, row 10) goes on up the wall, a jump from it. An alcove (85–86, row 5) is five rows above that catwalk. West of the pipe ledge, a step (73–74, row 10) is a hop up to a gantry (69–72, row 8) that runs west under a roof of `pipes` (58–73, row 4), lit, with a five-cell gap (64–68) before a nook at its end (61–63). |
| 87–109 | The depot: the clinic (88–97), the `freight_lift` down to the sewers (100–101), a `dead_terminal` (104), and the high ledge (106–109, row 12) against the east wall. |

**What later tasks build on.** Each has an id that stays put; `simile.street.metro` names them.

| Task | Hook | Id, and where |
|---|---|---|
| S4 | Dark stretches, in `light` | `metro_vault` (19–57, rows 0–11), `metro_tunnel_west` (58–70, rows 10–19), `metro_tunnel_east` (74–86). The rest is lit: `metro_entrance`, `metro_platform`, `metro_gantry` (58–70, rows 0–9), `metro_maintenance` and `metro_depot`. |
| S4 | The maintenance plug, a `plug` | `metro_plug`, stood at from (72, 15), in the lit alcove between the tunnel's two dark halves. The `breaker_box` there draws it. |
| S6 | Places salvage can lie, in `pickups` | `metro_salvage_1` on the train's roof (38, 12), `_2` (63, 15) and `_3` (68, 15) in the west tunnel, `_4` in the alcove (85, 5), `_5` (83, 15), and `_6` on the high ledge (108, 12). |
| S6 | The scrap trader's stall, and its spot | The location `scrap_stall` (24–28, rows 13–15, entry 28). The spot is `metro_scrap_trader`, `standing` at (26, 15) facing `south`, at the `scrap_stall` piece. |
| S7 | The clinic, and the doctor's stall spot | `clinic`, an `amenity` on `clinic_floor_0` (room `clinic`, 10 wide), its door at (89, 15). The doctor's spot is `clinic_doctor`, `standing` at (6, 2) facing `south`. The room is bare for S7 to furnish. |
| S8 | The high ledge, a `machine` | `metro_high_ledge`, its four cells (106–109, row 12). It's three rows above the floor under it (`LEDGE_ROWS`): out of reach of the player's own jump, two rows up (`rise` 2.3 tiles), and of the legs' on any grade, and in reach of the spring feet's, four rows up (`rise` 4.3). Salvage and a secret wait on it. |
| S8 | The dead terminal, a `jack` | `metro_terminal`, stood at from (104, 15). With the datajack, E finds the incident's `lift_log` in it. |
| S8, S9 | The lift down to the sewers, a `jack` | `metro_lift`, stood at from its foot, (100, 15) (`LIFT_FOOT`). The door `metro_to_sewers` goes from there to the sewers' landing, and the client takes it only with the datajack. |
| S9 | Premium legs' part | `APEX_ACTUATOR` in `simile.street.sewers`, an item of kind `part`, in a secret past the gate in every level of the sewers (below). The clinic fits the premium legs only to someone carrying it. |
| S9 | What a place needs | A pickup's `needs`, on `simile.street.jump.NEEDS`' scale, and `meets(jump, needs)`. `moves(town, cell, jump)` jumps on a grade's `Jump` (`GRADES`), or on legs and feet together (`KITS`), so a test can check each place is in reach only with what it records, as `tests/street/test_metro.py` does. |

**Secrets** are `secret` pickups, each a jump that walking and climbing alone don't reach, and
salvage waits in two of the places only the feet reach:

| Needs | Place | What waits there |
|---|---|---|
| `jump` | The catwalk over the stairwell, a run jump from the landing | `metro_secret_stairwell` (8, 7, 25 money) |
| `jump` | The catwalk in the vault, a jump from the train's roof | `metro_secret_catwalk` (52, 10, 40 money) |
| `spring_feet` | The high ledge, three rows up | `metro_secret_ledge` (106, 12, 60 money) and `metro_salvage_6` |
| `spring_feet_2` | The alcove, five rows above the catwalk up the tunnel wall | `metro_secret_alcove` (86, 5, a `ration_pack`, food, 0.5 kg) and `metro_salvage_4` |
| `bionic_legs` | The gantry's nook, past a five-cell gap under a roof that stops a high jump rising | `metro_secret_gantry` (61, 8, 60 money) |

A place that needs a grade is in reach of whatever rises at least as high and runs at least as
fast: the second grade of feet reaches the first's places, every grade of legs the first's, and
stage 1's grades of legs the places of the grade of the line they jump as. With Space held, a jump
that rises higher than three rows bumps its head on the gantry's roof and falls short, so the legs
and feet together, like the premium legs, cross its gap on a tap.

**Drawing the metro** (`server/simile/papercraft/`): the metro's layers, furniture, the clinic's
front and room paper are painted in #329's revised cartoon, a little dirty. Its catwalks are
furniture over their solid rows, which hides the street's wooden ledge under them, and the train's
roof is its picture's top edge.

## The sewers

`sewers`, the Sewers (S9), is generated: `simile.street.sewers` makes a level from a seed, and
`simile street` writes a pool of eight, level `n` from seed `n`, to `levels/<n>/sewers.tmj`, with
[`levels/preview.png`](levels/preview.png) drawing them one under another. Every level's map is
`sewers`, so links, positions and saves name it the same way. A world plays one level, picked by
its seed (`world_level`, above), and the `snapshot` says which, so the client, which bundles them
all, plays the same one. The pick depends on how many levels there are, so adding or removing one
moves some worlds, today's village (level 1) among them; `test_sewers.py` fails on a stray folder.
Like the metro it's for the player alone (`JUMPING`) and under the village
(`UNDERGROUND`), and nobody's activity takes them there.

A level is 20 rows like a street, with a vault solid from the top down to row 1, and three tiers
under it: rooms standing on rows 15, 10 and 5 (`FLOORS`), each four rows high, the upper two on a
slab, the row under them. West to east it's columns of rooms:

- **The lift's shaft** (x 0–11, `SHAFT`), S8's landing: the `freight_lift` at (2, row 15), `LANDING`,
  where the door from the metro's lift arrives, lit (`sewers_landing`). A position saved there
  before S9 is still somewhere to stand.
- **Two or three columns** of rooms, then **the gate hall**, 17 wide and the full height, then
  **three or four more**. Between columns is a wall cell, a brick pier on each tier it closes and a
  doorway on each it doesn't. One column, on either side of the gate, is a **hall**: two tiers
  high, with a walkway along its top tier through a doorway from the room west of it. The rooms on
  each side of the gate are joined by a random tree of doorways and ladders, then an extra doorway
  in most levels and a drop or two: a hole two cells wide in a slab, down to the room under it. A
  ladder comes up through a hole two cells wide too, with open air on one side of its top rung, so
  a walk along that floor ends at the ladder, as the client's walking does, rather than passing
  over it. Holes are at least two cells apart, and ladders three, so a held key stops at the end
  of each climb. Walking, climbing and the odd hop over a hole get anywhere on that side.
- **The gate** is the way on: at the top tier a walkway from each side with a five-cell gap
  between them (`GAP`), under the vault, which stops a high jump rising, so only the legs cross it,
  or a weir three rows high across the hall's floor, which the feet jump onto (`WEIR`, 12 cells in,
  `WEIR_AT`). The legs get through on their first grade, and so do the feet, which are found past
  it; the player's own legs don't. A fall from the west walkway lands well short of the weir.
- **The hatch** (`HATCH`, `sewers_hatch`) is a `jack` in the room past the gate that the most
  doorways and ladders lead to: the maintenance hatch where Aris's trail goes on (S12's
  `hatch_log`, `simile.story`). Its cell is each level's own, so it's in the map, not in
  `content/story/story.toml`.
- **Plugs**: `sewers_plug_1`, a `Junction box` in the last column before the gate, and in half the
  levels `sewers_plug_2` past it, each in a lit stretch three cells wide. Some rooms have a lamp
  (`sewer_lamp`) and are lit (`sewers_lamp_<n>`). The rest is dark (`sewers_dark`).

**Pickups.** Each names its item. Salvage is `sewers_salvage_<n>`, six on the way, two before the
gate and four past it, from `SALVAGE_ITEMS`, which `simile.economy` prices. In the sewers `needs`
counts from the way through, which every grade of legs or feet takes:

| Needs | Place | What waits there |
|---|---|---|
| | On the floors, the way through | Six of lead pipe, copper coil, brass fitting, pump impeller, float valve, filter mesh and old battery |
| `jump` | A pipe two rows up against a wall, past the gate | `sewers_secret_actuator`, the `APEX_ACTUATOR` |
| `jump` | The same before the gate, in most levels | `sewers_secret_pipe`, 20 to 40 money |
| `spring_feet_2` | A sealed top room over a drop, five rows up from the room under it (`spring_pocket`) | `sewers_secret_spring`, 60 to 90 money, and `sewers_salvage_spring`, a pressure gauge |
| `bionic_legs` | The hall's ledge, past a five-cell gap from its walkway, under the vault and ten rows over the floor | `sewers_secret_sprint`, 50 to 80 money, and `sewers_salvage_sprint`, an Apex control board |

The actuator waits where the legs and the feet both reach. The two pockets keep their stage 1 ids,
and are never on the way to the hatch.

**What every level is checked for** (`problems`, which the generator keeps trying layouts until it
passes, and `tests/street/test_sewers.py` over the committed levels and more seeds): on every
one of `KITS`, any grade of legs or feet or one of each, the player reaches the hatch and the plugs,
and on their own legs they don't; on every one, and on their own legs, they can get back to the
lift from anywhere they can get to; each pickup is in reach on exactly the ones that meet its
`needs`; and every salvage has a price.

**Drawing it** (`server/simile/papercraft/`): in #329's properly grimy cartoon. The layers are the
sewers' own, and every solid cell above the floor has a piece over it: `sewer_vault` the vault,
`sewer_walkway` a slab three cells or longer and `sewer_pipe` a shorter one or a pipe to stand on,
`sewer_pier` a wall on a tier, and `sewer_weir` the gate's weir, down past the floor over the
walkway's edge, which the ground strip leaves out under it. The hatch is a
`maintenance_hatch`, the plugs `breaker_box`es, and `sewer_outfall`, `rubble`, `crates`, `bedroll`
and `pipes` dress the rooms.

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
lands. Under something solid the jump can rise only until the head meets it, and goes no further
along than a jump that high (`Jump.along`). `moves(town, cell, jump)` jumps on another `Jump`
instead, such as one of `KITS`. Residents never jump, so their paths are as they were.

**The player's position.** `simile.street.moves.possible(town, x, y, last)` is the server's check
on a `player_move` (`docs/protocol.md`): somewhere to stand or climb, or mid-step, or in open air
over somewhere to land, either within the farthest jump from somewhere to stand, or lower than
`last`, the last position kept on that map, and within that jump's reach of it along the row.

`jump.json` is the jump both sides share, on the player's own legs, with what each of `KITS`
changes of it under `kits`: each grade of legs or feet on its own, by the bionic, and one of each
together, joined by `+`, e.g. `bionic_legs+spring_feet` (`simile.street.jump.kit_name`). The legs
(`LEGS`) run faster and kick harder, and the feet (`FEET`) rise higher; together the jump rises as
the feet do and runs as the legs do, `kit`'s best of each:

| Fitted | `rise` | `rows` | `run` | `cells` | `reach` | `kick` |
|---|--:|--:|--:|--:|--:|--:|
| Their own | 2.3 | 2 | 5.2 | 4 | 5.5 | 1 |
| `bionic_legs` | 2.3 | 2 | 7.8 | 6 | 7.9 | 2 |
| `bionic_legs_2` | 2.3 | 2 | 10.4 | 8 | 10.2 | 3 |
| `bionic_legs_3` | 2.3 | 2 | 13 | 10 | 12.6 | 4 |
| `spring_feet` | 4.3 | 4 | 5.2 | 5 | 6.9 | 1 |
| `spring_feet_2` | 6.3 | 6 | 5.2 | 6 | 7.9 | 1 |
| `bionic_legs+spring_feet` | 4.3 | 4 | 7.8 | 8 | 9.9 | 2 |
| `bionic_legs_3+spring_feet_2` | 6.3 | 6 | 13 | 16 | 18.7 | 4 |

Stage 1's grades of legs (`STAGE_1`) jump as they did, until P18 retires them: `hydraulic_legs` as
the spring feet, `spring_legs` as their second grade, `sprint_legs` and `blade_legs` as the legs'
first two grades, and `premium_legs` as the legs' second grade with the feet's second. They kick
as the player's own legs do. Every grade jumps under the same gravity, so a higher jump stays up
longer and goes further too.
`rise` is how many tiles the feet rise with Space held, in `rise_seconds`; `run` how many tiles a
second they run, and fly along in a run jump; `fall_gravity` how much stronger gravity is falling or
once Space is let go;
`cut` how much of its speed up a jump keeps when Space is let go early; `coyote_seconds` and
`buffer_seconds` the grace after walking off a ledge and before landing; `foot` and `body` the
player's half-width and height; `kick` how many times harder than their own legs they kick, for
kicking (P9), and left out of comparing jumps; `cells` and `rows` the jump in the neighbour rule;
and `reach` the farthest jump's reach in tiles from the middle of the cell it takes off from: a run jump with
Space held, taking off as late as coyote time allows, at the client's longest step
(`frame_seconds`).

## Loading them

`simile.world.map` reads them alongside today's maps.

- `STREET_DIR` is this folder, and `MAP_DIR`. `load_maps()` returns every street (by file name)
  and then every floor, by map id, and the maps of one generated level, `levels/<level>/`
  (`load_maps(level=n)`, 0 by default). A world plays one level: `world_level()` picks it by the
  cast's seed (`level_of`), 0 for today's village, the running server loads it, and the
  `snapshot` tells the client which (`docs/protocol.md`). `load_maps(ISO_DIR)` still reads today's `content/map/` until
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
