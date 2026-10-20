# Side

The village from the side (#306): part 2's maps ([`content/street/`](../../../content/street/README.md)),
part 3's papercraft scenery ([`content/papercraft/`](../../../content/papercraft/README.md)) and part
4's paper dolls ([`../dolls/`](../dolls/README.md)), drawn by `SideScene`, the game's world scene.
The menu starts it (`?play` skips the menu).

## Looking at it

`make dev` and open http://localhost:5173 with the server, or http://localhost:5173/?harness=side
without it: the dev harness (`harness.ts`) dispatches a stand-in snapshot on the side-view maps, a
clock, the murals and paintings from `content/works/`, and moves the residents through every pose by
the protocol, through `server.dispatch`.

| Query | |
|---|---|
| `at=<map>:<x>[:<y>]` | Where the player starts, e.g. `at=coffee_shop_floor_1:9`. |
| `hour=` and `speed=` | The sim hour to start at, and sim seconds a second (60). |
| `still` | The residents stay where they start. |
| `murals=0` | Leaves the mural walls blank. |
| `panel=0` | Hides the harness's help. |

Left and right (or A and D) walk. E or up takes a door in front of you; down also leaves a building
by its front door. E gets on stairs or a ladder, then up and down climb, stopping anywhere; E rides a
lift all the way. Where a terminal, the counter, a painting or a mural is in reach, E uses that
instead ([`world/reach.ts`](../world/reach.ts)), and up still takes a door. A hint says what E or up
takes where you stand ("Press E or ↑ to go into The Daily Grind.", `ways.ts`). Clicking a mural
looks at it. In the harness, `[` and `]` move the clock an hour and 1 to 4 go to each street.

## How it draws

Everything is in world px at the scenery's own scale, 120 px a metre, so a tile is 132 px and every
piece draws at scale 1. The camera shows the street 19 m tall (`camera.ts`), follows the player along
it, and rises to the top floor or drops to Banyan Row's river.

- **The street** (`street-view.ts`): the sky, far, mid, near and foreground layers repeated across
  the view at the manifest's parallax, the ground strips under the map's ground (the square, the park
  and the promenade too), ledges, steps and ladders from the `climbable` layer, each building's front
  with its glow map and murals, and the furniture.
- **Dollhouses** (`house.ts`): every building with floors has its floors drawn in place behind its
  front, each from its own map: the back wall in its room paper, windows, picture frames with their
  paintings, furniture, stairs, ladders, the lift shaft and cars, and the slabs. Entering a building
  lifts its front off; whatever is on the street in front of it goes faint.
- **Residents and the player** (`side-doll.ts`) are drawn with the rig's poses, worked out once per
  step of a cycle and kept (`poses.ts`), and tinted with the light where they are.
- **Light** (`light.ts`): the manifest's four times of day, blended across each change, give a tint
  for each layer's depth (distant layers take some of the sky's colour, the foreground falls
  darker), haze on the far and mid layers, the glow maps added at night and 55% in the evening, and
  lamplit rooms after dark.
- **Shadows** are made at runtime from each picture's alpha, blurred and offset (`textures.ts`).

Every texture is filtered smoothly, Phaser's default. A mural painted at another aspect than its
wall is cropped to cover it, not stretched (`coverCrop`). Each street loads its pictures when the
player first goes there and frees the last street's.

## Movement

The Phaser-free halves are tested under vitest.

- `residents.ts`: residents from `snapshot` and `entity_moved`, walked between positions, climbing on
  a map's stairs or ladder by their cell's kind, and `climbing` or `riding` at a link's end played
  along the link (`runs.ts`'s `crossing`) until the server moves them onto the other floor.
- `player.ts`: the player's walking, doors, climbs and rides by the lead's choices on #311. Walking
  stops at stairs and ladders, which are taken with E. While crossing between floors the player's
  position stays at the end they left from, as the protocol holds residents.
- Jumping isn't here. Positions are floats, so an arc through open air, drawn with the rig's
  `jumping` pose, can come later as another mode beside walking and climbing.

## What it provides

`scenes` exports `SideScene` (key `side-world`), started with `this.scene.start(SIDE_SCENE)`. It
reads the player's start from the snapshot, or the square on the High Street. It registers the
dialogue UI's world view, the audio's positions, the `MuralView` that finds the mural under a click,
and the hint for the way where the player stands, and updates `world/interactables.ts` with the
player's position every frame. The murals and paintings come from `world/murals.ts`'s and
`world/paintings.ts`'s stores, the maps from `world/assets.ts` (`content.ts` reads them into a
`Village`), and the dialogue scene hands the same `maps` to `ui/side-view.ts`.
