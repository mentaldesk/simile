# World

The village's maps and what the player can reach on them, Phaser-free and tested under vitest. The
side view ([`side/`](../side/README.md)) draws them: `BootScene` (`scenes/`) starts the menu, and
playing starts `SideScene`.

Run it with `make dev` and open http://localhost:5173. The residents go about their day (B1's
`simile.behaviour`); at 1x the first ones leave home a few minutes after the server starts.

## Assets

`assets.ts` bundles every street and floor map in [`content/street/`](../../../content/street/README.md):
`maps` has them all by id, and `mapIds` their ids. `maps` is one object that's never replaced, since
`ui/side-view.ts` tells side views by it. It also bundles every generated level in
`content/street/levels/<n>/` (`levels`), and `maps` has the maps of the level the world plays:
level 0's until the `snapshot` names one, then that one's (`playLevel`), and `onLevel` tells
listeners which ids changed. The dolls are part 4's (`dolls`, from `dolls/assets.ts`), and
someone without one of their own gets a resident's, the same one every time (`dollFor`). The
player's is the one for the bionics `player_state` last said were fitted (`playerBody`).

## Maps

A position's `map` is the map it's on. The server always sends it, and the client always sends it
in `player_move`: `mapOf` reads a position without one as on no map. `tileOf` is the tile the
server reads a position as, W2's `floor(p + 0.5)`. `nativeCanvas` (`canvas.ts`) sizes the game's
canvas in device pixels, and `MoveThrottle` sends the player's position at most five times a second,
and at once onto another map.

## What the player can reach

**Interactables** (`interactables.ts`) are a floor's `interactables` objects, each with its `area`
and `stand` tiles in tiles. `interactableAt(map, position)` is the interactable whose `stand` tile
the player is on, with its `prompt`: "Order at the counter", "Look at the painting", "Use the 3D
printer". The side scene updates `interactables` with the player's position every frame, and
`interactables.on(listener)` hears the interactable the player steps onto, and `undefined` when they
step off.

`terminalsOn(maps)` in [`terminals.ts`](terminals.ts) lists every map's news terminals, the
`terminal` locations on the streets, each with its label and area in tiles, and
`terminalAt(terminals, position)` finds the one within `TERMINAL_REACH_TILES` (1) of the tile the
player stands on, on the same map.

**Murals** (`murals.ts`): `muralWalls` keeps the latest `murals`, and `wallNear(walls, position)` is
the painted wall nearest the player on their street, within `MURAL_REACH_TILES` (3) along it of
either end. Every wall faces the camera. The scene drawing the murals registers a `MuralView`
(`setMuralView`) that finds the wall drawn at a canvas point, for clicks. **Paintings**
(`paintings.ts`): `galleryFrames` keeps the latest `paintings`.

**E** (`reach.ts`): `inReach(position)` lists what E can use, V look at or T order at where the
player stands, nearest first along the street: a terminal, a counter, a painting's frame, a painted
wall while murals are drawn, a pile within a tile (one the player left, or one in `player_state`'s
`piles`), the clinic while its doctor would buy a part of them, fit a bionic or treat them, or any
buyer with a part to sell back (`trades` in `buyers.ts`), or else the buyer where they stand while
they carry something it buys, or a clue from `content/story/story.toml` on the player's cell
(`clues.ts`), after a pile as near. Before any of them, a thing to search on the player's stand tile
(`searchables.ts`): a `searchable`, or with the datajack a jack holding `items`, `money` or
`teaches`, that `player_state`'s `searched` doesn't list yet. Its `items`, `money` and `teaches` come
from the map, so its prompt is "Search the dead fridge" and E says what it found ("You find 2 credits
and a ration bar.") as it sends `pick_up`. `usedByE` is the first that isn't a mural or a painting, which are
V's (`lookedAtByV`), or a counter, which is T's (`orderedAtByT`). E takes every door, and the
dialogue UI uses `usedByE` only off a door's cell, so one press does one thing. Stairs, ladders and
the lift are the arrows'. The side scene says what each key would take where the player stands, and
where on the canvas, through `setWayPrompts`, and the dialogue UI shows `wayPrompts()` over them.

`npcAt(point, view)` in [`hit.ts`](hit.ts) finds the NPC drawn at a canvas point from the view's
`spriteOf` boxes: front to back, the first whose frame is opaque there, else the first whose box
holds it. Choosing who to talk to and the debug overlay both click with it.

Speeds and distances are in [`tuning.ts`](tuning.ts).

The dev harnesses (`?harness=dialogue`, `?audio-harness`) don't start the world scene;
`?harness=side` starts it with stand-ins for the server.
