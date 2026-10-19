# Draft: the follow-up migration issue

To be filed held with `needs-human` once the study merges and only if the user picks the side view.
Nothing below starts until then.

---

**Title:** Side view: move the village to papercraft streets, floors and dollhouse cutaways

**Body:**

Held with `needs-human` until the user releases it. #295's study recommends the switch; this is the
work it would take. **Each numbered part is one issue and one PR**, and each names the area of
#295's "What a switch would touch" it covers.

**Ownership rules:**

- Every part lists what it owns, and no two parts that can run at the same time own the same path.
  Parts that must change the same file run one after the other.
- **A part that deletes, moves or removes something, or changes a default other code relies on,
  also owns every file that imports or reads it, tests included, and updates them in the same
  PR.** Every such file is listed under the part, from a search of `main`.

The eleven residents keep their ids, values, voices, memories and `Appearance`. Only how they're
drawn changes, and their new art is made from the `Appearance` they already have.

## The approach, for the user to choose

**This departs from #295's sketch**, which has a contract change for positions and distance along
a street. It's offered as an option for the user to choose, alongside that sketch.

The sim stays on its grid. A side-view map is still a Tiled grid, read the other way up: x runs
along the street, y counts rows down from the top, and a resident stands on a cell with solid
ground under it. Every building is an interior map joined to the street by its door, as today.
Only the neighbour rule changes: left and right on the ground, and up and down only where the map
allows it (stairs, ladders, lifts). So `Tile`, `MapTile`, `TileArea`, `Position`, `Facing` and the
protocol's `Face` keep their shape, and nothing that uses them has to change because of them.
Every mural wall faces the camera (`south`). The questions this leaves open are below.

## Decisions before the migration starts

These are the user's, once they've decided to switch. The parts below assume whichever is chosen.

1. **How floors connect inside one map.** Today's `Door` rejects two ends on the same map
   (`Door._between_maps` in `schema/world.py`), and part 1 as drafted only adds `kind`.
   - Drop the same-map check in part 1, so a stair, ladder or lift is a `Door` between two cells
     of one map.
   - Or give stairs, ladders and lifts their own map layer, which part 2's neighbour rule reads,
     and keep `Door` for doors between maps.
2. **Map ids.** One outdoor map called `village` is assumed by `VILLAGE_MAP` (`schema/world.py`)
   and `MAP_ID` (`world/map.py`, `protocol/fixtures.py`), by `Position.map`'s default, by a
   `player_move` with no map (which means the village), by `sim/events.py`, and by tests that
   place people on `coffee_shop` tiles.
   - Keep today's ids: one `village` map holding every street, and interiors by location id.
     Part 7's per-map tables then need another key, such as the location.
   - Or change them (a map per street, a map per floor): a contract change, owned in part 1, with
     every user above in its Owns.
3. **Jumping later.** #295 asks for a world that can take jumping. On a grid of standing cells, a
   jump is a move through empty cells along an arc, with gravity bringing the jumper down onto the
   next cell with ground under it. `Position` already holds float x and y, so a resident can be
   between cells mid-air. What it would need: the client running the arc (part 8's player
   movement), the neighbour rule allowing jumps of a set reach (part 2), and a way for the server
   to accept a position in the air (`player_move`). None of that is in this migration.
4. **Facing.** The eight-way `Facing` has three eastward values (`north_east`, `east`,
   `south_east`), three westward ones, and `north` and `south`. Eastward is drawn facing right and
   westward facing left, but `north` and `south` have no side-view meaning. Today's map builder
   points viewing, desk, bar and terminal spots `north`, and a resident looking at a mural faces
   `north`.
   - Draw `north` as the back of the doll (facing into the picture) and `south` as its front, which
     needs two more poses in part 4's rig.
   - Or map them onto left and right (keep the last direction), and point those spots east or west
     in part 2's maps.

## Order

1. **Part 1**, the contract PR, first. It only adds an optional field, so it merges green.
2. **Parts 2, 3 and 4** in parallel. They create new paths only, and nothing uses them yet, so the
   game stays isometric. Part 4 paints with part 3's painter, so it merges after part 3.
3. **Part 5** after 3 and 4. **Parts 6 and 7** after 2. All three can run at the same time.
4. **Part 8**, the cut-over, after 5, 6 and 7. Server and client switch in one PR.
5. **Part 9** last: it deletes the isometric pipeline, W1's builder and A1's sprites.

## Retired paths, and the part that deletes each

| Path | Deleted by |
|---|---|
| The iso client: `client/src/scenes/iso-scene.ts` (`IsoScene`), `iso-characters.ts`, `iso-critters.ts` and `client/src/world/iso/`, with the mural wall quads | 8 |
| W1's map builder, `server/simile/world/build_map.py` and `simile map`, and `content/map/` | 9 |
| #116's Blender pipeline, `server/simile/art/iso/`, `content/art/iso/` and `server/tests/art/iso/` | 9 |
| A1's sprites and tileset: the rest of `server/simile/art/`, `server/simile/jobs/sprite.py`, `content/art/` and `server/tests/art/` | 9 |

`art/palette.py` and `art/characters.py`'s `SKIN_TONES` and `PLAYER` are the `Appearance` palette,
not A1's sprites: part 9 moves them rather than deleting them.

## 1. Contract: connection kinds

*Locations and positions.* **Contract PR.**

**Owns:** `server/simile/schema/`, `server/simile/protocol/`, `client/src/net/protocol.ts`
(regenerated), `server/tests/schema/`, `server/tests/protocol/`.

`Door` gains an optional `kind`: door (the default), stairs, ladder or lift, so a connection
can say how it's crossed. The docs on `Tile`, `Position`, `Facing` and `Face` say how a side-view
map reads them, as above. If decision 1 joins floors with doors, part 1 also drops
`_between_maps`'s same-map check, and if decision 2 changes the map ids, part 1 owns that change
and every user of them. Nothing else is removed.

## 2. Side-view maps and the neighbour rule

*Movement, Locations and positions.* After part 1.

**Owns:** `server/simile/street/` (new), `content/street/` (new), `server/tests/street/` (new).

A builder for side-view maps of the village and its interiors, replacing W1's for the new world,
with the same layers as today (locations, doors, spots, interactables, murals, collision), plus
a layer for stairs, ladders and lifts if decision 1 picks one, and **the same location, door, spot
and interactable ids** as `content/map/`, so code that works by id keeps working. Each house
interior holds its floors and rooms, joined as decision 1 settles. The neighbour
rule for pathfinding lives here too, with tests. Nothing loads these maps yet.

## 3. Papercraft scenery build step

*Gone: the replacement for W1's tiles and #116's renders.* Parallel with 2 and 4.

**Owns:** `server/simile/papercraft/` (new), `content/papercraft/` (new),
`server/tests/papercraft/` (new), and adding `onnxruntime` to `server/pyproject.toml` and
`server/uv.lock` if it isn't already there.

#295's `assets.py`, `cutout.py` and the scenery half of `compose.py`, made into a `simile
papercraft` command, with an edit-mode painter beside #296's `works/flux.py` (which only paints
from text). FLUX.2 Klein 4B in edit mode, with the references as style images, paints each street
layer, building front, room paper, furniture item, colour variant and platform piece, and one night
picture per building for its glow map. IS-Net plus the colour key cuts them out, and each is scaled
by the height kept beside its prompt. The cut-outs are committed, so CI and other machines never
run FLUX; tests that need it are marked `mlx`.

## 4. Paper-doll residents

*Characters and the creator.* Parallel with 2 and 3, merging after 3, whose painter it uses.

**Owns:** `server/simile/dolls/` (new), `content/dolls/` (new), `server/tests/dolls/` (new),
`client/src/dolls/` (new, an area without scenes).

- **Server.** #295's `doll.py`: the flat pieces from `Appearance`, the sheet, painting it in edit
  mode with the villagers reference, cutting the pieces on their outlines and pulling their
  colours back to the `Appearance`. About 58 s a resident. A doll job does the same for a new or
  changed character; part 9 registers it in place of A1's sprite job. Like the study's `doll.py`,
  it takes each resident's accent colour from `simile.art.characters.Colours` and the player's
  look from `PLAYER` there, until part 9 moves them.
- **Client.** The rig: each piece an image in a container, a pose a set of joint angles. Walking,
  standing and jumping are in the study; `Pose`'s sitting, reading, working and looking are new
  pose functions, with no new art. The flat pieces draw at once, before the painted ones exist.

## 5. The side-view scene

*Gone: the replacement for `IsoScene`.* After parts 3 and 4.

**Owns:** `client/src/side/` (new).

Parallax layers, buildings along each street, dollhouse interiors (back wall, floor slabs,
furniture), murals as flat images on their walls, the residents through part 4's rig, runtime drop
shadows from each sprite's alpha, and time of day: a tint per time and layer depth, and the glow
maps at night. Nothing starts it yet.

## 6. Earshot and conversation range, in both worlds

*Earshot and conversation range.* After part 2, parallel with 5 and 7.

**Owns:** `server/simile/voicing/`, `server/simile/ambient/`,
`server/simile/conversation/player.py`, `client/src/ui/`, `client/src/audio/`,
`server/tests/voicing/`, `server/tests/ambient/`, `server/tests/conversation/test_player.py`.

On a side-view map, distance is along x on the same floor, and people on different floors are
out of earshot. On today's maps nothing changes. The tests load both `content/map/` and
`content/street/` by path, so part 8's switch of the default doesn't touch them.

- Server: `voicing/config.py` and `voicing.py` (`earshot`), `ambient/director.py` (`Earshot`) and
  `ambient/config.py`, `conversation/player.py` (`say_range`, `leave_range`, `near`),
  `ambient/playthrough.py`.
- Client: `ui/tuning.ts` (`EARSHOT_TILES`, `CHAT_RANGE_TILES`, `FULL_ALPHA_TILES`) and its users
  in `ui/bubbles.ts`, `ui/dialogue.ts`, `ui/target.ts`; `ui/mural-panel.ts`'s reach;
  `audio/spatial.ts` and `audio/positions.ts` (gain and pan, which suit a side view better than
  iso).

## 7. The NPC brain and the café, in both worlds

*Unchanged, to confirm.* After part 2, parallel with 5 and 6.

**Owns:** `server/simile/behaviour/`, `server/simile/conversation/` except `player.py`,
`server/simile/gallery/`, `server/simile/cafe/`, `server/tests/behaviour/`,
`server/tests/conversation/` except `test_player.py`, `server/tests/gallery/`, `server/tests/cafe/`.

Behaviour, conversation, relationships and memory reason about places, not tiles. What's tied to
today's map becomes a table with entries for both worlds' maps, keyed as decision 2 settles
(by map id, or by location if the ids stay), so it reads the same from either:

- `behaviour/config.py`'s exercise `LOOPS` (tile lists).
- `cafe/config.py`'s `entrance`, `machine`, `hand_over` and the other fixed tiles, and the
  direction `cafe/cafe.py`'s queue grows in (down the grid today, along the floor in side view).
- `behaviour/mind.py`'s wandering picks walkable cells by the map's neighbour rule, and
  `conversation/engine.py`'s `facing` turns people east or west on a side-view map.
- `behaviour/scoring.py` (`Places.at`, `MuralSpot`), `behaviour/simulate.py`,
  `behaviour/snapshot.py` and `gallery/gallery.py`, `visits.py` and `cli.py` take the maps they're
  given rather than loading the default, so they follow the server's world.
- `social/`, `memory/` and `reflection/` have no spatial reasoning and don't change.

The tests load both worlds by path. Done when `simile behaviour simulate --hours 24 --seed 0`
gives the same share of time per location, within noise, in both.

## 8. The cut-over

*Movement, Locations and positions, Gone.* After parts 5, 6 and 7. One PR for server and client.

**Server.** `load_maps()`'s default (`world/map.py`'s `MAP_DIR`) becomes `content/street/`, and
movement uses part 2's neighbour rule. Saved positions that aren't standing cells in the new maps
go to their location's entry, so old saves still load. Mural walls face the camera:
`works/sightings.py`'s "in front of the wall" becomes the same floor, and `works/render.py` sizes
murals for the side view without importing `art/iso/`. Everything other packages import from
`server/simile/world/` (`Movement`, `Point`, `movement_of`, `inside`, `load_maps`, `TownMap`,
`MuralWall`, `Spot`, `SpotKind`, `find_route`, `choose` and the rest) keeps its name and
signature.

- **Owns:** `server/simile/world/` except `build_map.py` and `cli.py`, `server/simile/persistence/`,
  `server/simile/works/walls.py`, `render.py` and `sightings.py`, `server/tests/world/`,
  `server/tests/persistence/`, `server/tests/works/conftest.py`, `test_walls.py`, `test_render.py`,
  `test_sightings.py`. `tests/world/test_murals.py` drops its imports of `build_map.py` and
  `art/iso/`, and `tests/world/test_map.py` reads `content/map/` by path until part 9 deletes
  both.
- **And, because the default maps change,** every other file that loads them without a path:
  `server/simile/casting/bind.py` (the houses), `server/simile/works/cli.py` (the walls),
  `server/tests/casting/test_roles.py`, `debug/test_state.py`, `economy/test_economy.py`,
  `economy/test_loans.py`, `economy/test_residents.py`, `npc/test_generate.py`,
  `reflection/test_loans.py`, `schema/test_models.py`, `tools/test_recorder.py`,
  `works/test_cli.py`, `works/test_starters.py`. With the same ids in both worlds, most need no
  change.

**Client.** The menu and boot scene start part 5's scene. Left and right walk; up and down take a
stair, ladder or lift (`world/player.ts`, `map.ts`, `throttle.ts`, `motion.ts`, `doors.ts`).
`world/assets.ts` and `maps.fixture.ts` read `content/street/` and part 4's dolls instead of
`content/map/` and A1's atlases, and the creator previews the rig instead of calling
`/api/art/preview`. It still saves through A1's sprite job until part 9. `TERMINAL_REACH_TILES`
stays in tiles. The non-drawing halves of `world/iso/murals.ts` and `paintings.ts` (`MuralWalls`,
`muralWalls`, `wallNear`, `muralView`, `GalleryFrames`, `galleryFrames`) move to
`client/src/world/`. Then it deletes `IsoScene`,
`iso-characters.ts`, `iso-critters.ts` and `world/iso/`. The other modules that `audio/`, `debug/`
and `ui/` import from `client/src/world/` (`map`, `hit`, `view`, `interactables`, `terminals`,
`assets`, `tuning`) keep their exports.

- **Owns:** `client/src/scenes/`, `client/src/world/`, `client/src/creator/`, and the importers of
  what it deletes: `client/src/main.ts` (`world/iso/canvas`), `client/src/menu/menu-scene.ts`
  (`ISO_SCENE`), `creator/look.ts` (`world/iso/sheets`), and in `client/src/ui/`
  `dialogue-scene.ts`, `gallery-scene.ts`, `gallery-panel.ts`, `mural-panel.ts`,
  `gallery-panel.test.ts`, `mural-panel.test.ts` and `README.md`. In `ui/`, part 8 only repoints
  those imports and the README's mention of `IsoScene`; part 6 has already done the rest of
  `ui/`.

## 9. The last of iso, W1 and A1

*Gone.* Last.

**Deletes:** `server/simile/world/build_map.py` and the `simile map` command in `world/cli.py`,
`content/map/`, `server/simile/art/` (A1 and #116's `art/iso/`), `content/art/`,
`server/simile/jobs/sprite.py`, `server/tests/art/`, `server/tests/world/test_map.py` and
`server/tests/jobs/test_sprite.py`.

**Moves:** `art/palette.py`, and `SKIN_TONES` and `PLAYER` from `art/characters.py`, to
`server/simile/characters/palette.py`, with `server/tests/art/test_palette.py` going to
`server/tests/characters/test_palette.py`.

**Owns** what it deletes and moves, and every importer or reader of them:

- The palette: `server/simile/characters/generate.py`, `characters/biography.py`,
  `npc/generate.py`, `library/store.py`, `server/tests/characters/test_generate.py`,
  `server/tests/library/test_routes.py`, and `client/src/creator/palette.test.ts`, which reads
  `art/characters.py` as text.
- `art/iso/`: `server/simile/jobs/capabilities.py` (`blender.find`) and
  `server/tests/jobs/test_capabilities.py`. Part 8 has already removed `works/render.py`'s and
  `tests/world/test_murals.py`'s imports of it.
- The sprite job: `server/simile/jobs/lifespan.py` (`SPRITE`), which registers part 4's doll job
  instead; `client/src/creator/look.ts` and `look.test.ts`, which submit `sprite` jobs and read
  `/api/jobs/files/sprite/`, and switch to the doll job; and `server/tests/jobs/test_routes.py`,
  which tests the `sprite` kind.
- `Colours` and `PLAYER` in `server/simile/dolls/`: part 9 moves `Colours.of`'s accent and apron
  rule into `characters/palette.py` with the palette, and repoints the dolls' imports of both.
  `server/simile/papercraft/` imports neither.
- `art/routes.py`'s `/api/art/preview`: `server/tests/test_guard.py`, which lists the guarded
  routes. Part 8 has already moved the creator off it.
- `content/art/`: `server/simile/worlds/store.py` (`SPRITES`, which checks for a resident's art in
  `content/dolls/` instead), `server/tests/cafe/test_barista.py` and
  `server/tests/jobs/test_runner.py`.
- `content/map/` and `build_map.py`: `server/simile/world/cli.py` (`simile map`). Part 8 moved
  `MAP_DIR` and every other reader to `content/street/`, and the rest of their readers are deleted
  here.
- The docs that point at what's gone: the READMEs in `server/simile/world/`, `jobs/`, `worlds/`
  and `library/`, and in `client/src/world/` and `client/src/creator/`.

`Tile`, `MapTile`, `TileArea`, `Facing` and `Face` stay, so `sim/events.py`, `cafe/`, and the tests
in `cafe/`, `tools/`, `works/conftest.py` and `conversation/test_loans.py` that use them only
change where a part above owns them for another reason (`cafe/` and its tests in part 7,
`conversation/test_loans.py` in part 7, `tools/test_recorder.py` and `works/conftest.py` in
part 8).
