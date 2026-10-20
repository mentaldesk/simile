# Previews for #326, style study 2

This branch isn't for merging. Delete it after review. The study is on the PR's branch,
`task/326-style-study-2`, in `docs/style-study-2/`.

- `previews/`: every picture the study made, at full size.
  - The streets, full width as well as framed.
  - The parallax pans as animated WebP.
  - The dollhouses, the residents, the comparisons and the contact sheets.
- `paintings/<style>/used/`: every FLUX painting the scenery is cut from, named by piece. A front
  is one painting per unit, numbered from the left.
- `paintings/<style>/rejected/`: paintings that were replaced.
  - The cartoon café at seeds 0 and 1, with extra doors.
  - The inside window painted on white, whose pale blind was keyed away.
  - The mid layer painted on grey, whose grey glass was keyed away.
- `pieces/<style>/`: the cut, scaled pieces and their `manifest.json`, as `simile papercraft` writes
  them. The `drift/` pieces are #309's own prompts painted against the modern references.
- `dolls/<style>/`: each resident's manifest and atlases, as `simile dolls paint` writes them.
  - `sheets/`: the paintings the committed dolls are cut from.
  - `paintings/`: every sheet painted, rejected ones included. The cartoon's first front and back
    sheets merged the torsos into a whole character.
- `references/used/`: the eight references at full size.
- `rejected/`:
  - `references-v1/`: the first eight references, with lettering on their signs or a weak medium.
  - `references-v2/`: the second round's rejects, for lettering or a printed logo.
  - `dolls/`: the cartoon front and back sheets that failed.
  - `mid-on-grey/`: the mid layers cut on grey.
- `now-310-sheets/`: #310's side sheets, from `previews/310-paper-dolls`, which the skin
  measurement compares with.
- `timings.jsonl`, `consistency.json` and `skin.json`: the numbers in the README.
