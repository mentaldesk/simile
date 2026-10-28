# Side

The village from the side (#306): part 2's maps ([`content/street/`](../../../content/street/README.md)),
part 3's papercraft scenery ([`content/papercraft/`](../../../content/papercraft/README.md)) and
the residents' painted figures ([`../dolls/`](../dolls/README.md)), drawn by `SideScene`, the game's
world scene. The menu starts it (`?play` skips the menu).

## Looking at it

`make dev` and open http://localhost:5173 with the server, or http://localhost:5173/?harness=side
without it: the dev harness (`harness.ts`) dispatches a stand-in snapshot on the side-view maps, a
clock, the murals and paintings from `content/works/`, and moves the residents through every pose by
the protocol, through `server.dispatch`.

| Query | |
|---|---|
| `at=<map>:<x>[:<y>]` | Where the player starts, e.g. `at=coffee_shop_floor_1:9`. |
| `level=` | Which generated level the world plays (`content/street/levels/`), 0 by default. |
| `hour=` and `speed=` | The sim hour to start at, and sim seconds a second (60). |
| `still` | The residents stay where they start. |
| `murals=0` | Leaves the mural walls blank. |
| `panel=0` | Hides the harness's help. |
| `lamp=on` and `charge=` | The player's lamp, off and 0.8 charged by default. L switches it as the server would; nothing drains or charges it. |

Left and right (or A and D) walk, a press of Shift switches between walking and running, and Space
jumps (`jump.ts`, below). E takes the door or street way you're on, whatever else is in reach. It
never climbs, rides or talks: T talks to the ringed resident or orders at a counter, and V looks at
a mural or a painting (`ui/`). Up climbs stairs or a ladder from its foot, and down from its top,
from anywhere in the tile either side of the end (`CLIMB_REACH`, 1.5 tiles from its middle): the
player steps onto it first, and where two are in reach each key takes the nearest its way. Up and
down keep climbing while held, stopping anywhere. On either of the lift's cells, up rides it a floor
up and down a floor down, all the way. Off a door, E uses what's in reach
([`world/reach.ts`](../world/reach.ts)). A door on the cell beside a flight's foot, as in the noodle
bar, is E's and the stairs are up's. A small tag over each way a key takes from where you stand
names the keys and what it does ("E: go out", "↑: upstairs", "↑ ↓: lift", `ways.ts`). The scene
reads its keys through `input.ts`'s `readControls`; a tap of E, up or down shorter than a frame
still counts, and so does a tap of Space. Shift switches running only when it's pressed and let go
on its own (`RunToggle`), so Shift+Tab and ? leave it alone. Clicking a mural looks at it. L
switches the lamp (below). K kicks (below). In the harness, `[` and `]` move the clock an hour and 1
to 6 go to each street, 5 the rooftops and 6 the metro.

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
  paintings, furniture, stairs, ladders, the lift shaft and cars, and the slabs. The front door is
  drawn from inside too, on the back wall over its mat, with a lit EXIT sign. Entering a building
  lifts its front off; the street's props and residents in front of it aren't drawn until it's
  back on, so nothing is ever see-through.
- **Signposts** (`street-view.ts`): a fingerpost at each way to another street names it. The sign and
  the posts are drawn in code (`textures.ts`).
- **Residents and the player** (`side-doll.ts`) are drawn as their painted figures, each step of a
  cycle's frame worked out once and kept (`poses.ts`), and tinted with the light where they are.
- **Light** (`light.ts`): the manifest's four times of day, blended across each change, give a tint
  for each layer's depth (distant layers take some of the sky's colour, the foreground falls
  darker), haze on the far and mid layers, the glow maps added at night and 55% in the evening, and
  lamplit rooms after dark. Under the village (a street with `underground`, and its floors) it's
  always early afternoon's light with the glow maps at 55% (`lightBelow`), whatever the time.
- **Shadows** are made at runtime from each picture's alpha, blurred and offset (`textures.ts`).
- **Blood** (`blood.ts`, drawn by `blood-view.ts`): each hit the player takes (`ui/hurt.ts`'s
  `hurts`) bursts three to six drops from their chest, more and a little bigger the harder the hit
  (`BLOOD`). They fly up and away from what hit them, fall, settle on the ground if they reach it,
  and fade within `LIFE_SECONDS`, lit like the player. What hit them is `attacker.ts`'s
  `attackerOf`: the nearest creature attacking them within `HIT_FROM_TILES` (3 tiles, across rows
  too) on their map, else the nearest there, never one going down. With none, the drops burst
  straight up.
- **Things to pick up** (`piles.ts`): a pulsing glint, drawn in code, over each pile in the last
  `player_state` on the street or its floors, gold for cash: salvage, secrets and what the player
  left, and each thing still to search (`world/searchables.ts`'s `toSearch`), which stops glinting
  once it's searched.
- **What E uses** (`usables.ts`, drawn by `usable-view.ts`): every clue, searchable, jack, news
  terminal and pile on the street or its floors. Searchables, jacks and terminals are the furniture
  the street already draws, and one that no furniture draws is left out. The rest are icons from
  [`content/icons/`](../../../content/icons/README.md): Aris's notes pinned over her bench, out of
  the player's way, the splintered door frame on the maker space's door, a schematic on a searchable
  that teaches a recipe until it's searched, and each pile's first item. A clue without a picture
  of its own isn't drawn. A searched thing gets a painted tick. The one E would use where the player
  stands (`glowing`, as `world/reach.ts`'s `eUse` finds it) gets a pulsing glow round its outline,
  made in code from its picture; a jack doesn't without the datajack, and the lift does with it.

Every texture is filtered smoothly, Phaser's default. A picture wider than the GPU's widest texture
(16384 px on most), such as `sewer_vault` stretched across a level, is cut into parts within it,
drawn side by side, and its shadow is made from the whole (`textures.ts`, `placeParts`). A mural painted at another aspect than its
wall is cropped to cover it, not stretched (`coverCrop`). Each street loads its pictures when the
player first goes there and frees the last street's.

## Darkness and the lamp

Each street's `light` layer says where it's dark (`darkness.ts`, by the server's rule). On a street
with dark stretches, `DarkView` (`dark-view.ts`) draws darkness over them, above everything in the
world: a canvas of four px a cell, scaled up smoothly, so the edges of the dark are soft.

- A dark cell is near black (`DARK`) until the lamp has lit it, and dimmed (`DIM`) from then on
  while the lamp is elsewhere, so places seen are dimmed, not hidden. `Sight` keeps what's been seen
  on each street while the page is open.
- The lamp, held at chest height, lights a circle around the player (`LAMP_RADIUS`, 4.5 tiles),
  fully within its inner `INNER` share and fading to its edge. Below `LOW` (20%) charge it draws in,
  to `FADED` of its radius when flat. A flat lamp gives no light. Without it, a glimmer
  (`GLIMMER`) is just enough to make out the player.
- With the infrared eye fitted and the lamp off, the player sees the dark around them (`EYE`, 5
  tiles) through a red veil, and what it sees is dimmed from then on, as with the lamp. The lamp
  outshines it while it's on.
- L sends `lamp`, switching the lamp the other way (`switchLamp` in `lamp.ts`). The lamp's state is
  the last `player_state`'s, so it lights once the server says so.
- The player charges their lamp by standing on a plug's stand tile, as the server reads it
  (`atPlug`). `plugs.ts` draws a charging point in code at each plug no furniture draws: at home, the
  café and the noodle bar. The metro's is its breaker box.
- The gauge in the corner (`ui/lamp-gauge.ts`) reads `lampHere`, where the scene last drew the
  player: in the dark, or at a plug.

## Movement

The Phaser-free halves are tested under vitest.

- `residents.ts`: residents from `snapshot` and `entity_moved`, walked between positions, climbing on
  a map's stairs or ladder by their cell's kind, and `climbing` or `riding` at a link's end played
  along the link (`runs.ts`'s `crossing`) until the server moves them onto the other floor.
- `player.ts`: the player's walking, running, jumping, doors, climbs and rides, by #311's choices,
  #325's, #330's and #331's: what the keys take is `ways.ts`'s `waysNear` and `chosen`. Walking
  stops at walls, stairs and ladders on a map, which are taken with up or down, and walks off a
  ledge. While crossing between floors the player's position stays at the end they left from, as
  the protocol holds residents.
- Running: a press of Shift turns the walk into a run over `RUN_BLEND_SECONDS`, and another turns it
  back, at up to `runSpeed`, `RUN_PACE` (2) times `PLAYER_SPEED` on their own legs and faster on the
  bionic legs, along streets and floors and through the air. Each press counts once, though Phaser
  hands a frame's earlier key events to its listeners again with each new one (`eachOnce`), so a
  tap of Shift and an arrow in the same frame still switches.
  Stopping, stairs, ladders and the lift leave it on; they go at their own speeds. The figure turns
  from its walk to its run halfway through the blend (`Drawn.run`), and its phase steps by
  `WALK_CYCLE_M` or the longer `RUN_CYCLE_M` a cycle, so the stride lengthens.
- Jumping (`jump.ts`), arcade style, from `content/street/jump.json`, the table the server checks
  positions by. Space jumps from anywhere the player stands, the feet rising `rise` (2.3) tiles in
  `rise_seconds` (0.38) with Space held; letting go early keeps `cut` of the speed up, so a tap
  hops. Coming down, or once let go, gravity is `fall_gravity` (1.3) times stronger, so it's
  snappy. In the air the arrows steer, towards walking or running speed at `AIR_ACCEL`, and
  braking at `AIR_BRAKE` with neither, so a run jump goes about twice as far: a walking jump clears
  two cells, a run three. Walking off a ledge falls, and Space still jumps for `coyote_seconds`
  (0.1); Space pressed up to `buffer_seconds` (0.12) before landing jumps again on landing. The
  player is `foot` (0.25) tiles wide either side and `body` (1.7) tall: their feet stand on a
  ledge's edge, walls stop them, a ceiling bumps their head, and they land on top of whatever is
  solid under them, from any height, with no harm. The figure leaps in its run frame furthest off
  the ground (`dolls/sprite.ts`'s `leap`), placed so its lowest point is on the feet line, and
  lands with a squash over `LANDING_SECONDS`; its shadow stays on the ground under it, fading with
  height. The camera stays at the height the jump left from, following only a fall below it
  (`steady`). Anywhere off a whole row, as a snapshot can leave the player, they fall.
- When the player collapses from hunger, `player_collapsed` puts them at home, as through a door,
  once the street is shown and any door they're going through is done. It's also where the scene
  starts them next (`sideResidents.start`), for a tab that wasn't in the game when they collapsed. After every `snapshot` the
  scene sends the player's position again, so a restarted server knows where they are.
- The jump is the player's own, by the legs and feet fitted (`jumpOf`): `content/street/jump.json`'s
  `kits` say what each grade of either, or one of each, changes, under the same gravity
  (`KIT_TABLES`). The feet rise higher, two rows on the spring feet and two more on their second
  grade; the legs run half as fast again, then twice and two and a half times as fast, and so jump
  further, and kick harder (`kick`, which the server reads for itself). With both, the jump rises as
  the feet do and runs as the legs do. The scene reads
  the body from `player_state` each frame and sets the player's `rise` and `runSpeed`. With the
  datajack fitted, the link from a jack's stand tile, the lift down to the sewers, is a way like any
  other; without, it isn't.
- K kicks (`kick.ts`), standing on the ground: not in the air, on stairs, a ladder or the lift. It
  kicks the way they last walked, turning them to it if they faced up or down, and sends `kick`
  with that `facing`. The server decides what it hits. The figure stands still for `KICK_SECONDS`
  (0.3), drawn in its run cycle's frame with the near leg furthest forward (`KICK_PHASE`), and
  another kick waits until it's done.
- The server keeps every position a jump or a fall sends, and ignores one nobody could be at
  (`simile.street.moves.possible`, `docs/protocol.md`), by the same jump. `server/tests/street/positions.json` is a
  table of the client's sends and places nobody could be that the server's tests and
  `jump.test.ts`'s copy of the rule both check.

## The walk

`walk.e2e.ts` serves the client, opens the harness in Chromium and walks the player by the keys into
every building, out of every exit and along every street door on E, up and down every flight and
ladder on the arrows alone, and a floor up and down on the lift from each of its cells, checking
each prompt on the way. Before each arrow it presses E where nothing else takes it, and checks the
player didn't move. It takes doors and lifts from their cell, and stairs and ladders from 1.4 tiles
off their end, near the edge of the reach. Murals are drawn, so the doors beside them are walked on
E too. Then it runs along the High Street from a press of Shift, checking the speed and the blend,
jumps the rooftops' one-, two- and three-cell gaps, the last running, checking it lands on the far
roof, and the metro's jumps up to its secrets, walks off the clock house's roof into the lane, walks
down into the metro, through it into the clinic and back up to Banyan Row, walks into the metro's
dark west tunnel, lights the lamp with L and walks on to the plug, checking the darkness and the
gauge's hints, checks Aris's notes are drawn in the maker space and glow only while the player
stands by them, searches Aris's bench and checks it's drawn searched, checks a run jump at the
metro's high ledge falls short, lands on the high ledge's
secret on the spring feet and crosses the gantry's gap to its secret on the bionic legs, at the gate
in level 0 of the sewers checks a jump on the player's own legs falls back from the weir, gets onto
it on the spring feet and crosses the high gap on the bionic legs, opens the news at every terminal
on E, orders at the café's counter on T, talks to Lachlan on T, each after E there does nothing, and
looks at house 10's mural and a painting on V and closes them on V, and checks the sewers' vault is
drawn edge to edge in parts on the widest level, with no `texImage2D` error. It steps Playwright's clock
rather than waiting, and the *Side walk* workflow runs it on every PR.

```bash
npx playwright install chromium   # once
node src/side/walk.e2e.ts         # --screens <dir> keeps a screenshot at each prompt, --real-time waits
```

## What it provides

`scenes` exports `SideScene` (key `side-world`), started with `this.scene.start(SIDE_SCENE)`. It
reads the player's start from the snapshot, or the square on the High Street. It registers the
dialogue UI's world view, the audio's positions, the `MuralView` that finds the mural under a click,
and the prompts for the ways the player can take from where they stand, and updates `world/interactables.ts` with the
player's position every frame. The murals and paintings come from `world/murals.ts`'s and
`world/paintings.ts`'s stores, the maps from `world/assets.ts` (`content.ts` reads them into a
`Village`, and puts each map of the level the snapshot names in place of level 0's with
`Village.replace`), and the dialogue scene hands the same `maps` to `ui/side-view.ts`.
