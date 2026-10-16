# Iso world

The village drawn isometric from A2a's pre-rendered scenery (#116). `?renderer=iso` in the URL opts
in: `BootScene` then starts `IsoScene` (`scenes/iso-scene.ts`) instead of `WorldScene`. The map,
collisions, the server and `player_move` are the same; only the drawing changes. Everything in this
folder is Phaser-free and tested under vitest.

[`server/simile/art/iso/README.md`](../../../../server/simile/art/iso/README.md) is the contract for
the manifests, the projection, the depth slices and the ground heights.

## Assets

`assets.ts` globs `content/art/iso/scenery/`. Manifests are imported `?url` and images `?no-inline`,
so the build emits each file under `dist/assets/` with a hash and inlines none of them, and the
bundle holds only their URLs. The scene fetches one manifest and the 115 images it names (about
4.5 MB), so only the set in use is downloaded. In dev, Vite serves them straight from `content/`.

**Which set:** the one whose hours hold the sim time from the snapshot or the latest `clock` message
(`time-of-day.ts`). The scene waits up to `CLOCK_WAIT_MS` for it, then draws the afternoon. The spans
mirror `lighting.py`, and a test checks them against every manifest.

## Drawing

- **Projection** (`projection.ts`): a position `(x, y)` stands at the middle of its tile,
  `(x + 0.5, y + 0.5)`, projected as the manifest's camera does.
- **Ground**: the chunks, under everything.
- **Depth** (`depth.ts`): each object slice is its own crop of the object's image at its own depth,
  and residents sort by the screen y of their feet on the ground plane, in front on a tie.
- **Ground heights** (`ground.ts`): feet on grass are drawn about 10 px up and on a road 4 px down.
  Depth stays on the ground plane.
- **Cutaway** (`cutaway.ts`): a building fades to `CUTAWAY_ALPHA` while it's in front of the player
  where they stand and its silhouette covers them. The ground under it is lit.
- **Camera** (`camera.ts`): it follows the player and keeps the view on the map's diamond, giving way
  at the edges and corners so the player stays within `TARGET_REACH` of the centre.
- **Controls** (`controls.ts`): arrows and WASD are screen directions, turned into grid directions,
  so up is north-west. The player still walks and collides in tiles.
- **Characters**: `scenes/iso-characters.ts` draws today's atlases at 3×, anchored at the feet and
  facing their direction of travel on screen, until A2b's sprites replace them (#144).

Still to come: picking, bubbles and audio positions (#143), so under `?renderer=iso` the dialogue UI
falls back to its own top-down placement and voices play unpositioned. The crossfade, tint and drop
shadow are #144's.
