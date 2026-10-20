# Papercraft scenery

The side-view village's scenery: street layers, building fronts with their night glow, room
papers, furniture and platform pieces. FLUX.2 Klein 4B paints each one in edit mode with the
[references](references/) as style images, and the build cuts it out, scales it and commits it as
WebP. Part 5's scene (#311) draws it, and part 4's dolls (#310) are painted with the same painter.

Don't edit these files by hand. Change `server/simile/papercraft/` and run:

```bash
cd server
uv sync --extra images                              # Apple Silicon only
uv run simile papercraft                            # repaints only what changed
uv run simile papercraft-preview /tmp/papercraft    # contact sheets, streets and dollhouses
```

- `--only 'fronts/*'` limits a run to the keys matching a glob.
- `--dry-run` lists what's stale and what would be painted.
- CI never runs FLUX or IS-Net. `server/tests/papercraft/` checks the committed files against the
  manifest, the catalogue and the maps, and keeps this folder under 12 MB.

## Fitting the maps

[`layout.json`](layout.json) is what the scenery was painted to fit, read from the side-view maps
in `content/street/`: each street's width, each building's front (where it stands, its width,
height, storeys, door and mural walls), each building's rooms, and the largest cells each piece of
furniture takes. `simile papercraft` refreshes it from the maps first, so moving a building or a
door repaints only that front, and a test fails if the maps and `layout.json` disagree.

## How a piece is made

- **Painted** from a prompt naming its materials and colours, in `catalogue.py`.
  - A building's front is redrawn from a flat plan drawn in code (`fronts.py`), with no style
    image. The plan fixes its width, height and storeys, its door, its windows, shop windows,
    lamps and lanterns, and blank walls for murals, so FLUX only adds the papercraft. FLUX keeps
    to a plan one house wide but redraws a wider one as some other building, so a front wider
    than 8.6 m is painted as a terrace of units, each a whole front with its own roof, and put
    back together side by side. FLUX also likes to give every unit a door, so on the café the
    units without one get windows rather than a shop window, which it boards up.
  - Stairs, the ladder, the lift and the white bathroom fittings and fridge are redrawn from flat
    sketches the same way (`sketches.py`), so they fit their cells and come out as card.
  - A night picture is an edit of its day front, and a colour variant an edit of its item.
- **Cut out** with IS-Net plus a colour key on the plain backdrop (`cutout.py`). White things are
  painted on grey. A front is cut on its plan's outline.
- **Scaled** to its height in metres at 120 px/m. Street layers, papers and the sky keep their
  painted size, and are made to tile along x (papers both ways).
- **Hashed.** A piece's `hash` covers its prompt, seed, size, style images, plan or sketch, and the
  pipeline's version. A run repaints and rewrites only the pieces whose hash changed. Paintings
  are cached by their own hash in `~/.cache/simile/papercraft/raw/`, so a change to how pieces
  are cut re-cuts them without repainting on the machine that painted them.

IS-Net's weights (`isnet-general-use.onnx`, 179 MB, rembg's release) download once into
`~/.cache/simile/models/` and are checked against their MD5.

## The manifest

`manifest.json` lists every piece by key, and looks them up by the ids the maps use:

```json
{
  "version": 1,
  "ppm": 120,
  "parallax": {"sky": 0.04, "far": 0.2, "mid": 0.45, "near": 0.85, "ground": 1.0, "foreground": 1.3},
  "times": {"night": {"tint": [0.36, 0.42, 0.66], "sky": [0.2, 0.24, 0.46], "haze": [0.35, 40, 50, 90], "glow": 1.0}},
  "streets": {"high_street": {"sky": "layers/sky", "far": "layers/far-hills", "mid": "...", "near": "...", "ground": "...", "foreground": "..."}},
  "grounds": {"square": "layers/ground-plaza", "park": "layers/ground-park", "riverside": "layers/ground-promenade"},
  "buildings": {"coffee_shop": {"street": "high_street", "front": "fronts/coffee_shop", "glow": "glow/coffee_shop", "floors": ["papers/cafe-panelling", "..."]}},
  "furniture": {"sofa": {"piece": "furniture/sofa", "variants": {"coral": "furniture/sofa-coral"}}, "workbench": {"piece": "furniture/workbench", "stretch": true}},
  "platforms": {"stairs": "platforms/stairs", "ladder": "platforms/ladder", "lift": "platforms/lift", "...": "..."},
  "slab": "papers/slab",
  "pieces": {
    "fronts/coffee_shop": {"file": "fronts/coffee_shop.webp", "size": [2880, 1704], "height": 14.2, "kind": "front", "anchor": [0.5, 0.993], "width": 22.0, "eaves": 12.1, "hash": "..."},
    "furniture/sofa": {"file": "furniture/sofa.webp", "size": [215, 102], "height": 0.85, "kind": "sprite", "anchor": [0.5, 1.0], "hash": "..."}
  }
}
```

### Pieces

| Field | |
|---|---|
| `file` | The WebP, relative to this folder: `<key>.webp`. |
| `size` | Its width and height in px. |
| `height` | How tall the picture is in metres. For sprites and fronts, `size[1] / height` is `ppm`. For layers and papers it's the height to draw them at. |
| `kind` | One of the kinds below. |
| `anchor` | Sprites and fronts: the point that stands on the ground at the piece's x, as fractions of the width and height. |
| `hash` | The hash of its inputs, for the build. |

| Kind | |
|---|---|
| `sprite` | Furniture, street props and platform pieces, with alpha, trimmed to the object, anchored at the bottom middle. Draw a piece in the middle of its cells on the map. |
| `front` | A building's front, with alpha. Its walls are `width` metres wide and `eaves` metres tall, as the map's building is, and `anchor` is the middle of their ground line. Above `eaves` is the roof, for a dollhouse to keep when it lifts the walls off. |
| `glow` | A front's lights at night, RGB on black, the same size and placement as its front. Add it on top: in full at night, 55% in the evening. Only the plan's windows, shop windows, glass door, wall lamp and lanterns glow. |
| `layer` | A far street layer, with alpha, solid from its skyline down, tileable along x. |
| `strip` | A mid, near or foreground street layer, with alpha, tileable along x. |
| `ground` | A ground street layer, with alpha, solid from its top edge down, tileable along x. Its top edge is the surface people walk on. |
| `paper` | An opaque texture. Room papers and the floor slab tile both ways, and the sky along x. |

### Lookups

- **`streets`**, by street map id: its six layers, back to front, as piece keys. Streets of the
  same kind share layers.
- **`grounds`**: ground strips for stretches that aren't pavement: the square, the park and the
  river's promenade below Banyan Row.
- **`buildings`**, by the id of the map's building: a location id, or for a building that only
  carries a mural, its mural wall's id. Its `street`, `front` and `glow`, and `floors`: the paper
  for each floor's back wall, ground floor first. A mural wall's stretch of the front is left
  blank, from its `bottom` to its `top` in the building's storeys (4.4 m each), up to the eaves.
- **`furniture`**, by the name the maps' `furniture` objects use: its piece, any colour
  variants, and `stretch` for runs like counters and workbenches, to draw as wide as their cells
  by repeating their middle and keeping their ends. Also some pieces the maps don't use yet, for
  dressing rooms and streets, and `picture_frame` for the gallery's paintings.
- **`platforms`**: `stairs` (one storey, rising to the right: mirror it for a flight to the left),
  `ladder`, `steps` (stone steps rising to the right), `ledge` (stretch it by repeating its
  middle), `lift` (the car), `lift_shaft` (one storey of it, to stack), and an inside `window`
  and `door` for back walls.
- **`slab`**: the corrugated card band for floor slabs and the dollhouse's sides.
- **`parallax`** and **`times`**: what the previews use, as a starting point for part 5. A time's
  `tint` multiplies near layers and sprites, `sky` the sky, `haze` mixes the far layer that
  fraction of the way to its colour (the mid layer half as much), and `glow` scales the glow
  maps.

## References

[`references/`](references/) holds the five style references from #295's study (0.75 MB): street,
house, rooftops, furniture and characters. The build reads them from here, never from `docs/`.
