# Previews for #329, style study 3

This branch isn't for merging. Delete it after review. The study is on the PR's branch,
`task/329-style-study-3`, in `docs/style-study-2/`. #326's paintings and pieces are on
`previews/326-style-study-2`, which this one doesn't change.

- `previews/`: every picture the study made, at full size, all five styles and the game now.
  - The streets, full width at 40 px/m and framed at 80 px/m, as a retina screen draws them.
  - The parallax pans as animated WebP.
  - The dollhouses at 60 px/m, the residents, the comparisons, the contact sheets, the pixel art
    rig study, the outline study and the sharpness study.
  - #326's two styles are re-drawn here the same way, from their pieces on its branch.
- `paintings/<style>/used/`: every FLUX painting the new styles' scenery is cut from, named by
  piece. A front is one painting per unit, numbered from the left.
- `paintings/<style>/rejected/`: paintings that were replaced, named by seed and why:
  - `extra-door`: a café unit that grew a door the plan doesn't have
  - `a-dollhouse` and `stairs-inside`: a bookshelf painted as a cut-away house
  - `smudged`: the revised cartoon's first sky
- `pieces/<style>/`: the cut, scaled pieces and their `manifest.json`, as `simile papercraft` writes
  them. `pieces/pixel/` are snapped to the pixel grid, with their palette in `palette.json`, and
  `pieces/pixel-smooth/` are the same pieces before the snap.
- `dolls/<style>/`: each resident's manifest and atlases.
  - `grimy-plain/` are the revised cartoon's residents painted with no outline, which the study
    draws one round. `grimy/` are painted with an outline, the other choice.
  - `sheets/`: the paintings the dolls are cut from.
  - `paintings/`: every sheet painted, rejected ones included, by hash. The revised cartoon's first
    front and back sheets for Odalys, Kofi and Lachlan misplaced the back of the head.
- `references/used/` and `references/rejected/`: every reference painted, at full size, by style,
  scene and seed. The rejects all have lettering. `*-as-kept.jpg` are the kept shop references as
  committed: pixel art's has one icon painted out of seed 44.
- `sharpness/<variant>/`: the sharpness study's pieces and dolls, at 8 bits, bf16, 1.5 times the
  pixels and from text.
- **The numbers in the README:**
  - `timings.jsonl`: the references, sharpness paintings, doll sheets and model loads, of #326 and
    #329. #329's start at `"at": 1792560000`.
  - `timings-<style>-scenery.jsonl`: every scenery painting, from #309's `Build`.
  - `consistency.json`, `skin.json`, `match.json`, `legibility.json`, `rig.json` and
    `sharpness.json`.
