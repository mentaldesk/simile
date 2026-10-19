# Previews for #295, the side-view papercraft study

Not for merging. The study itself is `docs/side-view-study/` on its PR branch; this branch holds
everything it made, full size.

- `scenes/`: the composited pictures as PNG, full size, including the four times of day one by
  one and the street's camera pan as an animated WebP.
- `paintings/`: every FLUX.2 Klein 4B painting as it came out, as JPEG. `pilot-*` are the first
  tries (img2img and text prompts for the doll parts, text and edit mode side by side),
  `first-*` the paintings a second prompt replaced (the mid layer with people in it, the bathtub
  and basin on white, the awning that came with a kiosk), `*-text` the text-only twins, `night-*`
  the night edits, `sofa-*` the colour variants, `doll-*` the residents' painted parts sheets and
  `q8-*`/`q4-*` the quantized runs.
- `cutouts/`: each painting cut out, full size and untrimmed, as WebP with alpha.
- `sheets/`: the flat paper-doll sheets drawn from each resident's `Appearance`, before painting.
- `timings.jsonl`: every load and painting with its prompt, size, mode and seconds.
- `consistency.json`: each asset's colour distance from the references, edit mode against text.
