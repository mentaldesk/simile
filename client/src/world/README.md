# World

The village as the player sees it. `scenes/` has the Phaser side: `BootScene` loads the map and
every character atlas, then starts `WorldScene`, which draws the map and the characters and moves
the player. Everything here in `world/` is Phaser-free and tested under vitest.

Run it with `make dev` and open http://localhost:5173. The residents go about their day (B1's
`simile.behaviour`); at 1x the first ones leave home a few minutes after the server starts.

Arrow keys or WASD move the player.

## Assets

`assets.ts` imports the map, the tileset and every `content/art/characters/*` atlas through Vite,
so they're bundled into the build and new NPC sprites show up without code changes. An NPC without
its own atlas gets one of the `sample_*` sprites, the same one every time (`characterFor`).

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
- Facing comes from the direction of travel, picking a 4-way facing on diagonals. Walk cycles play
  at `WALK_FPS` at walking speed, faster for the player.

Speeds and distances are in [`tuning.ts`](tuning.ts).

## What it provides

`WorldScene` registers itself as the dialogue UI's `WorldView` (bubbles anchor on the top centre of
each sprite) and as audio's position provider, with the player as the listener. Other code can read
`world` (`world.positionOf(id)`, `world.npcs`, `world.player`) from `world/model.ts`.

`terminalsOf(map)` in [`terminals.ts`](terminals.ts) lists the map's news terminals, each with its
label and area in tiles, and `terminalAt(terminals, position)` finds the one within
`TERMINAL_REACH_TILES` (1) of the tile the player stands on. The dialogue UI opens the news there.

`npcAt(point, view)` in [`hit.ts`](hit.ts) finds the NPC drawn at a canvas point: the 48 × 72 box
under their `bubbleAnchor`, the one in front where sprites overlap. Choosing who to talk to and the
debug overlay both click with it, so a new projection changes it here.

## Rendering

Tiles and sprites are 16 px, drawn at 3× (`ZOOM`). The camera follows the player and stops at the
map's edges, and keeps its centre on a whole world pixel so every art pixel is exactly 3×3 canvas
pixels. Layers `ground`, `buildings` and `decor` are under the characters, `above` over them, and
characters are sorted by where their feet are. `main.ts` shows the 640×360 canvas at the largest
zoom that fits the window and draws each canvas pixel as whole device pixels (`pixelZoom`). It
sizes from the window, not the page, and hides page overflow, so scrollbars can't feed back into the
zoom (`fitZoom`).

The dev harnesses (`?harness=dialogue`, `?audio-harness`) don't start the world scene.
