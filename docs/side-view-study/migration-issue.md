# Draft: the follow-up migration issue

To be filed held with `needs-human` once the study merges and only if the user picks the side view.
Nothing below starts until then.

---

**Title:** Side view: move the village to papercraft streets, floors and dollhouse cutaways

**Body:**

Held with `needs-human` until the user releases it. #295's study recommends the switch; this is the
work it would take, split by the areas #295 listed. Each numbered part is one issue and one PR, and
the parts marked **contract first** need their own small PR to `server/simile/schema/` or
`server/simile/protocol/` before anything builds on them.

The eleven residents keep their ids, values, voices, memories and `Appearance`. Only how they're
drawn changes, and their new art is made from the `Appearance` they already have.

## Order

1. **Part 3a, the contract PR,** first. Everything else reads positions.
2. Then parts 1, 2, 3b, 4 and 5 in parallel. They own separate paths.
3. Part 6 last: confirm the NPC brain is unchanged once positions have moved.

## 1. Gone, and what replaces it

Retire:

- W1's map builder: `server/simile/world/build_map.py`, `content/map/`, A1's tileset
  (`server/simile/art/tiles.py`, `content/art/tiles.*`).
- #116's Blender scenery pipeline: `server/simile/art/iso/`, `content/art/iso/`.
- The iso client: `client/src/scenes/iso-scene.ts`, `iso-characters.ts`, `iso-critters.ts` and
  `client/src/world/iso/` (projection, camera, depth, cutaway, interiors, crossfade, lighting,
  shadow, time of day, controls).
- The mural wall quads: `client/src/world/iso/murals.ts` and `paintings.ts`; the iso `Face` on
  `MuralWall` (`server/simile/world/map.py`) and `Wall` (`protocol/messages.py`).

Replace with, as separate issues:

- **1a. Scenery build step** (`server/simile/art/side/`, `content/art/side/`). FLUX.2 Klein 4B
  through mflux in edit mode, with #295's references as style images, paints each street layer,
  building front, room paper, furniture item and platform piece on white. IS-Net plus a colour key
  cuts them out (#295's `cutout.py`), and they're scaled by a real-world height kept beside each
  prompt. Paintings are cached and committed, so CI and other machines never run FLUX. Marked
  `mlx` tests only.
- **1b. Side-view client scene** (`client/src/scenes/`, `client/src/world/side/`). Parallax layers,
  buildings along each street, dollhouse interiors as rooms with a back wall, floor slabs and
  furniture sprites, and runtime drop shadows from each sprite's alpha.
- **1c. Time of day.** One tint per time and per layer depth, plus an emission map per building
  for lit windows and lamps at night, as #295's `time-of-day` picture does. Replaces #116's four
  lighting sets.
- **1d. Murals and paintings.** A wall is a flat rectangle on a building front or a room's back
  wall, so it's drawn as a plain image, with no quads and no faces. **Contract first** if `Wall`
  changes shape, and it rides in part 3a's PR.

## 2. Movement

- Open ground becomes walkways: each street and each floor of a building is a span along x, joined
  by stairs, ladders, lifts and doors as edges. A* over a grid becomes a shortest path over that
  graph: `server/simile/world/paths.py` (`find_path`, `find_route`), `world/movement.py`
  (`Movement.walk_to`, `place`, `track`), `world/spots.py`, and `world/map.py`'s collision layer.
- `player_move`: `on_player_move` in `server/simile/world/lifespan.py`, and on the client
  `world/player.ts`, `world/map.ts`, `world/throttle.ts`, `world/motion.ts`, `world/doors.ts`.
  Left and right walk, up and down take a stair, ladder or lift where there is one.
- **Leave room for jumping.** Keep x and height continuous and treat a floor as a span at a
  height, so a later platformer stage adds gravity and jumps without another position change.

## 3. Locations and positions

- **3a. Contract first: the schema and protocol PR.** `server/simile/schema/world.py` (`Tile`,
  `MapTile`, `TileArea`, `Location.area` and `entry`, `Door`, `Interactable` stand tiles,
  `Facing`) and `protocol/messages.py` (`Position`, `Entity`, `SnapshotMessage`,
  `EntityMovedMessage`, `PlayerMoveMessage`, `Wall`, `Face`, `MuralsMessage`), regenerated through
  `protocol/export.py` (the client's `net/protocol.ts`) and `schema/export.py`.
  A sketch: a position is a walkway id, x in metres along it and a height above it; a location is
  a span of a walkway or a room; `Facing` is left or right; a connection names its two ends and
  its kind (stairs, ladder, lift, door).
- **3b. Saved worlds.** `server/simile/persistence/state.py` saves `SavedNpc.position` as a
  `Tile`. On load, put each resident at their current location's entry rather than converting
  coordinates, so old saves still load.

## 4. Characters and the creator

- A1's generator (`server/simile/art/characters.py`, `art/build.py`, `jobs/sprite.py`,
  `art/routes.py`'s preview) becomes the paper-doll pipeline from #295's `doll.py`: flat part shapes
  from `Appearance`, laid out on a sheet, painted by FLUX in edit mode with the villagers reference,
  cut along the known outlines and pulled back to the `Appearance` colours. About 45 s a resident.
- The rig runs in the client: each piece is an image in a container, and a pose is a set of joint
  angles. Walking, standing and jumping are in the study; `Pose`'s sitting, reading, working and
  looking are new pose functions, with no new art.
- The creator (`client/src/creator/`, `look.ts`'s `SpritePreview`) shows the rig live: changing a
  colour retints the flat pieces at once, and the painted pieces follow when the job finishes.
- Sprite loading: `world/assets.ts`, `scenes/boot-scene.ts`, `world/sprites.ts`. `Appearance`
  itself doesn't need to change.

## 5. Earshot and conversation range

Distances become metres along a walkway, and two people on different walkways (another floor, the
street and a room) are out of earshot unless they're in the same room.

- Server: `voicing/config.py` and `voicing.py` (`earshot`), `ambient/director.py` (`Earshot`) and
  `ambient/config.py`, `conversation/player.py` (`say_range`, `leave_range`, `near`),
  `behaviour/config.py` (`near`, `talk_range`, `wander_radius`), `ambient/playthrough.py`.
- Client: `ui/tuning.ts` (`EARSHOT_TILES`, `CHAT_RANGE_TILES`, `FULL_ALPHA_TILES`) and its users
  in `ui/bubbles.ts`, `ui/dialogue.ts`, `ui/target.ts`; `audio/spatial.ts` and
  `audio/positions.ts` (gain and pan, which suit a side view better than iso);
  `world/tuning.ts` (`TERMINAL_REACH_TILES`).

## 6. Unchanged, to confirm: the NPC brain

Behaviour, conversation, relationships and memory reason about places, not tiles, except in a few
spots that move to the new positions without changing what they decide:

- `behaviour/mind.py`: `_entry`, `_company` (`math.dist` within `near`), wandering to random tiles
  within `wander_radius`, the exercise `LOOPS` (tile lists in `behaviour/config.py`), the
  `talk_range` check, spot choice, and following another entity's `MapTile`.
- `behaviour/scoring.py` (`Places.at`, `MuralSpot`), `behaviour/simulate.py`'s nearness metrics,
  `behaviour/snapshot.py`'s spawn, `conversation/engine.py`'s `places.at(here)` and `facing`.
- `gallery/gallery.py` and `gallery/visits.py` (distance to doors and frames).
- `social/`, `memory/` and `reflection/` have no spatial reasoning.

Done when `simile behaviour simulate --hours 24 --seed 0` gives the same share of time per
location, within noise, before and after.
