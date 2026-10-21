# Style study 2: a near-future Shenzhen village (#326)

After playing the side view, the user found the papercraft had taken the village back to the
1950s. This study rebuilds #295's pieces two ways and compares them:

1. **Papercraft with modern references.**
2. **A hand-drawn cartoon** in the spirit of Oxygen Not Included.

The pieces are the same as #295's: a street in parallax layers, a dollhouse interior with
furniture, and paper-doll residents seen from the front, the side and the back, with a walk.

Nothing here changes the game. Every piece is painted, cut out and scaled by the game's own
pipelines, run read-only with this study's references, prompts and front plans:

- **Scenery:** #309's `simile.papercraft.build.Build`, the game's `layout.json` and `EditPainter`.
- **Residents:** #310's `simile.dolls.build.paint`, with its sheets, cut and colour restore.

The scenery keeps the game's manifest keys, so `simile.papercraft.preview` composes High Street and
the coffee shop's dollhouse unchanged, on the real maps. The residents are posed by a Python port of
the client's rig (`client/src/dolls/rig.ts`). FLUX.2 Klein 4B runs through mflux at 8 bits, as the
game's builds do. No picture is painted whole.

## The references

![The references](images/references.jpg)

There are four references for each style: a street, a dollhouse interior, residents, and a shop
with neon signs. Each one is painted from text alone (`references.py`).

- **The period is described outright:** glass towers behind low-rise shops, AC units, balconies
  full of plants, e-bikes, a delivery drone, banyan trees and contemporary clothes.
- **Signs are neon pictograms,** never boards. Asked for "LED sign panels", FLUX wrote
  pseudo-Chinese characters on every one. 14 of the 22 reference paintings were rejected, all but
  one for lettering. A sign is now "a glowing neon pictogram in the window: a coffee cup, a noodle
  bowl or a gear".
- **The residents reference names each skin tone,** from pale to deep brown, since #295's had only
  light skin.
- **The cartoon is described, not named:** "very thick bold dark brown outlines around every shape,
  flat colours with simple soft shading, chunky rounded shapes, slightly exaggerated proportions".
  The street references ask that "everything in the picture" is made that way. The first
  papercraft references had paper trees in front of photographic buildings.

## 1. Papercraft with modern references

![High Street in modern papercraft](images/papercraft-street.jpg)

![Panning along it](images/papercraft-street-parallax.gif)

![The coffee shop as a dollhouse](images/papercraft-dollhouse.jpg)

![The residents](images/papercraft-residents.jpg) ![Walking](images/papercraft-walk.gif)

### Does the period still drift?

**Not with today's prompts and plans. The references alone change almost nothing.**

Below, #309's own prompts (left), the same prompts and seeds with the modern references (middle),
and this study's prompts (right):

![What the references change alone](images/drift.jpg)

With the modern references, #309's prompts still give tiled shophouses with shutters and striped
awnings, picket fences, a velvet sofa on round wooden feet and a carved bed with a patchwork
quilt. The references set the medium and the palette. They add the odd e-bike, but the period
comes from the words. Three places carry it in #309's pipeline:

- **The prompts** (`catalogue.py`, `village.py`): shophouses, shutters, terracotta, velvet,
  brass, patchwork. Here every piece names today's materials instead: glazed tiles, charcoal
  brick, pale oak, white laminate, steel, induction hobs.
- **The front plans** (`fronts.py`). FLUX keeps to the plan, so whatever the plan draws stays:
  cream curtains, sills and lintels, striped awnings, shutters, flower boxes and tiled roofs.
  - Fronts are painted with no style image, so no reference reaches them.
  - `scenery.modernised` draws over #309's plans with today's details: slim dark window frames
    with roller blinds, a plain light band where each awning was, a lit shop window with a neon
    ring for the pictogram, and AC units. Each building gets a flat roof.
  - FLUX turns the ring into the pictogram the prompt names, and keeps the rest.
- **The references,** for the medium and palette.

**What still drifts:**

- **Modern materials don't read as paper.** Steel, white laminate and glass come out as product
  renders rather than card, as the enamel bath did in #295. Wood, fabric and plants still look
  cut.
- **A modern palette is pale.**
  - White and grey walls, glass and pale oak lose the warm contrast of the old village.
  - They also fight the cut-out. On white, the mid layer's white blocks were keyed away, leaving it
    sparse. On grey, their grey glass went instead, leaving a grey smear.
  - The street above uses the white version.
- **The residents barely change.** #310's dolls already wear t-shirts, jeans, caps, headphones
  and backpacks, drawn in code from each `Appearance`. A new residents reference only changes
  their texture.

## 2. The hand-drawn cartoon

![High Street as a cartoon](images/cartoon-street.jpg)

![Panning along it](images/cartoon-street-parallax.gif)

![The coffee shop as a dollhouse](images/cartoon-dollhouse.jpg)

![The residents](images/cartoon-residents.jpg) ![Walking](images/cartoon-walk.gif)

The cartoon uses the same pieces, plans, prompts and seeds as the papercraft. Only the style text,
the references and how things are made ("hand-drawn in the cartoon style" for "made of cut paper
and card") differ.

### How its residents rig

**Cut-out parts, as in #310.** It's the same pipeline and rig. Klei's games also build their
characters from separate drawn parts.

- **The side sheet works unchanged.** All six side sheets kept every piece in place, with
  #310's prompt in cartoon words, and FLUX drew a thick outline on each piece.
- **The front and back sheet needed a new prompt.** With #310's wording, 4 of 6 merged the two
  torsos into a whole character with arms. "Four separate flat pieces of a cartoon cut-out puppet,
  laid apart" kept the torsos apart in all six. Odalys's back head left its outline at both seeds,
  as it did in #310, which took six paintings for her. #310's cut repaints the gap in its region's
  own colour.
- **#310's cut, patching and colour restore work unchanged.**
- **Three additions, all numbers:**
  - An ink outline 0.9 units wide round each piece, drawn when the piece is placed, so overlapping
    joints read as separate parts.
  - Heads 1.22 times bigger, about the neck.
  - Bodies 1.15 times wider, through `Look.width`.
- **The poses and walk are #310's,** angle for angle.
- **The outline shows at the joints.** Where a forearm crosses the torso its outline crosses it
  too, and the painted outline doubles the drawn one along each edge. That's the cut-out look. The
  doubled line could be thinned.

## 3. Side by side

The game today, the modern papercraft and the cartoon, from the same maps and residents:

![High Street](images/compare-street.jpg)

![The coffee shop](images/compare-dollhouse.jpg)

![The residents](images/compare-residents.jpg)

![The walk](images/walk-compare.gif)

At play size, 1:1 (a 900 px window shows 22.5 m, near the client's 19 m view, so a resident is
about 82 px tall):

![At play size](images/compare-play-size.jpg)

### The futuristic feel

**Both read as a contemporary Chinese tech city, and equally so.** The same prompts and plans give
both the glass skyline, mid-rise blocks with solar panels and roof gardens, AC units, tiled
fronts, solar street lamps, a smart kiosk and neon pictograms. Neither looks like science fiction.
"Near-future" here means today's Shenzhen, and more future would come from the prompts in either
style.

- **The cartoon reads the city more clearly.** Its outlines keep the far towers and mid blocks
  crisp. The papercraft's pale card hazes them into the sky.
- **The papercraft is calmer and more muted.** Some will prefer it. With glass and steel, its
  handmade charm thins out.

### Consistency across separately made pieces

| | Game now | Papercraft | Cartoon |
|---|--:|--:|--:|
| Colour distance to its own references (CIE76, lower is closer) | 11.1 | 8.8 | 11.2 |
| Worst piece | 32.7 | 27.3 | 29.0 |
| Fronts painted off the plan (an extra door) | | 0 of 10 units | 3 seeds of 3 |
| Front and back doll sheets painted for the 6 kept | | 6 | 14 |

The colour distances are the mean over the 34 pieces all three have, as #295 measured it
(`compose.py consistency`).

- **Both styles hold together across 40 separate paintings.** Painted from the same prompt
  skeleton and seeds, the two styles even share their layouts piece for piece.
- **The cartoon looks more uniform than its colour numbers say.** One outline weight on everything,
  from towers to cups to residents, ties it together more than any palette. The outlines also make
  its cut-outs cleaner, where the papercraft's pale walls and glass went with the backdrop.
- **Papercraft looks less uniform than its numbers say.** Its palette sits closest to its
  references. But steel and laminate furniture next to paper plants looks like two media.
- **The cartoon strayed from its plans more.**
  - Its café redrew a door into a door-less unit at all three seeds tried. The papercraft café kept
    to the same plan at its first. The study keeps the third seed, whose extra door is the
    narrowest.
  - Its front and back sheets needed the new prompt above.
  - Its plaza paving came out as a thick-outlined slab in perspective, which shows more than the
    papercraft's.

### Walking and rigging

**Both are #310's cut-out rig, unchanged.**

- **Papercraft:** a resident is card pieces at joints, which is what paper dolls are.
- **Cartoon:** the same rig with an outline per piece, bigger heads and wider bodies. Klei's own
  characters are separate drawn parts with outlines too, so it suits the style.

Neither needs new poses. The cartoon needs its outline, which can be baked into the atlas so the
client draws it unchanged, and its two proportions.

### Legibility at play size

**The cartoon is easier to read.** At about 82 px tall, its outlined residents stand clear of the
tiled walls and paving, and so do the café tables, benches and kiosk. The papercraft residents
read, but their edges are soft. The pale furniture of the modern palette blends into pale walls,
and the old village's warm, darker walls gave more contrast. Faces are a few pixels in both.

### Cost

**Seconds a painting are the same.** Both use the same model, sizes, steps and reference images.
Measured on this M2 Max at 8 bits:

| | Papercraft | Cartoon |
|---|--:|--:|
| References, from text (1344 × 768) | 33 s | 30 s |
| Street layers | 31 s | 36 s |
| Room papers and the sky | 25 s | 29 s |
| Front units (about 1.2 MP) | 73 s | 78 s |
| Furniture and platform pieces | 23 s | 25 s |
| Doll sheets (two images, 1024 × 768) | 60 s | 59 s |

A style doesn't change FLUX's work. The cartoon's scenery ran while other work was running on the
Mac, so its 5 to 18% difference is noise. The doll sheets, painted later, match.

- **This study** took 148 paintings and 107 minutes of FLUX, all counted:
  - 22 references, 8 of them kept
  - 40 scenery paintings in each style
  - 10 repainted: six café units, two windows and two mid layers
  - 4 to measure drift
  - 32 doll sheets
  - 22 model loads, 41 s in all
- **A whole village** is what #309 and #310 measured, in either style: about 90 minutes for the
  scenery, with night pictures, and 26 minutes for 12 dolls.
- **Papercraft could keep today's dolls,** since they barely change. The cartoon repaints them.

**What each reuses of #309's and #310's pipelines:**

| | Papercraft, modern | Cartoon |
|---|---|---|
| `Build`: painting, cut-out, scaling, tiling, hashes, manifest | as is | as is |
| `EditPainter` and `cutout.py` | as is | as is |
| `preview.py`, the manifest, the client's scenery | as is | as is |
| `painter.STYLE` and `styled()` | as is | the style becomes a setting |
| `catalogue.py` and `village.py` prompts and looks | rewritten for today | the same rewrite, with the medium's words (`LEAD`, `REDRAW`, `TEXTURE`, `PAPER_CARD`) per style |
| `fronts.py` plans | today's details, as `modernised` draws them | the same |
| `content/papercraft/references/` | four new | four new |
| Dolls: shapes, sheets, cut, patching, restore, rig | as is | as is |
| Dolls: prompt | as is | the cartoon prompt, with "cut-out puppet" for the front and back |
| Dolls: look | as is | an outline baked round each piece in the atlas, bigger heads and wider bodies (numbers in `shapes.py` and `look.BUILD`), and `rimmed()`'s light card edge turned off |
| `content/dolls/` | can stay | repainted |

### Skin

Every resident's skin, hair and clothes match their `Appearance` in both styles, through #310's
colour restore, unchanged.

The painter still drifts before the restore. On each side sheet, the median painted skin is:

| | Game now (#310) | Papercraft | Cartoon |
|---|--:|--:|--:|
| Mean CIEDE2000 from the `Appearance` | 10.6 | 10.6 | 10.3 |
| Mean lightness change (L\*) | +7.8 | +6.8 | +7.5 |

The reference with a range of skin tones didn't reduce the pull.

- Light brown skin (Ingrid, Priya) comes out 15 to 18 L\* lighter in all three.
- Dark brown skin (Henrietta, Kofi) stays within about 3.
- The restore is still needed, and still works (`compose.py skin`).

## Recommendation

**Switch to the hand-drawn cartoon, keeping #309's and #310's pipelines, the maps and the rig.**
[`followup-issue.md`](followup-issue.md) drafts the re-render.

- **The period isn't the style's fault.** It comes from #309's prompts, looks and plans, and
  either style needs the same rewrite to fix it. So the choice is on the other grounds.
- **On those, the cartoon is ahead:**
  - It's easier to read at play size, which matters most in a game.
  - Its outlines keep separately made pieces looking like one world.
  - Its cut-outs are cleaner.
  - It keeps its warmth with glass and steel, where papercraft goes pale.
  - It rigs exactly as the paper dolls do.
- **It costs more:**
  - the residents repainted, about 26 minutes
  - the style made a setting in the painter and catalogue
  - an outline baked into the doll atlases
  - a closer look at fronts for extra doors
- **If the user prefers the papercraft's handmade feel,** the same follow-up works with the modern
  papercraft references instead, and today's dolls can stay. The study shows that fix works for the
  period. It doesn't fix legibility or the pale palette.

**Needs a human's eye:**

- **How Klei-like the cartoon is.** It's cleaner and cosier than Oxygen Not Included, which is
  grungier and more scratchy. Asking for scratchy ink and grime in the references would move it
  that way.
- **The cartoon residents' proportions:** heads 1.22 times bigger and bodies 1.15 times wider.
  Klei's are much bigger-headed.
- **The doubled outline on the residents,** painted and drawn, which could be thinner.
- **Whether the papercraft's muted look** suits the mood better than the cartoon's crispness.
- **The neon pictograms** for each shop.

## What wasn't tested

- **Anything in Phaser.** The streets and dollhouses are composed by #309's `preview.py`, in
  Python. The residents are posed by a Python port of `rig.ts`, so the outline, head scale and
  shadows are Python's, not the client's.
- **Night.** No glow maps were painted. The neon reads by day, and the plan's glow mask would
  need the light bands and pictograms added.
- **A whole village.** One street, four buildings and one interior per style. The other three
  streets and their buildings are estimated from #309.
- **Statistical weight.** Plan adherence and sheet failures are from a few seeds each.
- **Every resident.** Six residents per style, not all eleven and the player.

## Files

| | |
|---|---|
| `common.py` | Paths, the two styles, the period, the GPU check before every load, and FLUX in text mode |
| `references.py` | The eight references. `python references.py [style …]` |
| `scenery.py` | The pieces in a style: #309's `Build` with this study's references, prompts, looks and modernised plans. `python scenery.py <style> [glob …]` |
| `dolls.py` | #310's `paint()` with this study's references and the cartoon prompt, and the Python port of the client's rig. `python dolls.py <style> [who …]` |
| `compose.py` | Every picture and number above. `python compose.py [step …]` |
| `followup-issue.md` | The draft follow-up issue for the switch |

To make it all again, from `server/` with nothing else loaded:

```bash
uv sync --extra images
uv run python ../docs/style-study-2/references.py
uv run python ../docs/style-study-2/scenery.py papercraft
uv run python ../docs/style-study-2/scenery.py cartoon
uv run python ../docs/style-study-2/dolls.py papercraft
uv run python ../docs/style-study-2/dolls.py cartoon
uv run python ../docs/style-study-2/compose.py
```

The scripts read the cached FLUX weights offline and IS-Net from `~/.cache/simile/models/`.
Before every model load, they wait until no mflux process, `simile papercraft` or `simile dolls`
build, or Ollama model is running. Paintings, cut pieces, dolls and full-size pictures go to
`out/`, which is gitignored. The scripts make no LLM calls.

Every painting, rejected ones included, every cut piece and doll atlas, and each picture at full
size are on the orphan branch
[`previews/326-style-study-2`](https://github.com/mentaldesk/simile/tree/previews/326-style-study-2).
