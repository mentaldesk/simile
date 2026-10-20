# Dolls

The residents' and the player's paper dolls, drawn from each `Appearance` in `content/npcs/` and
the player's look, then painted by FLUX.2 [klein] 4B. The client's rig (`client/src/dolls/`) poses
them. Made from `server/` on Apple Silicon by

```bash
uv sync --extra images
uv run simile dolls paint            # every doll whose Appearance or pipeline changed
uv run simile dolls paint kofi --force --paintings /tmp/dolls   # one again, keeping its paintings
```

Don't edit them by hand. CI never paints; the tests check what's committed.

## Files

For each resident and `player`:

| File | What it is |
|---|---|
| `<id>.json` | The manifest, below. |
| `<id>-flat.webp` | Every piece in its flat colours, lossless: what the client draws at once. |
| `<id>-painted.webp` | The same pieces painted, at the same places in the atlas. |

The two atlases share one frame table, so the painted one replaces the flat one frame for frame.
`content/dolls/` stays under 3 MB (`tests/dolls/test_content.py`).

## The manifest

```json
{
  "id": "odalys",
  "hash": "16dd23efd47c4415",
  "appearance": {"skin": "#e4a672", "hair_style": "curly", "...": "..."},
  "version": 1,
  "unit": 5.0,
  "height": 100.4,
  "flat": "odalys-flat.webp",
  "painted": "odalys-painted.webp",
  "pieces": {
    "torso": {"frame": [0, 0, 110, 252], "pivot": [49.0, 169.0], "joints": {"neck": [53.0, 9.0], "shoulder": [47.0, 29.0], "hip": [49.0, 169.0]}},
    "...": {}
  }
}
```

- **`unit`** is atlas pixels a unit, and **`height`** a standing doll's height in units, sole to
  crown without hair or hats: so a doll is about 500 px tall in its atlas, twice its size on the
  street. The head is about a quarter of that. Against part 3's scenery (120 px/m), draw a doll
  2.04 m tall, a 1.7 m resident 20% over scale as #295's study did: 245 px. Seated, its hips are
  then about 0.45 m up, a chair's or bench's seat.
- **`flat`** and **`painted`** are relative to the manifest. The flat-doll route sends `flat` as a
  data URL and no `painted`.
- **`pieces`**: each piece's `frame` in the atlas (x, y, width, height), its `pivot`, the point it
  turns about, and its `joints`, where its children hang, both from the frame's top-left in pixels.
- **`hash`** is what the doll was painted from: the pipeline's `version`, the `Appearance` and any
  reroll. A doll whose hash no longer matches is painted again; nothing else is.

| Piece | Seen | Pivot | Joints |
|---|---|---|---|
| `head` | from the side, facing right | the neck | |
| `torso` | from the side | the hip | `neck`, `shoulder`, `hip` |
| `head_front`, `torso_front` | from the front (`south`) | the neck, the hips' middle | `neck`, `shoulder_left`, `shoulder_right`, `hip_left`, `hip_right` |
| `head_back`, `torso_back` | from the back (`north`) | as the front | as the front |
| `upper_arm`, `lower_arm` | any side | the shoulder, the elbow | `elbow`; `hand` |
| `upper_leg`, `lower_leg` | any side | the hip, the knee | `knee`; `ankle` |
| `shoe`, `shoe_front` | the side, or front and back | the ankle | |

Left and right in the front and back pieces are the picture's. Hair, hats and glasses are part of
the heads; apron, scarf and backpack are part of the torsos.

## How they're made

`server/simile/dolls/`:

1. **Flat pieces** from the `Appearance` (`shapes.py`): skin exactly, everything else muted a
   little (`colour.muted`: OKLCH chroma over 0.07 kept at 60%), so the loudest colours sit in the
   papercraft world. The accent (cap, scarf, backpack, headphones) and the apron's colour follow
   A1's sprites (`simile.art.characters.Colours`), and the player's look is `PLAYER` there.
2. **Two sheets**, the side pieces and the front and back ones, laid apart in a row on light grey
   (`sheet.py`), and each painted in edit mode with the villagers reference as the style image.
   The prompt names the skin, hair and accessories, or the painter drops them, and not the
   clothes, or it paints the rest of the person.
3. **Cutting**: each piece is cut on its own outline, its colour regions read from the flat piece
   as drawn, before antialiasing. Anything the painter left bare inside it, where it drew the
   piece a little small, or painted as something else in a region, is repainted in that region's
   own colour, keeping the painting's fine texture. The paper texture
   between a third of a unit and two units is strengthened, so it still reads at street size, and
   each colour region is pulled all the way back to its flat colour by its median, so the texture
   stays and something else painted into a region doesn't shift the rest. The pieces are scaled
   to the atlas and laid exactly over the flat ones, with a light cut edge. A front shoe the
   painter dropped takes its paint from the side shoe (`build.DONORS`).

Each painting is cached in `server/data/dolls/paintings/` by everything it was painted from, so
cutting can be retuned without painting again. A painting that comes out off-model gets a reroll in
`build.REROLLS` (`"<id>/<sheet>": n`), which repaints that sheet with another seed. `simile dolls
paint` reports pieces the painter moved, dropped or painted something onto.

## The flat-doll route

`POST /api/dolls/flat` with `{"appearance": {...}, "character": "new_face"}` (`character`
optional, for the accent) returns a manifest with `flat` as a data URL, drawn at once, with no
FLUX. The creator previews any look with it.

## The doll job

`simile.dolls.job.DOLL` is a `jobs` kind, `doll`, shaped like A1's sprite job, which part 9
replaces with it: `{"character": "new_face", "appearance": {...}}` paints that doll and publishes
`<id>.json`, `<id>-flat.webp` and `<id>-painted.webp`, with `{"doll", "flat", "painted"}` URLs
under `/api/jobs/files/doll/`. It needs Apple Silicon and the `images` extra; elsewhere the flat
doll stays. Like the sprite job, it refuses a resident in `content/`, except `player`.
