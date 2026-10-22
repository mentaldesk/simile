# Dolls

The residents' and the player's figures: each painted whole by FLUX.2 [klein] 4B from their
`Appearance` in `content/npcs/` and the player's look, as #334's approach 1, in the clean style.
The client swaps, flips, bobs and sways the painted frames (`client/src/dolls/`). Made from
`server/` on Apple Silicon by

```bash
uv sync --extra images
uv run simile dolls paint            # every figure whose Appearance or pipeline changed
uv run simile dolls paint kofi --force --paintings /tmp/dolls   # one again, saving its paintings
uv run simile dolls seats            # measure every seat again from the atlases, painting nothing
```

Don't edit them by hand. CI never paints; the tests check what's committed.

## Files

For each resident and `player`:

| File | What it is |
|---|---|
| `<id>.json` | The manifest, below. |
| `<id>.webp` | Every frame, cut out, in one atlas: WebP at quality 85. |

`content/dolls/` stays under 3 MB (`tests/dolls/test_content.py`).

## The manifest

```json
{
  "id": "odalys",
  "hash": "0b6afdf24ae9a3ca",
  "appearance": {"skin": "#e4a672", "hair_style": "curly", "...": "..."},
  "version": 3,
  "ppm": 80,
  "height": 163.2,
  "painted": "odalys.webp",
  "frames": {
    "stand": {"frame": [0, 0, 74, 168], "feet": [37.5, 166.0]},
    "run": {"frame": [76, 0, 88, 142], "feet": [44.0, 158.6]},
    "sit": {"frame": [166, 0, 80, 148], "feet": [36.5, 146.0], "seat": [36.5, 118.0]},
    "...": {}
  },
  "poses": {
    "stand": ["stand"],
    "walk": ["stride", "pass", "stride", "pass"],
    "run": ["run", "run_pass", "run", "run_pass"],
    "sit": ["sit"],
    "climb": ["climb"]
  }
}
```

- **`ppm`** is atlas pixels a metre, a retina screen's at play size (#329), and **`height`** a
  standing figure's height in atlas pixels, sole to crown: 2.04 m, the street's resident.
- **`frames`**: each painting's place in the atlas (x, y, width, height) and its **`feet`**: the
  ground under the middle of its head, from the frame's top-left. The client puts that point
  where the resident stands, so the head doesn't jump as the legs change. The run's frame in the
  air has its feet below the frame, so its head is as high as the other run frame's. Sitting has
  a **`seat`** too, the bottom of its thighs, which the client puts on the seat: the lowest row
  behind its calves, found by following its lower edge back from its heels up the backs of its
  calves, however far its shins slant.
- **`poses`**: the frames each pose plays through its cycle. Every frame faces right in
  three-quarter view but the climb, seen from behind; the client mirrors them to face west.
- **`hash`** is what the figure was painted from: the pipeline's `version`, the `Appearance`, who
  they are (age, and a man or a woman, from their voice) and any reroll. A figure whose hash no
  longer matches is painted again; nothing else is.

## How they're made

`server/simile/dolls/`:

1. **Standing, from text** (`figure.py`, `words.py`): a full-body figure in three-quarter view
   facing right on light grey, with a very big round head, a clean face, and their age, skin,
   hair, accessories, clothes and build, each colour named precisely: FLUX follows a colour's
   name, not its hex code.
2. **Every other pose is an edit of that painting:** a stride; a passing step, painted over a
   rough drawing of its legs (`legs_guide`, which leaves an apron over them as it was), since FLUX
   draws a stride whenever a passing step is asked for in words; a run; a second running frame,
   an edit of the passing step with the arms pumping; sitting in mid-air; and climbing, seen from
   behind.
3. **Cut out** with #309's IS-Net and key, without the shadow FLUX paints on the floor, keeping
   pale hair the key would take for the background wherever the outline encloses it, and opaque
   everywhere but its antialiased edge and real gaps (`sprites.cut_out`).
4. **Colours** (`measure.py`): a whole painting has no map of its regions.
   - **Standing,** each of the `Appearance`'s colours is found in the middle of its band (the
     crown, the face, the chest, the shins, the shoes): of the main colours there, the biggest
     of those nearly as near the colour asked for as the nearest. Hair a cap hides isn't looked
     for, or the face would be taken for it.
   - **Every other pose follows the standing figure:** each garment is what's painted near its
     colour as the standing figure was painted, so a shirt FLUX paints nearer the trousers' colour
     than the shirt's is still the shirt, and every pose moves it the same way.
   - Each is moved to the colour asked for, shading and all. The figure's other main colours, a
     backpack's or an apron's, stay put.
5. **Checks.** A frame is painted again with another seed, a few times at most (`build.TRIES`),
   and the best kept, if:
   - a colour still misses by more than ΔE 6 once matched, or the standing figure painted it
     another colour altogether (ΔE 20);
   - a pose loses one of the standing figure's colours, or is painted over 5% in colours the
     standing figure hasn't got, over ΔE 12 from all of its (`measure.strays`);
   - its face is painted over (`measure.face_marks`): more than 5% of the front of the face in
     patches more than ΔE 16 from the skin that aren't ink, eyes or brows;
   - it's drawn more than a quarter bigger or smaller than the standing figure
     (`sprites.scale`), by the width of the head, or for a climb its height.

   What still misses is in `build.MISSES`.
6. **Scaled** so the standing figure is 2.04 m at 80 px/m and every other frame's head is as
   wide (a climb, seen from behind with its hands up, as tall from the top of its head), then
   packed into the atlas (`sprites.py`).

Each painting is cached in `server/data/dolls/paintings/` by everything it was painted from, so
cutting and matching can be retuned without painting again. A painting that comes out off-model
gets a reroll in `build.REROLLS` (`"<id>/<frame>": n`), which repaints that frame with another seed.

## The flat-doll route

`POST /api/dolls/flat` with `{"appearance": {...}, "character": "new_face"}` (`character`
optional, for the accent) returns #310's flat paper doll for any look, with `flat` as a data URL,
drawn at once, with no FLUX. The creator shows it while a figure is painted.

## The doll job

`simile.dolls.job.DOLL` is a `jobs` kind, `doll`: `{"character": "new_face", "appearance":
{...}}` paints that figure and publishes `<id>.json` and `<id>.webp`, with `{"doll", "painted"}`
URLs under `/api/jobs/files/doll/`. It needs Apple Silicon and the `images` extra; elsewhere the
flat doll stays. It refuses a resident in `content/`, except `player`.
