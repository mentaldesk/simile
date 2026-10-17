# Iso world

The village drawn isometric from A2a's pre-rendered scenery (#116). `?renderer=iso` in the URL opts
in: `BootScene` then starts `IsoScene` (`scenes/iso-scene.ts`) instead of `WorldScene`. The map,
collisions, the server and `player_move` are the same; only the drawing changes. Everything in this
folder is Phaser-free and tested under vitest.

[`server/simile/art/iso/README.md`](../../../../server/simile/art/iso/README.md) is the contract for
the manifests, the projection, the depth slices and the ground heights.

## Assets

`assets.ts` globs `content/art/iso/scenery/` and the character sheets in `content/art/iso/characters/`.
Manifests are imported `?url`, images `?no-inline` and `characters.json` as data, so the build emits
each image under `dist/assets/` with a hash and inlines none of them. The scene imports `assets.ts`
itself, once it starts, so the map of their URLs is a lazy chunk and the top-down page loads none of
it. In dev, Vite serves them straight from `content/`.

## Time of day

The sim clock (`SimClock` in `time-of-day.ts`) is the latest time from the snapshot or a `clock`
message, run on at the clock's speed in real time. The scene waits up to `CLOCK_WAIT_MS` for it, then
draws `DEFAULT_HOUR`, the afternoon.

- **Which sets:** `blend(hour)` mirrors `lighting.blend`: one set, or two with smoothstep weights in
  the 60 sim minutes around each boundary, outgoing first. A test checks it against values from
  `lighting.py`, and the spans against every manifest.
- **Loading** (`SetLoader` in `crossfade.ts`): a set is about 4.5 MB of images. Only the sets the
  clock needs now are in memory, plus any whose fade starts within `PRELOAD_SECONDS` of real time,
  up to `MAX_LOOKAHEAD_HOURS` of sim time. A set that's no longer needed is destroyed with its
  textures. Until every set the hour needs has loaded, the scene keeps drawing what it drew, so a
  jump in the clock switches once.
- **Uploads** (`Uploads`): images are decoded off the main thread with `createImageBitmap`, then
  added as textures and placed in the scene `UPLOAD_MS_PER_FRAME` at a time, about 8 frames for a
  set. The set's drop-shadow mask is built then too, rather than on the first frame of its fade.
- **Crossfade:** every set has the same objects and slices, so each slice is drawn once per set, the
  incoming image `PAIR_DEPTH` above the outgoing one, at alpha = weight (`layerAlphas`). The outgoing
  image stays opaque until the last 5% of the weight, so at most 1.25% of the background shows
  through and soft edges end the fade as one image draws them. A cut-away building fades both images
  so that together they're as see-through as one. The two grounds pair the same way.
- **Characters** (`lighting.ts`): each set's tint times the light map's tint at the feet, scaled
  down to keep its hue, then blended by weight. Each set has its own drop shadow (`shadow.ts`), away
  from its sun at its strength times the light map's sun at the feet times its weight, so both show
  mid-fade, each pointing its own way. The contact shadow under the feet doesn't change.

## Drawing

- **Projection** (`projection.ts`): a position `(x, y)` stands at the middle of its tile,
  `(x + 0.5, y + 0.5)`, projected as the manifest's camera does.
- **Ground**: the chunks, under everything.
- **Depth** (`depth.ts`): each object slice is its own crop of the object's image at its own depth,
  and residents sort by the screen y of their feet on the ground plane, in front on a tie.
- **Ground heights** (`ground.ts`): feet on grass are drawn about 10 px up and on a road 4 px down.
  Depth stays on the ground plane.
- **Cutaway** (`cutaway.ts`): a building fades to `CUTAWAY_ALPHA` while it's in front of the player
  where they stand and its silhouette covers them, and back in `CUTAWAY_HOLD_SECONDS` after it stops.
  The ground under it is lit.
- **Camera** (`camera.ts`): it follows the player and keeps the view on the map's diamond, giving way
  at the edges and corners so the player stays within `TARGET_REACH` of the centre.
- **Controls** (`controls.ts`): arrows and WASD are screen directions, turned into grid directions,
  so up is north-west. The player still walks and collides in tiles.
- **Characters**: `IsoCharacters` in `scenes/iso-characters.ts` places, tints and shadows sprites
  from any `CharacterArt`: a `SpriteFrame` (the drawn size, the feet and the head's height) and a
  sprite per character with a `pose` for each step. Picking, bubbles, the cutaway and the lighting
  use only those. `sheetArt` is A2b's sheets: anchored at the feet, facing the sheet direction
  nearest their step on the map (`sheets.ts`), with the walk played faster or slower with how fast
  they move, so the feet don't slide, and the idle when they stop. Other art replaces `sheetArt`
  alone. Shadows are drawn on the ground, under every object.

## Resolution

The renders are drawn at one art pixel per CSS pixel, so a bigger window shows more of the village.
Under `?renderer=iso`, `main.ts` sizes the game to the window in device pixels and shows it at
`1 / devicePixelRatio` (`nativeCanvas` in `canvas.ts`). Phaser's `RESIZE` mode would size it in CSS
pixels, which a 2× screen blows up. The camera's zoom is whole device pixels per art pixel
(`isoZoom`): the pixel ratio rounded, or the canvas width over `MAX_TILES_ACROSS` (20) tiles rounded,
whichever is larger. So a 1× window keeps one art pixel per CSS pixel up to 2880 px wide (30 tiles)
and steps up there, and past 1920 px the view stays 15 to 30 tiles across. Top-down keeps
`main.ts`'s 640 × 360 canvas, scaled in whole steps.

## What it provides

`IsoScene` registers as the dialogue UI's `WorldView` and as audio's position provider.

- **Picking**: `spriteOf(id)` is a resident's sprite box on the canvas (`figureBox` in `screen.ts`,
  after the camera's scroll and zoom), their depth, and whether their frame is opaque at a point.
  `npcAt` in `world/hit.ts` goes front to back by depth and picks the first opaque one there, else
  the first whose box holds the point, so click-to-talk and the debug overlay pick the resident in
  front where sprites overlap. The box is the sprite's frame down to the feet, so the dialogue UI's
  ring sits at the feet.
- **Bubbles**: `bubbleAnchor(id)` is the top centre of that box: the top of the frame, a little above
  the head.
- **Audio**: positions are tiles turned 45° (`screenAligned`), so audio's pan follows left and right
  on screen. Distances don't change, so earshot is still in tiles.
