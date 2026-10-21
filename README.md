# Previews for #334, the residents study

This branch isn't for merging. Delete it after review. The study is on the PR's branch,
`task/334-residents-study`, in `docs/residents-study/`. Pictures with no transparency are JPEG at
q92 and 4:4:4; cut-outs, renders and atlases are lossless WebP.

- `pictures/`: every picture the study made, at full size.
- `1-whole/`: approach 1.
  - `paintings/`: the standing paintings from text and every pose's edit, by resident, pose and
    seed. `rejected/` are the pilot's first step, sit and climb edits: the second stride came
    out the same as the first, the sit on a box and the climb with a ladder.
  - `sprites/`: each painting cut out, with `feet.json`, where each stands.
  - `strip/`: approach 1b, the walk painted from the rig: each mannequin sheet (`*-guide`),
    its painting, each frame cut out and colour-restored, and `raw/` before the restore.
- `2-cut/`: approach 2.
  - `mannequins/`: the sheets FLUX painted over.
  - `paintings/`: its paintings, `<who>-1` with the loose prompt and `<who>-1-tight` with the
    tight one.
  - `dolls/` and `dolls-tight/`: the cut dolls, each a manifest and flat and painted atlases in
    #310's format, and `covered.json`, how much of each piece was filled in.
- `3-model/<who>/`: approach 3's renders, every frame toon-shaded and in flat colours
  (`*-flat`), the spec Blender built it from, and its timings. `grime` is the texture FLUX
  painted, and `grime-raw` the painting.
- `4-repaint/<who>/`: approach 4's repaints as FLUX painted them, `raw/` cut out, and `cut/` with
  the colour restored. `4-repaint-strip/<who>/`: the walk four frames to a painting, the guide
  and painting in `paintings/` and each frame cut out.
- `timings.jsonl`: every FLUX load and painting, with its prompt and seconds. The model renders'
  timings are in each `3-model/<who>/timings.json`.
- `match.json`, `consistency.json`, `legibility.json`, `costs.json`: the numbers in the README.
