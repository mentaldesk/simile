# World

The village and its interiors as the player sees them. `scenes/` has the Phaser side: `BootScene`
loads every character atlas, then starts `IsoScene`, which draws the map the player is on isometric
from the pre-rendered scenery and moves the player ([`iso/README.md`](iso/README.md)). Everything
here in `world/` is Phaser-free and tested under vitest.

Run it with `make dev` and open http://localhost:5173. The residents go about their day (B1's
`simile.behaviour`); at 1x the first ones leave home a few minutes after the server starts.

Arrow keys or WASD move the player in screen directions, so up is north-west on the map.

## Assets

`assets.ts` imports the village and every `content/art/characters/*` atlas through Vite, so they're
bundled into the build and new NPC sprites show up without code changes. Each interior map embeds
the tileset, about 120 KB, so it's bundled as a file of its own and fetched by `loadMap(id)` when
the scene first needs it. `maps` has the village and every interior loaded so far, and `mapIds`
every map's id. An NPC without its own atlas gets one of the `sample_*` sprites, the same one every
time (`characterFor`). The scenery's renders are `iso/assets.ts`'s.

## Movement

- **NPCs** follow `entity_moved`. Each position is queued and walked to at `WALKING_SPEED`, so a
  sprite moves continuously one tile behind the server when the server sends each tile as the NPC
  reaches it (W2's contract). A jump of more than 1.5 tiles snaps, and an NPC more than a few tiles
  behind hurries, then snaps. Each NPC keeps the `pose` and `facing` of its latest snapshot or
  `entity_moved`, standing facing south-east without them, for the scene to draw once it stops.
- **The player** is the client's: it moves at `PLAYER_SPEED` and collides locally with the map's
  `collision` layer around its feet (`FOOTPRINT`), and the scene sends `player_move` at most five
  times a second. The footprint always covers the tile W2 reads the position as, `floor(p + 0.5)`,
  so the server never thinks the player is standing in a wall. Only the first `snapshot` places it;
  after a reconnection it stays put and sends its position again.

Speeds and distances are in [`tuning.ts`](tuning.ts).

## Maps and doors

A position's `map` is the map it's on, and one without a map is on the village (`mapOf`). The player
always has one, and `player_move` always sends it. `world.map` is the player's map, the only one
drawn.

- **Doors** (`doors.ts`): `doorsOn(map)` lists the doors with an end on a map, from its `doors` layer.
  Each end knows the other and its way `out`: south off a doorstep, north from an interior's mat.
- **Going through** (`Doorways`): when the player steps onto a door's tile, as the server reads it
  (`tileOf`), while walking towards the door, the view fades to black over `DOOR_FADE_OUT_SECONDS`
  with the player held still. At black, once the scene can draw the other side, the player lands on
  the door's other end facing out, and the view fades back in over `DOOR_FADE_IN_SECONDS`. The
  scene sends that `player_move` at once, with the new map.
- **No bouncing**: a player who arrives on a door, by a door or the first snapshot, has to step off
  it before any door takes them anywhere. Walking past a doorstep along the pavement doesn't go in,
  since it isn't towards the door.

An NPC going through a door arrives as an `entity_moved` onto the other map: it disappears from one
map and appears on the other.

## What it provides

`IsoScene` registers itself as the dialogue UI's `WorldView` and as audio's position provider, with
the player as the listener. Other code can read `world` (`world.positionOf(id)`, `world.npcs`,
`world.player`, `world.map`) from `world/model.ts`. Only the NPCs on the player's map are drawn,
heard and picked: `world.here()` lists them, and `positionOf` is `undefined` for the others.
`whereIs(id)` is anyone's position on any map, which audio uses to silence voices from another map.

**Interactables** (`interactables.ts`) work like the news terminals. `interactableAt(map, position)`
is the interactable whose `stand` tile the player is on, with its `prompt`: "Order at the counter",
"Look at the painting", "Use the 3D printer". The scene updates `interactables` with the player's
position every frame, and `interactables.on(listener)` hears the interactable the player steps onto,
and `undefined` when they step off. What each one opens belongs to its building's task.

`terminalsOf(map)` in [`terminals.ts`](terminals.ts) lists the map's news terminals, each with its
label and area in tiles, and `terminalAt(terminals, position)` finds the one within
`TERMINAL_REACH_TILES` (1) of the tile the player stands on, on the same map. The dialogue UI opens
the news there.

`npcAt(point, view)` in [`hit.ts`](hit.ts) finds the NPC drawn at a canvas point from the view's
`spriteOf` boxes: front to back, the first whose frame is opaque there, else the first whose box
holds it. Choosing who to talk to and the debug overlay both click with it.

The dev harnesses (`?harness=dialogue`, `?audio-harness`) don't start the world scene.
