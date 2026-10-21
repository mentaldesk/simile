# Draft: the follow-up re-render issue

To be filed only if the user picks the switch #326 recommends. Nothing below starts until then. If
the user keeps papercraft, the same issue works with the modern papercraft references and prompts,
and without parts 2 and 5.

---

**Title:** Side view: re-render the village's scenery and dolls as a hand-drawn cartoon, set today

**Body:**

#326's study found that the side view's 1950s look came from #309's prompts, looks and front plans,
not mainly from its references. It recommends switching the art to a hand-drawn cartoon at the
same time: thick dark outlines, flat colours with soft shading, and chunky shapes. Its study is in
`docs/style-study-2/`, with every piece it painted on `previews/326-style-study-2`.

This issue re-renders `content/papercraft/` and `content/dolls/` with #309's and #310's own
pipelines, new references and new prompts.

**It doesn't touch movement, the maps or the client:**

- `content/street/`, `server/simile/street/`, `server/simile/sim/` and `client/` are unchanged.
- The manifests keep their format, keys and lookups, so the client's scenery and rig draw the new
  pieces as they are.
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

1. **References.** Replace `content/papercraft/references/` with four cartoon references:
   - a street, a dollhouse interior, residents, and a shop with neon signs
   - start from #326's `references/cartoon/`, or repaint them from `docs/style-study-2/references.py`
   - name them in `painter.reference()`'s docstring and the build's `refs`
   - **describe the look, never the game:** "very thick bold dark brown outlines around every shape,
     flat colour fills with simple soft shading, chunky rounded simplified shapes, bold readable
     silhouettes, slightly exaggerated proportions"
   - **signs are neon pictograms in windows, never boards,** or FLUX writes pseudo-Chinese
     characters on them
   - **for a grittier, more Klei-like look,** ask for scratchy ink and grime here, if the user wants
     it
   - look at each one, zooming in on small signs, and reject any with lettering, as #326 did
     for 18 of 26
2. **The style as a setting.**
   - `painter.STYLE` becomes the cartoon's.
   - The catalogue's medium words become the cartoon's: `LEAD`, `REDRAW`, `TEXTURE`, `PAPER_LEAD`,
     `PAPER_CARD`, and "made of cut paper and card" in `front_prompt` and `night_prompt`.
   - #326's `scenery.leads()` and `TEXTURE` have the wording.
3. **Today's village in the prompts and looks** (`catalogue.py`, `village.py`). Name contemporary
   materials and things throughout, as #326's `scenery.py` does:
   - layers: a glass skyline behind green hills, mid-rise blocks with solar panels and roof
     gardens, concrete planters with tropical plants, and a footpath with tactile paving and a
     cycle lane
   - furniture: pale oak, white laminate, induction hobs, a screen menu board, a smart kiosk and
     solar street lamps
   - room papers: oak slats, stacked white tiles and plain plaster
   - building looks: tiled, concrete and painted-brick fronts with flat roofs, no shutters, and
     planters
   - **paint pale pieces on a backdrop they don't share,** since white walls on white and grey
     glass on grey both get keyed away.
   - **cut each ground strip to its own band,** as fronts are cut on their plans.
     - Make the strip solid from the band's usual top row to its usual bottom one.
     - Trim the sloped ends of a slab painted in perspective.
     - #326's `scenery.banded` does this. Without it, a pale or grey slab keyed away with the
       backdrop, and a plaza's sloped end, left holes where the sky showed through the pavement.
4. **Today's details in the front plans** (`fronts.py`), as #326's `scenery.modernised` draws them:
   - slim dark window frames with roller blinds, instead of curtains, sills and lintels
   - a plain light band in the shop's colour instead of each striped awning
   - a lit shop window with a ring where the neon pictogram goes
   - AC units beside upper windows
   - Add the light bands and pictograms to the plan's glow mask, so the night maps light them.
   - Bump `PLAN`.
   - FLUX kept adding doors to door-less cartoon units (three seeds of three on the café). Check
     every unit, and reseed or tighten the prompt.
5. **The dolls** (`server/simile/dolls/`):
   - `paint.prompt` in cartoon words. The front and back sheet asks for "four separate flat pieces
     of a cartoon cut-out puppet, laid apart", or FLUX merges the torsos into a body (4 of 6 in
     #326).
   - An ink outline about 0.9 units wide, baked round each piece in both atlases, with the frames
     and pivots moved to match. The client's rig then draws it with no change.
   - Heads about 1.2 times bigger and bodies about 1.15 times wider, as numbers in `shapes.py` and
     `look.BUILD`. The user decides how far.
   - `rimmed()`'s light card edge off. `sheet.TEXTURE` lower, since the cartoon has no paper grain to
     bring out.
   - Keep #310's colour restore. #326 measured the painter pulling light-brown skin 15 to 18 L\*
     lighter before it, whatever the reference.
   - **Check every colour region of every piece in the atlas, ears included,** against its flat
     colour, as #326's `compose.py match` does.
     - The cartoon painter draws ears as a dark ring round an orange or pink disc. The restore,
       which pins a region's median with each channel's gain capped at 4×, left five residents'
       ears ΔE 13 to 22 off.
     - Fill any region still over ΔE 6 with its flat colour, keeping the painting's light and
       shade, as #326's `dolls.matched` does. It refilled 33 of the cartoon's 222 regions.
     - Add a test that every committed doll passes the check.
     - Check thin details too. #326's check needs a region at least 6 matching pixels big in the
       atlas, so a one- or two-pixel stripe, like the one on a sole, goes unmeasured. Some are off,
       such as Henrietta's blue sole stripe and Lachlan's mint sole. Measure them on the painted
       sheet, where they're wider, or pixel by pixel.
   - Bump `VERSION`, and reset `REROLLS`.
6. **Repaint and commit** every piece and doll:
   - `simile papercraft`
   - `simile dolls paint --force`
   - `simile papercraft-preview`, then look at every piece

## Done when

- [ ] `content/papercraft/` and `content/dolls/` are repainted in the cartoon, set today, with the
      same manifest format, keys and lookups.
- [ ] Every piece has been looked at, with none showing lettering or extra doors.
- [ ] Every colour region of every doll, ears included, is within ΔE 6 of its `Appearance`
      colour in the committed atlases, and a test checks it.
- [ ] `make test` and `make lint` pass, the client's included, with nothing under `client/` or
      `content/street/` changed.
- [ ] The PR shows the four streets, the dollhouses and the residents at play size, from
      `simile papercraft-preview` and the client's dolls preview.

**Cost, from #309's and #310's numbers:** about 90 minutes of FLUX for the scenery with night
pictures, 26 minutes for the twelve dolls, and a look at every painting.
