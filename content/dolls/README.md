# Dolls

The residents' and the player's figures: each painted whole by FLUX.2 [klein] 4B from their
`Appearance` in `content/npcs/` and the player's look, as #334's approach 1, in the clean style.
The client swaps, flips, bobs and sways the painted frames (`client/src/dolls/`). Made from
`server/` on Apple Silicon by

```bash
uv sync --extra images
uv run simile dolls paint            # every figure whose Appearance or pipeline changed
uv run simile dolls paint kofi --force --paintings /tmp/dolls   # one again, saving its paintings
uv run simile dolls paint player     # the player, and with each combination of bionics
uv run simile dolls seats            # measure every seat again from the atlases, painting nothing
uv run simile dolls add kofi         # paint only the frames kofi's atlas lacks, keeping the rest
```

Don't edit them by hand. CI never paints; the tests check what's committed. Painting waits
while another image model, a `simile papercraft` or `simile dolls` run, or an Ollama model is
using the GPU.

## Files

For each resident, the clinic's doctor, `player`, and the player with each combination of bionics
(`player_feet`, `player_bionic_legs_feet`, `player_bionic_legs_datajack_eye` and so on, below):

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
    "lie": {"frame": [0, 170, 132, 66], "feet": [66.0, 64.0], "bed": [66.0, 64.0]},
    "...": {}
  },
  "poses": {
    "stand": ["stand"],
    "walk": ["stride", "pass", "stride", "pass"],
    "run": ["run", "run_pass", "run", "run_pass"],
    "sit": ["sit"],
    "climb": ["climb"],
    "lie": ["lie"]
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
- **Lying** is on its side, asleep, head to the left and feet to the right, as the bed art's
  headboard is: the client never mirrors it. Its **`bed`** is the middle of its underside, across
  the middle of the frame on its lowest row, which the client puts on the mattress; its `feet` are
  the same point.
- **`poses`**: the frames each pose plays through its cycle. Every frame faces right in
  three-quarter view but the climb, seen from behind, and lying; the client mirrors them to face
  west.
- **`resident`** is `false` for someone who isn't a villager, the clinic's doctor
  (`content/npcs/tunnels/`), so the client never lends her figure to anyone without one of their
  own. It's left out for everyone else.
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
   behind; and lying down asleep, curled up with the knees drawn up, with no bed, pillow or
   blanket, painted in landscape.
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
     (`sprites.scale`), by the width of the head, or for a climb its height;
   - lying, it's longer than 1.8 m from head to toe once scaled (`build.LONG`), so it doesn't
     hang far off the 1.58 m bed.

   What still misses is in `build.MISSES`.
6. **Lying is measured turned head up** (`sprites.upright`): the bands, the face, the scale and
   the bionics' regions all expect an upright figure. It's laid down again for the atlas.
7. **Scaled** so the standing figure is 2.04 m at 80 px/m and every other frame's head is as
   wide (a climb, seen from behind with its hands up, as tall from the top of its head), then
   packed into the atlas (`sprites.py`).

Each painting is cached in `server/data/dolls/paintings/` by everything it was painted from, so
cutting and matching can be retuned without painting again. A painting that comes out off-model
gets a reroll in `build.REROLLS` (`"<id>/<frame>": n`), which repaints that frame with another seed.

**The residents' paintings are gone.** Their lying frames were added by `simile dolls add`
(`build.add_frames`): each is an edit of the resident's committed standing frame, upscaled onto
FLUX's grey, and goes on a shelf below the atlas, which is saved again losslessly so every other
frame keeps its pixels. To reroll one, put back their files from before and `add` again;
`simile dolls paint` would paint them again whole, and so would changing their `Appearance`.

## The player with bionics

Fifteen more figures, one for each combination of the lower body (the bionic legs, the spring
feet, or both), the datajack and the infrared eye (`server/simile/dolls/bionics.py`), with the
player's frames and poses. Every grade of a line looks alike (`bionics.shown`). The power cell is
inside, under the t-shirt, so it doesn't show. Their manifests say what's `fitted`, and their
`hash` is the whole player's with each layer's prompts and rerolls, and `bionics.VERSION`.

1. **Each layer is painted once on every frame that shows it** (`bionics.LAYERS`), as an edit of
   the whole player's same frame: 39 paintings. The bionic legs with the feet are one layer, the
   feet painted over the bionic legs' painting. The eye isn't seen from behind, so no climb has
   it.
   - The bionic legs are rounded steel-grey armour plates below shorts, with black knee joints,
     in the same sneakers.
   - The spring feet are steel foot plates on yellow coil springs, in place of the sneakers. Over
     the bionic legs, FLUX coils the springs up the shins.
   - The datajack is a chrome port with a green light. FLUX paints it on a band round the neck
     however it's asked not to, so that's how it looks, the same in every frame.
   - The eye is a red lens in a chrome rim.
2. **Each part is checked as the residents' poses are,** against the whole player's standing
   figure, and painted again if it doesn't show (`bionics.missing`):
   - steel over 12% of the legs, which the grey shading of the whole player's sneakers stays
     under (about 6%);
   - the springs' yellow over 0.6% of the legs, which the whole player has none of, while the
     feet alone are 0.7 to 4% in the atlas;
   - the green light;
   - one red lens, not two, no wider than 17% of the head, as the walk's lenses are (about
     15%), so it doesn't grow when the player stops.

   The face check spares the lens and its rim (`bionics.spared`). A frame may show the parts'
   steel, red, green and yellow (`bionics.PALETTE`) without their counting as strays. With either
   legs, the standing colour check looks for the bottom colour in the shorts (`bionics.SHORTS`),
   and with the feet it doesn't look for the shoes (`bionics.hides`).
3. **Laid over the whole player** (`bionics.changed`, `bionics.laid`): each layer is what its edit
   changed of the whole player's frame, near the part, or below the waist for the lower body
   (anything else FLUX redrew, a backpack a shade lighter, is left out), grown by its outline and
   feathered. Each combination is the whole
   player's frames with its parts laid over them, so the player is the same in every combination
   but for the parts, and each part is the same in every combination it's in.
4. **Scaled as the whole player is** (`sprites.frames`' `reference`), so fitting a part doesn't
   change the player's size.

The eye is painted where it shows, nearer the ear, whichever socket the sim fits it in. Both eyes
show in three-quarter view, and the client mirrors a figure to face west, so the eye swaps sockets
as the player turns, as every figure's hair parting and leading leg do. Painting the far socket
too would take another painting of the eye on every frame, and would show it as a red speck by the
nose whenever the player faced away from it.

## The flat-doll route

`POST /api/dolls/flat` with `{"appearance": {...}, "character": "new_face"}` (`character`
optional, for the accent) returns #310's flat paper doll for any look, with `flat` as a data URL,
drawn at once, with no FLUX. The creator shows it while a figure is painted.

## The doll job

`simile.dolls.job.DOLL` is a `jobs` kind, `doll`: `{"character": "new_face", "appearance":
{...}}` paints that figure and publishes `<id>.json` and `<id>.webp`, with `{"doll", "painted"}`
URLs under `/api/jobs/files/doll/`. It needs Apple Silicon and the `images` extra; elsewhere the
flat doll stays. It refuses a resident in `content/`, except `player`.
