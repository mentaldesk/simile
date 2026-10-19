# Draft: the follow-up migration issue

To be filed held with `needs-human` once the study merges and only if the user picks the side view.
Nothing below starts until then.

---

**Title:** Side view: move the village to papercraft streets, floors and dollhouse cutaways

**Body:**

Held with `needs-human` until the user releases it. #295's study recommends the switch; this is the
work it would take. **Each numbered part is one issue and one PR**, with its own Owns, and no two
parts that can run at the same time own the same path. Parts that must change the same paths run
one after the other. Each part names the area of #295's "What a switch would touch" it covers.

The eleven residents keep their ids, values, voices, memories and `Appearance`. Only how they're
drawn changes, and their new art is made from the `Appearance` they already have.

## Order

1. **Part 1**, the contract PR, first. It only adds types, so it merges green on its own.
2. **Parts 2, 3 and 4** in parallel. They only create new paths, and nothing uses them yet, so
   the game stays isometric. Part 4 paints with part 3's painter, so it merges after part 3.
3. **Part 5** once 3 and 4 have merged: the side-view scene, built but not yet started.
4. **Part 6**, the cut-over, once 2 and 5 have merged. Server and client switch in one PR,
   because they share positions.
5. **Parts 7 and 8** in parallel, once 6 has merged.
6. **Part 9** last: it removes the old types and everything isometric that's left.

## Retired paths, and the part that deletes each

| Path | Deleted by |
|---|---|
| W1's map builder, `server/simile/world/build_map.py`, and `content/map/` | 6 |
| The iso client: `client/src/scenes/iso-scene.ts` (`IsoScene`), `iso-characters.ts`, `iso-critters.ts` | 6 |
| `client/src/world/iso/`, including the mural wall quads (`murals.ts`, `paintings.ts`) | 6 |
| `MuralWall`'s iso faces in `server/simile/world/map.py` | 6 |
| #116's Blender pipeline, `server/simile/art/iso/`, and `content/art/iso/` | 9 |
| A1's sprites and tileset: the rest of `server/simile/art/`, `server/simile/jobs/sprite.py`, `content/art/` | 9 |
| `Tile`, `MapTile`, `TileArea`, the eight-way `Facing`, and the protocol's `Face` | 9 |

## 1. Contract: side-view types, added alongside the old ones

*Locations and positions.* **Contract PR.**

**Owns:** `server/simile/schema/`, `server/simile/protocol/`, `client/src/net/protocol.ts`
(regenerated).

Adds the side-view types next to today's, without changing or removing any:

- A **walkway**: a street, or one floor of a building, as a span along x in metres.
- A **connection** between two walkways: its kind (stairs, ladder, lift or door) and the x at
  each end.
- A location's **span** on a walkway, or its room, and its entry as an x.
- A **position** as a walkway, x in metres along it and a height above it, so jumping can come
  later without another change. It keeps the shape of today's `Position` (x, y and map), with map
  read as the walkway and y as the height, so code that measures distances keeps working.
- Facing **left or right**, and a mural wall as a flat rectangle on a building front or a room's
  back wall.

The new fields are optional, nothing reads them yet, and the old types stay until part 9.

## 2. The side-view world on the server

*Movement.* After part 1.

**Owns:** `server/simile/street/` (new), `content/street/` (new), `server/tests/street/` (new).

The village as data: streets, buildings with floors and rooms, connections, locations, mural walls
and spots. Shortest paths over walkways and connections replace A* over the grid, plus distance
along a walkway and "same room". Fully tested, and not wired in: `server/simile/world/` doesn't
change here.

## 3. Papercraft scenery build step

*Gone: the replacement for W1's tiles and #116's renders.* Parallel with 2 and 4.

**Owns:** `server/simile/papercraft/` (new), `content/papercraft/` (new),
`server/tests/papercraft/` (new), and adding `onnxruntime` to `server/pyproject.toml` and
`server/uv.lock` if it isn't already there.

#295's `assets.py`, `cutout.py` and the scenery half of `compose.py`, made into a `simile
papercraft` command, with an edit-mode painter beside #296's `works/flux.py` (which only paints
from text). FLUX.2 Klein 4B in edit mode, with the references as style images, paints
each street layer, building front, room paper, furniture item, colour variant and platform piece,
and one night picture per building for its glow map. IS-Net plus the colour key cuts them out,
and each is scaled by the height kept beside its prompt. The cut-outs are committed, so CI and
other machines never run FLUX; tests that need it are marked `mlx`.

## 4. Paper-doll residents

*Characters and the creator.* Parallel with 2 and 3, merging after 3, whose painter it uses.

**Owns:** `server/simile/dolls/` (new), `content/dolls/` (new), `server/tests/dolls/` (new),
`client/src/dolls/` (new, an area without scenes).

- **Server.** #295's `doll.py`: the flat pieces from `Appearance`, the sheet, painting it in edit
  mode with the villagers reference, cutting the pieces on their outlines and pulling their
  colours back to the `Appearance`. About 58 s a resident. A job does the same for a new or
  changed character, replacing `jobs/sprite.py` (deleted in part 9).
- **Client.** The rig: each piece an image in a container, a pose a set of joint angles. Walking,
  standing and jumping are in the study; `Pose`'s sitting, reading, working and looking are new
  pose functions, with no new art. The flat pieces draw at once, before the painted ones exist.

`Appearance` doesn't change.

## 5. The side-view scene

*Gone: the replacement for `IsoScene`.* After parts 3 and 4.

**Owns:** `client/src/side/` (new).

Parallax layers, buildings along each street, dollhouse interiors (back wall, floor slabs,
furniture), murals as flat images on their walls, the residents through part 4's rig, runtime drop
shadows from each sprite's alpha, and time of day: a tint per time and layer depth, and the glow
maps at night. It reads part 3's and part 4's content and part 1's types. Nothing starts it yet.

## 6. The cut-over

*Movement, Locations and positions, Gone.* After parts 2 and 5. One PR for server and client.

**Owns:** `server/simile/world/`, `server/simile/persistence/`, `server/simile/works/walls.py`,
`content/map/`, `client/src/scenes/`, `client/src/world/`, `client/src/creator/`, and their tests
(`server/tests/world/`, `server/tests/persistence/`, `server/tests/works/`'s wall tests).

- **Server.** `Movement` (`walk_to`, `place`, `track`, `position`, `distance`) runs on part 2's
  world, and keeps its API so behaviour, voicing and the gallery work unchanged until parts 7
  and 8 tune them. Targets still given as tiles, such as the exercise loops and wander targets,
  snap to the nearest point on a walkway until part 8 replaces them. `on_player_move` takes
  side-view moves. Positions go out in part 1's fields.
  Mural walls are part 2's rectangles. Deletes `build_map.py`, `content/map/` and the iso
  `MuralWall` faces.
- **Saved worlds.** `SavedNpc.position` is a `Tile`. On load, a resident goes to their current
  location's entry rather than converting coordinates, so old saves still load.
- **Client.** The boot scene starts part 5's scene. Left and right walk; up and down take a
  stair, ladder or lift where there is one (`world/player.ts`, `map.ts`, `throttle.ts`,
  `motion.ts`, `doors.ts`). `TERMINAL_REACH_TILES` becomes metres. Sprites come from part 4's
  rig (`world/assets.ts`, `world/sprites.ts`, `scenes/boot-scene.ts`), and the creator previews
  the rig live. Deletes `IsoScene`, `iso-characters.ts`, `iso-critters.ts` and `world/iso/`.

## 7. Earshot and conversation range

*Earshot and conversation range.* After part 6, parallel with 8.

**Owns:** `server/simile/voicing/`, `server/simile/ambient/`, `server/simile/conversation/player.py`,
`client/src/ui/`, `client/src/audio/`, and their tests.

Distances become metres along a walkway, and two people on different walkways (another floor, or
the street and a room) are out of earshot unless they're in the same room.

- Server: `voicing/config.py` and `voicing.py` (`earshot`), `ambient/director.py` (`Earshot`) and
  `ambient/config.py`, `conversation/player.py` (`say_range`, `leave_range`, `near`),
  `ambient/playthrough.py`.
- Client: `ui/tuning.ts` (`EARSHOT_TILES`, `CHAT_RANGE_TILES`, `FULL_ALPHA_TILES`) and its users
  in `ui/bubbles.ts`, `ui/dialogue.ts`, `ui/target.ts`; `ui/mural-panel.ts`'s reach;
  `audio/spatial.ts` and `audio/positions.ts` (gain and pan, which suit a side view better than
  iso).

## 8. The NPC brain, unchanged: to confirm

*Unchanged, to confirm.* After part 6, parallel with 7.

**Owns:** `server/simile/behaviour/`, `server/simile/conversation/engine.py`,
`server/simile/gallery/`, and their tests.

Behaviour, conversation, relationships and memory reason about places, not tiles, except in a few
spots that move to walkways without changing what they decide:

- `behaviour/mind.py`: `_entry`, `_company` (`math.dist` within `near`), wandering within
  `wander_radius`, the exercise `LOOPS` (tile lists in `behaviour/config.py`), the `talk_range`
  check, spot choice, and following another entity.
- `behaviour/scoring.py` (`Places.at`, `MuralSpot`), `behaviour/simulate.py`'s nearness metrics,
  `behaviour/snapshot.py`'s spawn, `conversation/engine.py`'s `places.at(here)` and `facing`.
- `gallery/gallery.py` and `gallery/visits.py` (distance to doors and frames).
- `social/`, `memory/` and `reflection/` have no spatial reasoning and don't change.

Done when `simile behaviour simulate --hours 24 --seed 0` gives the same share of time per
location, within noise, before and after.

## 9. Contract cleanup and the last of iso

*Locations and positions, Gone.* Last. **Contract PR.**

**Owns:** `server/simile/schema/`, `server/simile/protocol/`, `client/src/net/protocol.ts`,
`server/simile/art/`, `server/simile/jobs/sprite.py`, `content/art/`, and their tests.

Removes `Tile`, `MapTile`, `TileArea`, the eight-way `Facing` and the protocol's `Face`, makes part
1's fields required, and deletes #116's Blender pipeline and A1's sprites and tileset. By now
nothing reads them.
