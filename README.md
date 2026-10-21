# Previews for #326, style study 2

This branch isn't for merging. Delete it after review. The study is on the PR's branch,
`task/326-style-study-2`, in `docs/style-study-2/`.

- `previews/`: every picture the study made, at full size.
  - The streets, full width as well as framed.
  - The parallax pans as animated WebP.
  - The dollhouses, the residents, the comparisons and the contact sheets.
- `paintings/<style>/used/`: every FLUX painting the scenery is cut from, named by piece. A front
  is one painting per unit, numbered from the left.
- `paintings/<style>/rejected/`: paintings that were replaced, named by what was different.
  - `old-street-reference`: papercraft pieces painted from the first papercraft street reference,
    which had a small sign of fake characters. They were all repainted.
  - `ground-on-white`: ground strips whose pale paving was keyed away on white.
  - `mid-on-grey`: mid layers whose grey glass was keyed away on grey.
  - `window-on-white`: the inside window, whose pale blind was keyed away on white.
  - `seed0` and `seed1`: the cartoon café, which grew extra doors.
- `pieces/<style>/`: the cut, scaled pieces and their `manifest.json`, as `simile papercraft` writes
  them. The `drift/` pieces are #309's own prompts painted against the modern references.
- `dolls/<style>/`: each resident's manifest and atlases, as committed to the study's pictures.
  - `sheets/`: the paintings the dolls are cut from.
  - `paintings/`: every sheet painted, rejected ones included. The cartoon's first front and back
    sheets merged the torsos into a whole character.
- `references/used/`: the eight references at full size.
- `rejected/`:
  - `references-v1/`: the first eight references, with lettering on their signs or a weak medium.
  - `references-v2/`: the second round's rejects, for lettering or a printed logo.
  - `references-v3/`: the papercraft street at seeds 42 to 45, each with a small sign of fake
    characters.
  - `dolls/`: the cartoon front and back sheets that failed.
  - `mid-on-grey/`: the mid layers cut on grey.
- `now-310-sheets/`: #310's side sheets, from `previews/310-paper-dolls`, which the skin
  measurement compares with.
- **The numbers in the README:**
  - `timings.jsonl`: the references, doll sheets and model loads.
  - `timings-<style>-scenery.jsonl`: every scenery painting, from #309's `Build`.
  - `consistency.json`, `skin.json` and `match.json`.
