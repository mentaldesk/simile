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
- Before loading FLUX it waits until no other model is on the GPU: mflux, another simile build or
  Ollama.
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
    units without one get windows rather than a shop window, which it boards up. And it fills a
    big blank wall with windows, so the tower's and Garden Flats' prompts ask outright for their
    mural walls to stay empty.
  - Stairs, the ladder, the ledge, the rope bridge, the lift and the white bathroom fittings and
    fridge are redrawn from flat sketches the same way (`sketches.py`), so they fit their cells and
    come out as card.
  - A night picture is an edit of its day front, and a colour variant an edit of its item.
- **Cut out** with IS-Net plus a colour key on the plain backdrop (`cutout.py`). White things are
  painted on grey. Some items also have painted shadow, or backdrop showing between their legs,
  cut away (`cut` in the catalogue). A front is cut on its plan's outline.
- **Scaled** to its height in metres at 120 px/m. Street layers, papers and the sky keep their
  painted size, and are made to tile along x (room papers both ways). A tile is cut where its
  ends look most alike and crossfaded there, with the painting's light falloff levelled across
  it so the join shows no step. The sky is joined only in clear sky, so no cloud is cut.
- **Hashed.** A piece's `hash` covers its prompt, seed, size, style images and the pipeline's
  version. For a front it covers the plan's parameters and `fronts.PLAN` (bump it when a change
  to the drawing should repaint the fronts), and for a sketched piece the sketch's code, rather
  than their pixels, which differ by a pixel between platforms.
  A run repaints and rewrites only the pieces whose hash changed. Paintings are cached by their
  own hash in `~/.cache/simile/papercraft/raw/`, so a change to how pieces are cut re-cuts them
  without repainting on the machine that painted them.

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
| `anchor` | Sprites, fronts and landmarks: the point that stands on the ground at the piece's x, as fractions of the width and height. |
| `surface` | Optional, `ground` pieces: metres down from the strip's top edge to the far edge of the surface people walk on, for a strip painted with a kerb or a wall behind its pavement. Absent means 0. The client draws the strip's top `GROUND_LIFT_M + surface` metres above the street's feet line, so the far edge stays `GROUND_LIFT_M` (0.35 m) above it. |
| `hash` | The hash of its inputs, for the build. |

| Kind | |
|---|---|
| `sprite` | Furniture, street props and platform pieces, with alpha, trimmed to the object, anchored at the bottom middle. Draw a piece in the middle of its cells on the map. |
| `front` | A building's front, with alpha. Its walls are `width` metres wide and `eaves` metres tall, as the map's building is, and `anchor` is the middle of their ground line. Above `eaves` is the roof, for a dollhouse to keep when it lifts the walls off. |
| `glow` | A front's lights at night, RGB on black, the same size and placement as its front. Add it on top: in full at night, 55% in the evening. Only the plan's windows, shop windows, glass door, wall lamp and lanterns glow. |
| `layer` | A city or far street layer, with alpha, solid from its skyline down, tileable along x. |
| `strip` | A mid, near or foreground street layer, with alpha, tileable along x. |
| `ground` | A ground street layer, with alpha, solid from its top edge down, tileable along x. Its top edge, or `surface` below it, is the far edge of the surface people walk on. |
| `paper` | An opaque texture. Room papers tile both ways, and the floor slab and the sky along x. |

### Lookups

- **`streets`**, by street map id: its six layers, back to front, as piece keys. Streets of the
  same kind share layers. A street may also have a seventh, `city`, between `sky` and `far`: the
  city's skyline, a `layer` piece, hazed like the far layer. Streets underground leave it out, and
  a street without one draws no city.
- **`landmarks`** (optional), by name: buildings drawn once per street behind the city layer
  rather than tiled with it, so the far tile's repeats never show one twice. `apex` is the Apex
  towers. Each has:
  - `piece`: the landmark's piece key. Its `anchor`, the middle of its foot, stands on the city
    layer's bottom edge, and its `height` is how tall to draw it in the street's metres, as a
    layer's is. It moves with the city layer, at `parallax.city`, so the skyline hides its foot,
    and takes the city layer's time-of-day tint and haze.
  - `glow`: its lights at night, a `glow` piece the same size and placement as `piece`, added on
    top as a front's glow is: in full at night, 55% in the evening.
  - `at`: by street map id, where along that street it stands, as a fraction of the street map's
    width from its left edge (0 to 1), not counting the ground drawn past either end: the
    landmark's anchor is in the middle of the view when the camera's centre is there, whatever
    `parallax.city` is. A street it leaves out, as it does those underground, has no landmark.
- **`grounds`**: ground strips for stretches that aren't pavement: the square, the park and the
  river's promenade below Banyan Row.
- **`buildings`**, by the id of the map's building: a location id, or for a building that only
  carries a mural, its mural wall's id. Its `street`, `front` and `glow`, and `floors`: the paper
  for each floor's back wall, ground floor first. A mural wall's stretch of the front is left
  blank, from its `bottom` to its `top` in the building's storeys (4.4 m each), up to the eaves.
- **`furniture`**, by the name the maps' `furniture` objects use: its piece, any colour
  variants, and `stretch` for runs like kitchens, counters and workbenches, to draw as wide as
  their cells by repeating their middle and keeping their ends, the rooftops' `rope_bridge` among
  them, its deck on the solid row under it. Also some pieces the maps don't use yet, for dressing
  rooms and streets, and `picture_frame` for the gallery's paintings. A map can use one of those
  extras too, as the rooftops use the palm tree, the bicycle and the bin.

  An entry can also carry measurements of its art, which hold for its variants too. Each is
  optional, and without it the client does as it does today:

  | Field | |
  |---|---|
  | `seat` | Metres from the piece's foot (the bottom edge its `anchor` stands on) up to the top of the seat at its front edge, where a sitting figure rests. The client's `SEAT_M`. |
  | `bed` | Metres from the bed's foot up to the top of its mattress at its front edge, where a figure lies. The client's `BED_M`. |
  | `light` | Metres from the piece's foot up to the middle of the lamp's head, where its light is centred. Any entry with `light` gets a light there, `lamp`, `sewer_lamp` and `floor_lamp` alike. Without it a piece has no light, except the street `lamp`, which falls back to the client's `LAMP_HEAD_M`. |
  | `moulding` | A frame's: `{"left", "right", "top", "bottom"}`, how wide its moulding is on each side in the piece's own px (as `size` counts them), kept as the frame stretches round a painting. The rest is the opening. The client's `MOULDING`. |
- **`platforms`**: `stairs` (one storey, rising to the right: mirror it for a flight to the left),
  `ladder`, `steps` (stone steps rising to the right), `ledge` (stretch it by repeating its
  middle), `lift` (the car), `lift_shaft` (one storey of it, to stack), and an inside `window`
  and `door` for back walls.
- **`slab`**: the corrugated card band for floor slabs and the dollhouse's sides.
- **`parallax`** and **`times`**: what the previews use, as a starting point for part 5.
  `parallax` has the six layers, and `city` is required whenever any street has a city layer. A
  client reading a manifest without it uses 0.1. A time's `tint` multiplies near layers and
  sprites, `sky` the sky, `haze` mixes the far layer that fraction of the way to its colour (the
  mid layer half as much), and `glow` scales the glow maps.

## References

[`references/`](references/) holds the five style references from #295's study (0.75 MB): street,
house, rooftops, furniture and characters. The build reads them from here, never from `docs/`.
[`references/cartoon/`](references/cartoon/) holds #329's revised cartoon references, street and
interior (0.47 MB), for the tunnels.

## The tunnels

The metro under the village (`content/street/README.md`'s *The metro*) is painted in #329's revised
cartoon, kept a little dirty: its layers (`TUNNEL_LAYERS`), the furniture marked `cartoon`, the
clinic's front (its `Look` is `cartoon`) and its room paper (`CARTOON_PAPERS`). Their prompts end in
`painter.CARTOON` rather than the papercraft style, and they're painted from the cartoon references.
The rest of the pipeline is the same, with three additions:

- `near-metro` is a solid tiled wall 4.6 m tall, so it hides the foot of `mid-metro`, which the
  client draws 2.75 m up. It's cut as a `ground` piece, keyed on its top row's colour (`cut`
  `above`), since the wall fills its sides.
- The clinic's `Look` is `whole`: one painting however wide, with no seam where units would meet.
- The metro's catwalks and steps are furniture drawn over the street's own ledges and steps, which
  stay papercraft.

## The sewers

The sewers' levels (`content/street/README.md`'s *The sewers*) are generated, so nothing is
painted per level: every level is composed from one set of pieces in #329's properly grimy
cartoon (`painter.GRIMY`, from the study's `grimy` look, painted from the cartoon references):
the sewers' six layers (`SEWER_LAYERS`) and the furniture marked `grimy`. The pieces that cover the
levels' solid cells are redrawn from sketches, so they fit their cells and their tops are where
the player stands: `sewer_vault` along the top, `sewer_walkway` and `sewer_pipe` over the slabs,
stretched to their length, `sewer_pier` over each wall on a tier, and `sewer_weir` over the gate's
weir. `maintenance_hatch`, `sewer_outfall` and `sewer_lamp` dress the rooms, with the metro's
`breaker_box`, `rubble`, `crates`, `bedroll`, `pipes` and `freight_lift`.

`layout.json` reads every level: they share the map id `sewers`, so its width is the widest
level's.

