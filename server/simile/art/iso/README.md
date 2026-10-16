# Iso art

Pre-rendered isometric art, made in Blender from `content/map/village.tmj` (#116). The map stays
orthogonal: locations, collisions and entries keep their tile coordinates, and only the drawing is
isometric.

```bash
cd server && uv run simile art iso scenery                  # every lighting set, only what changed
cd server && uv run simile art iso scenery --set night --work /tmp/iso   # one set; keep Blender's raw renders
```

Blender is a tool on the machine, not a Python dependency. `blender.py` runs it as a subprocess,
finding it at `$BLENDER`, then `blender` on the `PATH`, then `/Applications/Blender.app`. CI can't
render, so the renders are committed under `content/art/iso/`. The tests check the manifests, the
images they name and the size budget, and the tests that render skip without Blender.

| | |
|---|---|
| `camera.py` | The camera and projection every render shares |
| `lighting.py` | The four lighting sets, the neutral light for characters, the shared look, and `blend(hour)` |
| `blender.py` | Runs a script from `in_blender/` on a JSON job and returns its JSON result |
| `in_blender/` | Runs inside Blender: `common.py` (materials, primitives, render setup, camera, lights), `scenery.py` (the village's models), `lightmap.py` (the light map passes), `render_scenery.py` (a set's scenery job) |
| `town.py` | The map as the renders see it: ground, buildings and props, and what shades what |
| `scenery.py` | `simile art iso scenery`: plans, renders what changed and writes the manifests |
| `post.py` | Glow, ground chunks and the runtime light map |
| `depth.py` | Depth keys and slices |
| `formats.py` | The file format for each kind of asset |

## Projection

Tiles are 96 × 48 px diamonds, 1.1 m a side, seen from the south-east at 30°, so grid north points
up and to the right on screen. A map point `(x, y)` in tiles, `z` metres up, is drawn at screen px

```
sx = (x − y) · 48
sy = (x + y) · 24 − z · 53.44
```

with the corner of tile `(0, 0)` at the origin. Every position in a manifest is in these screen
px or in tiles, and `camera.project` is the reference.

## Lighting sets

| Set | Sim hours | Sun (the moon at night) |
|---|---|---|
| `night` | 21:00–05:00 | 150°, 50° up |
| `morning` | 05:00–11:00 | 105°, 26° up |
| `afternoon` | 11:00–17:00 | 215°, 52° up |
| `evening` | 17:00–21:00 | 248°, 16° up |

The spans, and the 60-minute crossfade centred on each boundary, come from the approved mock-up
(#122, `docs/style-study/README.md`). `lighting.blend(hour)` is the reference for which sets to
draw and with what weights (smoothstep).

## Manifests: `content/art/iso/scenery/<set>.json`

There is one manifest per set, and its images are in `content/art/iso/scenery/<set>/`. Image
paths are relative to the manifest's folder. The renderer (C1c) builds against this.

```jsonc
{
  "format": 1,
  "set": "night",
  "hours": [21, 5],                          // start and end; night wraps past midnight
  "crossfade_minutes": 60,
  "sun": {"azimuth": 150, "elevation": 50},  // degrees; azimuth clockwise from grid north
  "tile": {"width": 96, "height": 48, "metres": 1.1, "px_per_metre_up": 53.443},
  "map": {"width": 64, "height": 42},        // tiles
  "ground": {
    "x": -2040, "y": -24, "width": 5136, "height": 2592,   // screen px
    "heights": {"grass": 0.18, "water": -0.35, "road": -0.08, "crosswalk": -0.08},  // metres
    "hash": "…",
    "chunks": [{"image": "night/ground-0-0.webp", "x": -2040, "y": -24, "width": 1712, "height": 1296}, …]
  },
  "light_map": {
    "image": "night/light.webp", "px_per_tile": 8,
    "width": 512, "height": 336,             // each half: the tint on top, the sun below it
    "sun_y": 336, "scale": 6.057, "hash": "…"
  },
  "objects": [
    {
      "id": "building-28-6",
      "kind": "building",
      "anchor": [36, 11],                    // tiles
      "footprint": [28, 6, 36, 11],          // x0, y0, x1, y1 in tiles
      "image": "night/building-28-6.webp",
      "width": 667, "height": 669,
      "offset": [-419, -665],                // screen px from the anchor to the image's top-left
      "hash": "…",
      "slices": [{"x": 0, "width": 35, "depth": 936.0}, {"x": 35, "width": 48, "depth": 948.0}, …]
    },
    {"id": "tree-8-4", "kind": "tree", "anchor": [9.0, 4.5], "footprint": [9.0, 4.5, 9.0, 4.5], …}
  ]
}
```

**Ground.** The ground has every object's shadow, the lamp pools and the reflections baked in,
but no objects. Draw it under everything. It comes in chunks of at most 2048 px, for GPUs with
small textures: draw each chunk at its `x`, `y`. Outside the map's diamond it's transparent.
Under each building's footprint is the ground as it would be without that building, lit by the
set's light, so a building faded by the cutaway shows the ground rather than a black hole.

**Ground heights.** Grass beds are raised and roads and water sunk. A ground tile whose name in
the map starts with a key of `heights` is that many metres up (negative is down), and any other
tile is at 0. Draw feet standing on it `metres × px_per_metre_up` px higher on screen: about
10 px up on grass and 4 px down on a road. Depth keys stay on the ground plane.

**Objects** are everything that can hide a resident: the 16 buildings and every prop (trees,
palms, lamps, benches, terminals, the fountain, bins, bikes, planters, bollards and café tables),
each with its own image. Draw an object's image with its top-left at `project(anchor) + offset`.
A building's anchor is its front (south-east) corner, and a prop's is where it stands.

**Depth.** Sort everything by the screen y of whatever stands nearest the camera, and residents by
the screen y of their feet, `(x + y) · 24`. One key per object can't get a building right: a
resident just in front of its south wall is nearer the camera than its front corner, but has a
smaller y. So each object comes in `slices`: vertical strips of its image (`x` and `width` within
the image) on the screen's 48 px diagonal grid, each with its own `depth`. That's the screen y of
the footprint's front edge at the far end of the strip, the end further from the camera. Draw each
slice as its own crop of the image at that depth, and a resident in the same strip sorts correctly
against it. Keying by the far end keeps a figure up to 96 px wide, walking along a south or east
wall, from having its leading edge cut off by the next strip. Most props have one slice. On a tie,
draw the resident in front.

**Crossfade.** Every set has the same objects in the same order, with the same `id`, `anchor`,
`footprint`, `width`, `height`, `offset` and `slices`. So an object pairs up across sets by `id`,
and its two images share a silhouette. Mid-fade, draw the incoming image directly above the
outgoing one at the same depth, at alpha = weight, and each incoming ground chunk above the
outgoing one. Don't fade a Layer or Container instead: Phaser 3 applies its alpha to each child,
so what's behind would show through.

**Light map.** This is the light a standing resident gets at each spot, for their tint and drop
shadow, seen from straight above at `px_per_tile` px a tile, with no iso projection. It's one
opaque image in two halves, each `width` × `height`, so nothing depends on alpha (browsers
premultiply it). Sample it at a resident's feet `(x, y)`, at `(u, v) = (x · 8, y · 8)`: it's
already averaged over a resident's footprint.

- **Tint**, the top half at `(u, v)`: RGB × `scale` / 255 is how much more light than in the open
  square a figure gets there, per channel, with gamma 1/2.2 applied. It's 1 in the open, less in
  shade and more under a lamp. Multiply the set's tint by it. Phaser's `setTint` can't go above 1,
  so then scale the result down until no channel passes 1, keeping its hue.
- **Sun**, the bottom half at `(u, v + sun_y)`, grey: any channel / 255 is how much of the sun (the
  moon at night) reaches the spot, 1 in the open and 0 in shadow. Multiply the drop shadow's
  strength by it.

**Hashes.** Each image's `hash` covers what it depends on: the pipeline version, the look, the
lighting set, the camera, the palette, the format and its options, the object, and whatever can
shade or light that object in that set. The ground and light map depend on the whole map. A rebuild
renders only what's missing or whose hash changed, and writes a file only if its bytes changed, so
a rerun with nothing changed writes nothing. `tests/art/iso` fails if the committed manifests are
stale, and pins a digest of the pipeline's code (see below).

## Formats

`formats.py` has one setting for each kind of asset, chosen by measurement in #140:

- **Ground: lossy WebP**, quality 82. Lossless ground would take most of the budget.
- **Sprites: lossless WebP.** For these renders it's about a third smaller than PNG.
- **Light map: lossless WebP**, since it's data. It's about a third smaller than PNG.

`formats.sizes(images)` measures images in each format, so the choice can be remade for another
kind of asset. `content/art/iso/` stays under 20 MB in total, and `tests/art/iso` checks it.

## How it's built

Each lighting set is one Blender run: Cycles at 48 samples, denoised, with the AgX view.

- **Ground:** the whole village, with every object hidden from the camera, so that their shadows
  and reflections still land on the ground. A second pass without the buildings fills in the ground
  under their footprints.
- **Light map:** the same scene from straight above, with all the ground white, in three passes:
  sun and sky, the sun alone, and lamps and lit signs alone.
- **Objects:** each object is rendered in place, with whatever can shade it in that set (anything
  whose shadow, swept away from the sun, reaches it) and every lamp within 12 tiles when lamps are
  lit. All of those stay out of the camera's sight, so an object is lit as it would be in the
  scene: benches by a lamp at night, a tree in a building's evening shadow. A pavement plane under
  each object, also out of sight, bounces light up onto it.
- **Glow:** a halo around neon, lamps and screens, inside each image's silhouette, as in the
  mock-up.

Each set scales the lamps, neon, lit windows, screens and water by its `emit` settings in
`lighting.py`, so the canal and fountain are dimmer at night than by day.

To change how something looks, change it in `in_blender/`, `lighting.py` or `post.py`, then rerun
the command on a Mac with Blender. The hashes see the settings in `lighting.py`, the palette, the
formats and the map, but not code. So `tests/art/iso` pins a digest of the code that decides how
renders look (`SOURCES` in `scenery.py`) and fails when it changes. Then bump `PIPELINE_VERSION`
and rerun if the renders would change, and either way update the pin. A building or prop added to
the map needs only the rerun.
