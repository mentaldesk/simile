# World

The village as the player sees it. `scenes/` has the Phaser side: `BootScene` loads every character
atlas, then starts `IsoScene`, which draws the village isometric from the pre-rendered scenery and
moves the player ([`iso/README.md`](iso/README.md)). Everything here in `world/` is Phaser-free and
tested under vitest.

Run it with `make dev` and open http://localhost:5173. The residents go about their day (B1's
`simile.behaviour`); at 1x the first ones leave home a few minutes after the server starts.

Arrow keys or WASD move the player in screen directions, so up is north-west on the map.

## Assets

`assets.ts` imports the map and every `content/art/characters/*` atlas through Vite, so they're
bundled into the build and new NPC sprites show up without code changes. An NPC without its own
atlas gets one of the `sample_*` sprites, the same one every time (`characterFor`). The scenery's
renders are `iso/assets.ts`'s.

## Movement

- **NPCs** follow `entity_moved`. Each position is queued and walked to at `WALKING_SPEED`, so a
  sprite moves continuously one tile behind the server when the server sends each tile as the NPC
  reaches it (W2's contract). A jump of more than 1.5 tiles snaps, and an NPC more than a few tiles
  behind hurries, then snaps.
- **The player** is the client's: it moves at `PLAYER_SPEED` and collides locally with the map's
  `collision` layer around its feet (`FOOTPRINT`), and the scene sends `player_move` at most five
  times a second. The footprint always covers the tile W2 reads the position as, `floor(p + 0.5)`,
  so the server never thinks the player is standing in a wall. Only the first `snapshot` places it;
  after a reconnection it stays put and sends its position again.

Speeds and distances are in [`tuning.ts`](tuning.ts).

## What it provides

`IsoScene` registers itself as the dialogue UI's `WorldView` and as audio's position provider, with
the player as the listener. Other code can read `world` (`world.positionOf(id)`, `world.npcs`,
`world.player`) from `world/model.ts`. Only the NPCs on the player's map are drawn, heard and
picked: `world.here()` lists them, and `positionOf` is `undefined` for the others.

`terminalsOf(map)` in [`terminals.ts`](terminals.ts) lists the map's news terminals, each with its
label and area in tiles, and `terminalAt(terminals, position)` finds the one within
`TERMINAL_REACH_TILES` (1) of the tile the player stands on. The dialogue UI opens the news there.

`npcAt(point, view)` in [`hit.ts`](hit.ts) finds the NPC drawn at a canvas point from the view's
`spriteOf` boxes: front to back, the first whose frame is opaque there, else the first whose box
holds it. Choosing who to talk to and the debug overlay both click with it.

The dev harnesses (`?harness=dialogue`, `?audio-harness`) don't start the world scene.
