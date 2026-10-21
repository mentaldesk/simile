# Draft: the follow-up issue for rebuilding the residents

To be filed only if the user chooses to switch, from #334's study in `docs/residents-study/`. It's
written for the study's recommendation, approach 1b: whole FLUX characters painted from the rig's
poses. The end says what changes if the user picks another approach.

---

**Title:** Side view: residents as whole FLUX characters, in the chosen style

**Body:**

#334 compared four ways to make the residents against #310's paper dolls. The user chose whole
characters painted from the rig's poses. The build lays out each resident's flat doll in a few
poses on one sheet, FLUX redraws the sheet as one whole person in the chosen style, and the client
swaps between the painted frames, as sprites. The study and its pictures are in
`docs/residents-study/`, and every painting is on `previews/334-residents-study`.

**It doesn't touch movement or the maps:**

- These stay unchanged:
  - `content/street/`, `server/simile/street/` and `server/simile/sim/`
  - the client's maps, `client/src/side/motion.ts`, `client/src/side/layout.ts` and the camera
- The sim's poses, facings and positions are unchanged. The poses are `client/src/net/protocol.ts`'s
  `Pose`. Only how a resident is drawn in a pose changes.
- The client keeps placing a figure by the point under its feet, at the depth it uses now.

## Owns

- **The build:** `server/simile/dolls/` and `server/tests/dolls/`. This includes `job.py` and
  `routes.py`, since the creator's job paints the new sheets (step 5).
- **The content:** `content/dolls/`.
- **Drawing in the client:**
  - `client/src/dolls/`: a sprite figure beside `PaperDoll`, and the manifest's new kind
  - where the game draws residents: `client/src/side/side-doll.ts`, `client/src/side/poses.ts`
    (its `PoseCache` over `rig.ts`) and `client/src/side/side-scene.ts`, which loads the atlases
  - `client/src/world/assets.ts`, which looks up each resident's manifest
- **The creator's preview:** `client/src/creator/doll-stage.ts`.
- **The tests that read `content/dolls/`:** `client/src/dolls/assets.test.ts` and
  `client/src/side/poses.test.ts`.

## Task

1. **The sheets.** For each resident and the player, lay out their flat doll, with #310's pieces
   and the client's rig at the style's proportions, four figures to a sheet:
   - **walk:** four side-on frames of `rig.ts`'s walk (#334's `whole.py strip walk`)
   - **run:** four side-on frames of its run (`whole.py strip run`)
   - **still:** standing side-on, sitting, a stair step, and a ladder climb seen from behind
   - **turn:** standing and mid-stride from the front, then the same from behind. These are
     what facing south and north show, walking or not. `DollStage` walks every doll east,
     south and north.
2. **Painting.**
   - FLUX redraws each sheet freely in the style, in edit mode with the style's residents
     reference. One painting a sheet keeps its four figures the same person.
   - Name skin, hair, clothes, accessories, age and build in the prompt, as #310's `person()`
     does, and say "the face clean".
   - **Check each sheet's poses.** #334's FLUX turned the walk's first frame, a passing pose,
     into a full stride on every sheet, so each walk came out stride, stride, pass, stride.
     Make the guide's legs clearer (the near leg lifted, the far leg straight), or reroll a sheet
     whose frames repeat. Look at every sheet, and keep rerolls in `REROLLS`.
3. **Cutting out and colour.**
   - Cut each figure out with #309's IS-Net and key, and store where its feet are.
   - Pull its colours back to the `Appearance`, region by region, with the mannequin fitted over
     the painting as the map. This is #334's `study.restored`, a gentler #310 `restore`.
   - **It isn't enough on its own.** After it, #334 still had 7 of 24 regions over ΔE 6: shoes
     against the ink line, white shoes painted cream, an apron and a scarf. Skin came within
     ΔE 1.6.
   - Add a second pass for what's still off, like #329's `dolls.matched`. It fills a region with
     its flat colour and keeps the painting's shading, once the map lines up well enough to
     find the region.
4. **The manifest and the client.**
   - **The manifest:** one per resident, with each pose's frames, their atlas rectangles and
     feet points, and the `hash` and `appearance` #310 keeps. Pack the frames into a WebP atlas
     at q85.
   - **A `SpriteFigure`** with `PaperDoll`'s `setPose(pose, facing, phase, options)`:
     - each pose picks its frame by phase, as `rig.ts` picks angles
     - west flips the side frames, and south and north use the turn sheet's
     - the walk bobs a little, and `run` blends from the walk's frames to the run's
     - reading and working use sitting or standing, looking uses standing, and riding uses the
       front standing frame
     - drawn at the client's retina size: #329 found sharpness is set by draw size, not by the
       painting
   - `side-doll.ts` and `side-scene.ts` draw it where they now draw `PaperDoll`.
5. **The creator.** `DollStage` shows today's flat doll at once and swaps in the sprites when the
   sheets are painted, as #310's job does now. Four sheets are about 5 minutes of FLUX on Apple
   Silicon. `job.py` and `routes.py` paint and serve them.
6. **Remove** #310's sheet prompts, cut and patching once nothing draws `PaperDoll`.

## Done when

- [ ] Every resident and the player has sprites in `content/dolls/`, built by
  `uv run simile dolls`. Only changed `Appearance`s are repainted.
- [ ] The game draws residents from them in every pose the sim sends, facing east, west, south and
  north.
- [ ] The creator previews a new resident at once and paints them in the background.
- [ ] Each resident's skin, hair, top and bottom are within ΔE 6 of their `Appearance`, checked
  region by region against the mannequin. Shoes and accessories are within 6 too, or listed
  with how far off they are.
- [ ] `client/src/dolls/assets.test.ts` and `client/src/side/poses.test.ts` pass, changed only
  for the new manifest. Movement's and the maps' tests pass unchanged.

## If the user picks another approach

- **Paint whole, then cut (2):** keep #310's manifest and the client's rig. Replace the sheet
  prompt and cut with #334's `cut.py`. It needs a pose-faithful painting first: #334's cuts show
  at every joint with both prompts.
- **3D, pre-rendered (3):** a Blender build, MPFB with CC0 assets, renders each pose and view to
  the same sprite manifest as above, so the client part is the same.
  - The creator needs a body type and age besides the `Appearance`.
  - The machine that builds needs Blender.
- **3D, repainted (4):** as (3), then FLUX repaints each frame on its own. #334 found four frames
  to a painting worse. `restore` pulls the colours back with Blender's flat pass as the map, and
  hair the map puts over a face needs the same second pass as above.
