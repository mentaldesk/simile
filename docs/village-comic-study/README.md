# A comic style study for the village (#554)

The gate before the village's comic re-render (#549): the village's pieces painted in two comic
line treatments, from two reference sets, with the city and the Apex towers behind it, and composed
at the client's retina size with the real figures from `content/dolls/`. Nothing here changes the
game.

- **Line A, smooth:** the figures' own words (`simile.dolls.figure.LOOK`): smooth, even dark brown
  ink outlines of one steady weight, and clean surfaces with no smudges, stains or grime.
- **Line B, scratchy:** the tunnels' words (`simile.papercraft.painter.CARTOON`) without their dirt:
  thick scratchy, uneven, slightly broken ink, with "a little worn and dirty with a few smudges,
  scuffs and stains, a slightly muted palette" taken out. No clean words are added.

Every piece is painted, cut and scaled by #309's `Build`, as #329's study did, with #329's
`modernised` front plans, banded ground cut and today's subjects. The paintings go to the game's
own cache, `~/.cache/simile/papercraft/raw/`, so a piece the repaint keeps word for word is free.
FLUX.2 Klein 4B runs at 8 bits, as the game's builds do.

**Contents:** [the line](#the-line) · [the references](#the-references) ·
[the city and the Apex](#the-city-and-the-apex) · [the grime ladder](#the-grime-ladder) ·
[the pieces](#the-pieces) · [what the repaint has to fix](#what-the-repaint-has-to-fix) ·
[the numbers](#the-numbers) · [decisions](#decisions) · [files](#files)

## The line

High Street by day and at night, and the Rooftops, each 27 m wide at 95 px/m (the client draws
19 m of view on an 1800 px tall retina canvas). The residents stand, and sit on the benches where
the map's seat spots are, at the client's `SEAT_M`.

![High Street, A, day](images/a-new-high-street-day.jpg)
![High Street, B, day](images/b-new-high-street-day.jpg)
![High Street, A, night](images/a-new-high-street-night.jpg)
![High Street, B, night](images/b-new-high-street-night.jpg)

The Rooftops' own buildings weren't in the study, so `house_1` stands in for the print works, the
tea house and the laundry, and a bench and two plants are added to the ground:
[A by day](images/a-new-rooftops-day.jpg), [B by day](images/b-new-rooftops-day.jpg),
[A at night](images/a-new-rooftops-night.jpg), [B at night](images/b-new-rooftops-night.jpg).

The coffee shop as a dollhouse, one paper on every floor, with residents on the stools and at the
cafe tables, and one asleep in bed at `BED_M`:

![The coffee shop, A](images/a-new-dollhouse.jpg)
![The coffee shop, B](images/b-new-dollhouse.jpg)

Each seat and the bed, the game's pieces now and each line's, with the residents where the client
puts them. The red mark is the client's `SEAT_M` or `BED_M`:

![Seats and the bed](images/poses.jpg)

- **Both lines come out clean.** B kept no grime with its dirt words gone: no smudges, stains or
  drips, and its palette is as bright as A's.
- **They differ in the line only.** A's outlines are even and match the figures' exactly. B's
  sketchy double strokes read at play size, on fronts and clouds most; next to the figures'
  smooth line, B's scenery looks drawn by a different hand.
- **A's clean scenery leaves the most room for the grime ladder**: the metro's scratchy, dirty
  line is a step down from it, not a sideways move.

## The references

Two sets, each the scenes the pieces take as style images, a street and an interior:

![#326's clean cartoon, and the new ones for each line](images/references.jpg)

- **#326's clean cartoon** (`docs/style-study-2/references/cartoon/`), shared by both lines.
  `signage.jpg` isn't used: no piece takes it, since fronts are painted from their plans alone.
- **New ones,** painted from text in each line's words with #329's scenes (`references.py`). 11 of
  18 were rejected for lettering: prints on hoodies, a blade sign, glyphs on a sign band, a
  machine's display and buttons, and shop signs behind the dollhouse. After the first seven, the
  prompts ask for plain clothes, no blade signs, nothing behind the dollhouse but sky, towers and
  trees, and machines with nothing written on them. Line A's street took six seeds.

  ![The rejected candidates](images/references-rejected.jpg)

- **The village doesn't use `content/papercraft/references/cartoon/`,** the tunnels' grimy ones.
  Only the dirty metro entrance below does, on purpose.

**The references change little.** The same sky, city, layers and furniture from each set, then
High Street with them:

![Pieces from each set](images/compare-references.jpg)
![High Street from each set](images/compare-references-street.jpg)

The line words decide the line; the references mostly decide how solid the mid layer comes out,
which varies as much from seed to seed.

## The city and the Apex

**The city** is a tiled strip (`layers/city`), drawn here 8 m tall with its bottom 4 m above the
feet line, at parallax 0.1, between the sky and the mid layer, hazed towards each time's haze
colour by the time's own amount plus 0.35. At night its lit windows are drawn in code: a sparse
grid inside the towers. Three hazes:

![City haze 0.15, 0.35 and 0.55](images/haze.jpg)

**The Apex** is one landmark per street, drawn from a code plan (`apex.py`) and redrawn by FLUX,
then hazed at 0.6 times the city's extra haze. Its night glow is drawn from the plan in code, on
the painting's own light and shade: cool window bands, a lit crown and a red beacon on each spire.
Three silhouettes, by day and at night:

![The Apex by day](images/apex-day.jpg)
![The Apex at night](images/apex-night.jpg)

Four placements of the twin. At parallax 0.1 it moves 5 m across the screen over the whole of
High Street, so it's in view from everywhere on the street, and a placement is mostly where on
screen it sits:

![Four placements](images/apex-places.jpg)

The city strip painted one tall spired tower in every set, which competes with the Apex
(placement 3 shows it). P74 should ask for a skyline with no spires.

## The grime ladder

The village, then the game's metro and sewers as committed, each 16 m wide at 95 px/m:

![The grime ladder, A](images/a-new-grime-ladder.jpg)
![The grime ladder, B](images/b-new-grime-ladder.jpg)

- **The ladder holds:** clean → a little dirty → grimy.
- **The papercraft platforms don't.** The tunnels' ladders, the metro's steps and its ledges are
  the street's papercraft ones, and the wooden ladder in the metro and the sewers is the one piece
  that reads as another game.

**Banyan Row's metro entrance,** clean in each line, and a little dirty in the metro's own words and
references:

![The metro entrance](images/metro-entrance.jpg)

## The pieces

Each line's fronts by day and at night, furniture and platforms, and layers and papers. The night
pictures are the game's: tinted by the night's tint, with the glow map added.

| | A, smooth | B, scratchy |
|---|---|---|
| Fronts | [fronts](images/a-new-fronts.jpg) | [fronts](images/b-new-fronts.jpg) |
| Furniture and platforms | [furniture](images/a-new-furniture.jpg) | [furniture](images/b-new-furniture.jpg) |
| Layers and papers | [layers](images/a-new-layers.jpg) | [layers](images/b-new-layers.jpg) |

- **Fronts:** `house_1`, `coffee_shop` and `maker_space`, each with a #329-style modern look,
  painted a unit at a time on #329's `modernised` plans. The light bands over the shop windows are
  added to the plans' glow masks, so the night maps light them.
- **Interior:** `plaster-cream` and the slab.
- **Furniture:** sofa, kitchen, bed, wardrobe, table, stool, cafe_table, bench, plant,
  picture_frame and the metro entrance, and the stairs, window and door. #329's subjects where it
  had them; the stool, picture frame, door and metro entrance are new, and the bench has a
  backrest so its seat stays at the game's height.
- **Street:** the sky, `mid-shophouses`, `ground-street` and the city. `near-walls` was added,
  though the issue didn't ask for it: without it, sky shows under the mid layer, which the client
  draws 2.75 m up.

## What the repaint has to fix

- **The bed is 2.2 m wide**, not the client's 1.57 m. A "low modern bed" 1.05 m tall comes out
  long and flat. P73 should ask for a taller headboard, or a shorter bed. The mattress is at
  about `BED_M` in both lines.
- **The seats are close to `SEAT_M`** in both lines, by eye: the stool and the bench fit, and the
  new cafe chairs are a little lower than the old ones. P69 moves the heights into the manifest;
  measure them there.
- **The window is narrower** (0.9–1.1 m against 1.48 m): a single-pane window with a roller
  blind.
- **The coffee shop's first unit got a door** in both lines, as every #329 style did. P72 should
  reseed or tighten its prompt. Its three units also differ a little in tile shade.
- **The stretched kitchen repeats its sink and hob,** as the game's does; P73 could paint its
  middle as plain cupboards.
- **White and pale pieces need a grey backdrop:** the kitchen's cupboards and the mid layer's pale
  blocks went with the white one, in every set, and were painted again on grey. B's mid layer is
  still washed out in its middle.
- **Not in the study:** the Rooftops' and the other streets' buildings, the far layers, the
  foreground, the lamp, the other furniture and room papers, and anything drawn by the client
  rather than Python.

## The numbers

Measured on this Mac at 8 bits (`compose.py numbers`, from `out/timings.jsonl`):

| | Paintings | Mean seconds | Minutes |
|---|--:|--:|--:|
| References, from text | 18 | 33 | 9.9 |
| Fronts, a unit each | 14 | 70 | 16.4 |
| Night pictures, a unit each | 14 | 44 | 10.2 |
| Apex | 6 | 55 | 5.5 |
| Layers | 23 | 36 | 13.8 |
| Furniture | 35 | 21 | 12.5 |
| Platforms | 6 | 28 | 2.8 |
| Papers | 4 | 18 | 1.2 |
| **All** | **120** | | **72.3** |

Plus 13 model loads, each a few seconds from the cached weights: about 73 minutes of FLUX in all,
against the issue's 45, for twice its paintings (the second reference set, the new references and
their rejects, and the night pictures painted a unit at a time). No LLM calls.

| | Painted | Kept | Seconds | Rejected |
|---|--:|--:|--:|--:|
| References | 18 | 4 | 3 good but not needed | 11, all for lettering |
| Line A, new references | 41 | 38 | | 3: kitchen and mid layer (white parts lost), then the near layer added |
| Line B, new references | 40 | 37 | | 3: the same |
| Line A, #326 references | 11 | 8 | | 3: kitchen, mid layer, and the mid layer again (a white band of sky kept) |
| Line B, #326 references | 10 | 8 | | 2: kitchen and mid layer |

The near layers are counted as kept; the coffee shop's extra door is kept and reported above.

## Decisions

The user's, with this study's recommendation:

| Decision | Recommendation |
|---|---|
| **The line** | **A, smooth.** It's the figures' own line, so residents and scenery look drawn by one hand, and the village stays a clear step above the metro's scratchy dirt. B is clean too, but its sketchy strokes look like a different artist next to the figures. |
| **The reference set** | **The new ones, line A's.** They're drawn in the line's own words and checked for lettering. #326's give nearly the same pieces, so it's a weak preference: either works. |
| **The clean words** | **Keep them**, word for word as `figure.LOOK`. B came out clean without them, so they aren't strictly needed, but they cost nothing and keep the village and the figures on one prompt. |
| **The Apex silhouette** | **The twin**: two tapering spires and a sky-bridge read as one landmark at a distance, by day and lit at night. The helix is the most "biotech" but thin at play size; the trio reads as ordinary towers. |
| **The Apex placement** | **1, over the square** (about 60% across, 0.8 scale, bottom 4 m up): always in view on High Street's open stretch, never hidden behind a three-storey front. 2 overpowers the street; 4 hides it. |
| **The city's haze** | **0.35** over the time's own: the city sits behind the village without competing, and the Apex, hazed less, stands out from it. |
| **Today's period** | **Keep today**, as painted: glass, solar panels, AC units and neon pictograms. The Apex and the city carry the future. |
| **The tunnels' own ladders, steps and ledges** | **Yes, do P75.** The papercraft wooden ladder is the one piece in the metro and sewers that reads as another game. |
| **The metro entrance on Banyan Row** | **Clean, like the street,** in the chosen line. The dirty one is a nice hint of what's below, but on a clean street in daylight it reads as a dirty piece of the village rather than as the metro's door. |

## Files

| | |
|---|---|
| `study.py` | Paths, the two lines, the reference sets, the GPU check and the timing log |
| `references.py` | The new references, with the seeds kept and rejected. `python references.py [line/scene=seed …]`, then `keep` |
| `pieces.py` | The pieces: #309's `Build` with #329's modernised plans and subjects, in one line from one set. `python pieces.py <line> <refs> [glob …]` |
| `apex.py` | The Apex's three plans and their night lights |
| `compose.py` | Every picture and the numbers. `python compose.py [step …]` |

To make it all again, from `server/` on Apple Silicon:

```bash
uv sync --extra images
uv run python ../docs/village-comic-study/references.py "simile papercraft"
uv run python ../docs/village-comic-study/references.py keep
for set in "a new" "b new" "a 326" "b 326"; do
  uv run python ../docs/village-comic-study/pieces.py $set "simile papercraft"
done
uv run python ../docs/village-comic-study/compose.py
```

`"simile papercraft"` on the command line is ignored by the scripts. It's there so the other
builds' GPU checks (`simile.dolls.flux.busy`, `simile.icons`) see a painting run and wait for it.
The scripts wait in turn, before every model load, until no mflux process, simile painting build
or Ollama model is running. Cut pieces go to `out/`, which is gitignored; the paintings stay in
the game's cache.
