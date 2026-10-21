# Draft: the follow-up issue for rebuilding the residents

To be filed only if the user chooses to switch, from #334's study in `docs/residents-study/`. It's
written for the study's recommendation, whole FLUX characters (approach 1, painted from the rig's
poses as approach 1b), with what changes if the user picks another approach at the end.

---

**Title:** Side view: residents as whole FLUX characters, in the chosen style

**Body:**

#334 compared four ways to make the residents against #310's paper dolls. The user chose whole
characters: each resident painted whole by FLUX.2 Klein in the chosen style, as #295's villagers
were, with a small set of painted poses the client swaps between, flips and bobs. The study and
its pictures are in `docs/residents-study/`, and every painting is on
`previews/334-residents-study`.

**It doesn't touch movement or the maps:**

- `content/street/`, `server/simile/street/`, `server/simile/sim/` and the client's movement,
  camera and map code are unchanged.
- The sim's poses (`client/src/net/protocol.ts`'s `Pose`), facings and positions are unchanged.
  Only how a resident is drawn in a pose changes.
- Where a resident stands, how fast they walk and where they climb stay the sim's. The client
  keeps placing a figure by the point under its feet.

## Owns

- `server/simile/dolls/`: the build becomes a sprite build, except `routes.py` and `job.py`
  until the creator moves over (below)
- `server/tests/dolls/`
- `content/dolls/`
- `client/src/dolls/`: a sprite figure beside `PaperDoll`, and the manifest's new kind
- the client's tests that read `content/dolls/`

## Task

1. **The sprites.** For each resident and the player, from their `Appearance`:
   - Lay out the flat doll in each pose on one sheet, with #310's pieces and the client's rig
     (`rig.ts`), at the style's proportions: four side-on walk frames, standing, sitting, a
     stair step, and a ladder climb seen from behind. #334's `whole.py strip` does the walk.
   - FLUX redraws the sheet freely in the style, in edit mode with the style's residents
     reference. One painting a sheet keeps every frame the same person.
   - Name skin, hair, clothes and accessories in the prompt, as #310's `person()` does, and say
     "the face clean" so the style's grime stays off faces.
   - Cut each figure out (#309's IS-Net and key), and store where its feet are.
   - Pull its colours back to the `Appearance`, region by region, with the mannequin as the
     map: #310's `restore`. #334 found whole paintings drift by ΔE 5 to 9 on skin without it.
   - Reroll a sheet whose figures came out off-model, as #310's `REROLLS` do. Look at every
     sheet.
2. **The manifest.** One per resident: each pose's frames, their atlas rectangles and feet
   points, and the `hash` and `appearance` #310 keeps. Pack frames into a WebP atlas at q85.
3. **The client.** A `SpriteFigure` beside `PaperDoll`, with the same `setPose(pose, facing,
   phase, options)`:
   - each pose picks its frame by phase, as `rig.ts` picks angles
   - west flips the frame, north uses the back frame
   - the walk bobs and sways a little, and a run plays the walk faster
   - poses with no frames fall back to the nearest that has one (reading and working to
     sitting or standing)
   - drawn at the client's retina size; #329 found sharpness is set by draw size, not painting
4. **The creator.** It shows today's flat doll at once and swaps in the sprites when their sheet
   is painted, as #310's job does now. A sheet is about 75 s of FLUX on Apple Silicon.
5. **Remove** #310's sheet prompts, cut and patching once nothing draws `PaperDoll`.

## Done when

- [ ] Every resident and the player has sprites in `content/dolls/`, built by
  `uv run simile dolls`, and only changed `Appearance`s are repainted.
- [ ] The client draws residents from them in every pose the sim sends, facing every way.
- [ ] Each resident's skin, hair and clothes are within ΔE 6 of their `Appearance`, checked
  region by region against the mannequin.
- [ ] The creator previews a new resident at once and paints them in the background.
- [ ] Nothing in movement, maps or the sim changed, and its tests pass unchanged.

## If the user picks another approach

- **Paint whole, then cut (2):** keep #310's manifest and the rig. Replace the sheet prompt and
  cut with #334's `cut.py`. It needs a pose-faithful painting first: #334's loose paintings
  moved every arm, and the cuts show.
- **3D, pre-rendered (3):** a Blender build (MPFB with CC0 assets) renders each pose to the same
  sprite manifest as above, so the client part is the same. The creator needs a body type and
  age besides the `Appearance`, and Blender on the machine that builds.
- **3D, repainted (4):** as (3), then FLUX repaints each frame, four frames to a painting, and
  `restore` pulls colours back with Blender's flat pass as the map.
