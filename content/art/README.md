# Art

Everything here except this README is drawn by `server/simile/art/`. Don't edit the images by
hand: change the generator and run

```bash
cd server && uv run simile art         # tileset, player, sample characters, previews, NPC sprites
cd server && uv run simile art --npcs  # only the sprites for content/npcs/*.json
```

Output is deterministic. `tests/art` fails if the tileset, `tiles.md`, the `player` and `sample_*`
sprites or the previews drift from the generator. It ignores NPC sprites and `preview/npcs.png`.

## Palette

32 colours, defined once in `server/simile/art/palette.py`. Every opaque pixel in every PNG here
is one of them. Characters' `#rrggbb` colours snap to the closest palette colour (in Lab space);
skin snaps to one of six skin tones.

## Tileset: `tiles.png`, `tiles.tsj`

The game doesn't draw these tiles: they're what the village is built from. W1's builder lays the map
out with them (`server/simile/world/build_map.py`) and draws its previews from them, and the iso
scenery build reads each map cell's tile by name to model the village
([`server/simile/art/iso/README.md`](../../server/simile/art/iso/README.md)).

- 16×16 px tiles, 16 columns, no margin or spacing.
- `tiles.tsj` is a Tiled JSON tileset named `simile`. Every tile has three properties:
  - `name`: a stable name. Code should look tiles up by name, not id.
  - `collides`: blocks walking (water, buildings, most props).
  - `above`: goes on the map's `above` layer (tree crowns and the tops of lamps, palms, terminals
    and vending machines).
- [`tiles.md`](tiles.md) lists every id and name. Ids are positions in `tiles.png`. Each group
  starts a new row, so add new tiles in a group's free slots or as a new group at the end, or
  existing maps break.
- [`preview/tiles.png`](preview/tiles.png) shows every tile with its id.

Suggested map layers: ground (terrain), buildings (roofs and facades), decor (everything with a
transparent background: props, signs, awnings), then above (`above` tiles).
`blocked`, a red cross, is for a hidden collision layer and is never drawn in the game.

**Terrain.** Grass, road and water patches sit inside pavement. Each patch is at least two tiles
thick, and patches are at least one pavement tile apart.
A patch's border tiles are named by the sides that touch pavement: `grass_n` has pavement to the
north, `grass_ne` is the patch's north-east corner, and `grass_ne_nook` has pavement only on its
north-east diagonal (a concave corner). `simile.art.tiles.edge_variant(terrain, same)` picks the
name from the neighbours, and the tileset's corner wangsets (`grass`, `road`, `water`) let Tiled's
terrain brush paint them. `road_line_h/v` and `crosswalk_h/v` (for a horizontal or vertical road)
go inside roads; `tactile_h/v` and `plaza*` sit on pavement.

**Buildings** are a flat roof over a facade, viewed from the south:

- Roof: a 9-slice, `roof_nw roof_n roof_ne / roof_w roof roof_e / roof_sw roof_s roof_se`, at least
  two rows tall. The south row includes the parapet's front face. `roof_green_*` is the same with a
  green roof. `roof_solar`, `roof_ac` and `roof_skylight` replace middle tiles.
- Facade, for material `cream` or `slate`: any number of upper rows from `wall_<m>_l`, `wall_<m>`,
  `wall_<m>_r`, `window_<m>` and `door_<m>_top`, then one ground-floor row from `base_<m>_l`,
  `base_<m>`, `base_<m>_r`, `base_window_<m>` and `door_<m>` (under `door_<m>_top`).
- Shop ground floor: `shopfront_l`, `shopfront`, `shopfront_r`, `shop_door`, with `awning_red_*`
  or `awning_blue_*` (`_l`, middle, `_r`) on the decor layer over the same row.
- Coffee shop: `cafe_wall_l`, `cafe_wall`, `cafe_wall_r` and the two-tile `cafe_sign_l/r` above
  `cafe_window_l`, `cafe_window`, `cafe_window_r` and `cafe_door`, with `cafe_awning_*` over the
  windows, and `cafe_table` and `cafe_menu` outside.
- Facades and doors collide; the pavement tile in front of a door is the way in.
- Wall decor: `neon_*` signs (`neon_vertical_top/bottom` is two tiles tall), the two-tile street
  screen `screen_l/r` and `ac_unit`.

**Multi-tile props:** `tree_tl tree_tr / tree_bl tree_br`, `fountain_*` in the same layout,
`bench_l bench_r`, and `<name>_top` above `<name>` for `terminal` (the news terminal), `lamp`,
`palm` and `vending`.

## Characters: `characters/<id>.png`, `characters/<id>.json`

- 16×24 px frames in a 3 × 8 grid (48×192 px). Rows: `down`, `left`, `right`, `up`, then the
  three-quarter views `down_left`, `down_right`, `up_left`, `up_right`, each facing that way on
  screen. Columns: 0 and 2 are steps, 1 is standing. Frame index = row × 3 + column.
- Every right-facing frame is its left-facing frame mirrored. `down_left` is the face turned to the
  left and `up_left` the back of the head with the left cheek showing. Every view keeps the feet on
  the frame's bottom row, so one origin works for all of them.
- `<id>.json` is a Phaser JSON hash atlas naming each frame `<direction>-<column>`, e.g. `left-1`.
  Because the grid is uniform, `load.spritesheet(key, url, { frameWidth: 16, frameHeight: 24 })`
  works too.
- Walk with columns 0, 1, 2, 1; idle on column 1. The feet are at the bottom of the frame, so set
  the origin to `(0.5, 1)` and place the sprite where the feet go.
- `player` is the player. `sample_*` are placeholders until the generated NPCs exist. Each NPC in
  `content/npcs/<id>.json` gets `characters/<id>.png` drawn from its `appearance`, plus
  `preview/npcs.png`.

The client loads every atlas in `BootScene` and draws them with `pixelArt` in
`client/src/scenes/iso-characters.ts`, which picks one of the eight rows from each step
([`client/src/world/iso/README.md`](../../client/src/world/iso/README.md)).

Every `Appearance` option is drawn: hair `bald`, `buzz`, `short`, `curly`, `bob`, `long`,
`ponytail`, `bun`; build `slim`, `average`, `broad`; accessories `glasses`, `sunglasses`, `cap`,
`beanie`, `headphones`, `scarf`, `backpack`, `apron`. Scarves, caps, beanies and backpacks use an
accent colour that differs from the outfit; aprons are cream, or brown over a light top.

## Previews

`preview/` is for reviewing the art: `tiles.png`, `characters.png` (the player and samples at 1×,
2× and 3×), `walk.gif` (every walk cycle, round all eight facings) and `npcs.png` once NPCs exist.
