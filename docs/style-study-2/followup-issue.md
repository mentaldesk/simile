# Draft: the follow-up re-render issue

To be filed once the user picks a style from #326's and #329's study. Nothing below starts until
then. It works for any of the four:

- **papercraft** with the modern references
- **the Klei-like cartoon**, as #329 revised it: scratchier and grimier, bigger heads, one outline
- **pixel art**
- **the flat cartoon**

Fill in `<style>` and keep that style's rows in [What changes per style](#what-changes-per-style).
#329's recommendation is the revised cartoon.

---

**Title:** Side view: re-render the village's scenery and dolls in `<style>`, set today

**Body:**

#326's and #329's studies found that the side view's 1950s look came from #309's prompts, looks
and front plans, not mainly from its references. They compared five styles on the same pieces, and
the user chose `<style>`. The study is in `docs/style-study-2/`, with every piece it painted on
`previews/326-style-study-2` and `previews/329-style-study-3`.

This issue re-renders `content/papercraft/` and `content/dolls/` with #309's and #310's own
pipelines, new references and new prompts.

**It doesn't touch movement or the maps:**

- `content/street/`, `server/simile/street/` and `server/simile/sim/` are unchanged.
- The manifests keep their format, keys and lookups, so the client's scenery and rig draw the new
  pieces as they are. Pixel art keeps them too, but needs the client to draw on its grid: see
  below.
- The client's tests that read the committed manifests (`client/src/side/*.test.ts`,
  `client/src/dolls/`) must pass unchanged.

## Owns

- `server/simile/papercraft/`, except `layout.py` and `preview.py`
- `content/papercraft/`, except `layout.json`
- `server/tests/papercraft/`
- `server/simile/dolls/`, except `routes.py` and `job.py`
- `content/dolls/`
- `server/tests/dolls/`

## Task

1. **References.** Replace `content/papercraft/references/` with four references in `<style>`:
   - a street, a dollhouse interior, residents, and a shop with neon signs
   - start from the study's `references/<style>/`, or repaint them with
     `docs/style-study-2/references.py`
   - name them in `painter.reference()`'s docstring and the build's `refs`
   - **describe the look, never a game or a brand.** The study's `common.py` has each style's
     words.
   - **signs are neon pictograms in windows, never boards,** or FLUX writes pseudo-Chinese
     characters on them. The user likes the pictograms.
   - look at each one, zooming in on every sign, and reject any with lettering. The studies
     rejected most of their first references for it.
2. **The style as a setting.**
   - `painter.STYLE` becomes the style's.
   - The catalogue's medium words become the style's: `LEAD`, `REDRAW`, `TEXTURE`, `PAPER_LEAD`,
     `PAPER_CARD`, and "made of cut paper and card" in `front_prompt` and `night_prompt`.
   - The study's `scenery.leads()`, `TEXTURE` and `SLAB` have the wording.
3. **Today's village in the prompts and looks** (`catalogue.py`, `village.py`). Name contemporary
   materials and things throughout, as the study's `scenery.py` does:
   - layers: a glass skyline behind green hills, mid-rise blocks with solar panels and roof
     gardens, concrete planters with tropical plants, and a footpath with tactile paving and a
     cycle lane
   - furniture: pale oak, white laminate, induction hobs, a screen menu board, a smart kiosk and
     solar street lamps
   - room papers: oak slats, stacked white tiles and plain plaster
   - building looks: tiled, concrete and painted-brick fronts with flat roofs, no shutters, and
     planters
   - **paint pale pieces on a backdrop they don't share,** since white walls on white and grey
     glass on grey both get keyed away. In #329, without a thick outline, the kitchen's cabinets,
     the dining table's top, the plant's pot, the kiosk's screen and the bed's duvet all went with
     a white backdrop, and painted on grey they kept them (the study's `scenery.ON_GREY`). Check
     every piece for holes where it should be solid.
   - **cut each ground strip to its own band,** as fronts are cut on their plans.
     - Make the strip solid from the band's usual top row to its usual bottom one.
     - Trim the sloped ends of a slab painted in perspective.
     - The study's `scenery.banded` does this. Without it, the sky showed through holes in the
       pavement.
     - The cut keeps only what the key found: a strip whose lower band went with its backdrop
       needs painting again. Check every ground strip is opaque to its bottom row.
4. **Today's details in the front plans** (`fronts.py`), as the study's `scenery.modernised`
   draws them:
   - slim dark window frames with roller blinds, instead of curtains, sills and lintels
   - a plain light band in the shop's colour instead of each striped awning
   - a lit shop window with a ring where the neon pictogram goes
   - AC units beside upper windows
   - Add the light bands and pictograms to the plan's glow mask, so the night maps light them.
   - Bump `PLAN`.
   - FLUX sometimes adds doors to door-less units. Check every unit, and reseed or tighten the
     prompt.
5. **Judge the pieces at the client's real size,** from #329's sharpness study:
   - `simile papercraft-preview` draws the street at 40 px/m. The client draws about 95 px/m on a
     retina screen, and #329 found that was what made #295's pictures look sharper. Look at the
     pieces in the client on a retina screen, or with the study's `scaled.py`, which draws
     `preview.py`'s street at twice its pixels without changing it.
   - Keep 8 bits, the painting sizes and WebP q85. bf16 paints no sharper, though it's 20% faster
     for 7 GB more. Fronts at 1.5 times the pixels have finer detail but thinner outlines than
     the rest, for 2.1 times the time.
6. **The dolls** (`server/simile/dolls/`): `paint.prompt` in the style's words, and the style's
   rows below.
   - Keep #310's colour restore. The painter pulls light-brown skin lighter in every style.
   - **Check every colour region of every piece in the atlas, ears included,** against its flat
     colour, as the study's `compose.py match` does. Fill any region still over ΔE 4.5 with its
     flat colour, keeping the painting's light and shade, as the study's `dolls.matched` does:
     under the check's 6, since the lossy WebP atlas moves a small region by up to 2. Add a test
     that every committed doll is within ΔE 6.
   - Check thin details too, on the painted sheet where they're wider: the study's check skips a
     one- or two-pixel stripe.
   - Bump `VERSION`, and reset `REROLLS`.
7. **Repaint and commit** every piece and doll:
   - `simile papercraft`
   - `simile dolls paint --force`
   - `simile papercraft-preview`, then look at every piece

## What changes per style

| | Papercraft | Klei-like cartoon, revised | Pixel art | Flat cartoon |
|---|---|---|---|---|
| References | the study's `papercraft` four | the study's `grimy` four | the study's `pixel` four | the study's `flat` four |
| Medium words (`common.py`) | as #309's, with today's materials | scratchy, uneven ink, smudges, grime and wear, a dirty palette | crisp square pixels of one size, a limited palette, no anti-aliasing | bold flat colours, geometric shapes, no dark outlines, no texture |
| Dolls | can stay as they are | repainted | repainted | repainted |
| Doll prompt (`dolls.SHEETS`) | #310's | "cut-out puppet" for the front and back, with no outline painted round any piece | "pixel art cut-out puppet" | "cut-out puppet in flat illustration", no outlines |
| Outline | none | drawn round each piece, about 0.9 units, its width varying as a worn pen's, and baked into both atlases with the frames and pivots moved to match | none | none |
| Proportions (`shapes.py`, `look.BUILD`) | as they are | heads 1.6 or 1.8 times bigger, the user's pick; the neck joint lowered by as much as the head grows below it; shoulder joints 2 units lower; bodies 1.15 times wider | as they are | as they are |
| `rimmed()`'s card edge | on | off | off | off |
| Colour fallback (`dolls.matched`) | from ΔE 4.5 | from ΔE 4.5 | from ΔE 4.5 | from ΔE 4.5 |
| Pixel grid | | | every piece snapped to 20 art pixels a metre in one shared palette and saved lossless, and each doll piece pixelated by colour region, as the study's `pixel.py` does | |
| Client | unchanged | unchanged | drawn on the grid: see below | unchanged |

### Pixel art in the client

Pixel art is the one style that changes the client. This issue doesn't own the client, so that's
a task of its own, blocked by this one. #329 found that #310's rig survives pixels unchanged if
it's drawn at the art's own size, so the change is in how the side scene draws, not in the rig:

- **Draw at the art's size, then scale by a whole number.** The side scene renders into a target
  of 20 art pixels a metre, with nearest-neighbour filtering and positions rounded to art pixels,
  and that is drawn to the screen at a whole number of screen pixels to an art pixel
  (`camera.ts`). Otherwise the grid shimmers as the camera moves, and pieces don't share it.
- **The rig turns pieces at that size, with nearest-neighbour.** At 41 art pixels tall a limb is 3
  to 4 pixels wide, and #329 found no frame breaks apart, at 41 or at 20 pixels tall. Frame-by-frame
  poses aren't needed, and `rig.ts` is unchanged.
- **The dolls' atlases hold pixelated pieces:** each piece shrunk to 20 px/m by colour region, so
  each art pixel is a shade of its region's flat colour, with the pivots scaled to match.

## Done when

- [ ] `content/papercraft/` and `content/dolls/` are repainted in `<style>`, set today, with the
      same manifest format, keys and lookups.
- [ ] Every piece has been looked at, with none showing lettering or extra doors.
- [ ] Every colour region of every doll, ears included, is within ΔE 6 of its `Appearance`
      colour in the committed atlases, and a test checks it.
- [ ] `make test` and `make lint` pass, the client's included, with nothing under `client/` or
      `content/street/` changed.
- [ ] The PR shows the four streets, the dollhouses and the residents at play size, from
      `simile papercraft-preview` and the client's dolls preview.

**Cost, from #309's, #310's and #329's numbers:** about 90 minutes of FLUX for the scenery with
night pictures, 26 minutes for the twelve dolls, and a look at every painting. Expect to repaint
a few pieces: every style but papercraft added a door to the café, and every #329 style painted
the bookshelf as a cut-away house, at its first seed. Pixel art adds its client task.
