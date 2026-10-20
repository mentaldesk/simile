# Previews for #309, the papercraft scenery build

Not for merging. The scenery itself is `content/papercraft/` on its PR branch; this branch holds
everything the build painted and composed, full size.

- `scenes/`: streets by day (`street-<id>.jpg`) and at night, each street at the four times of
  day (`times-<id>.jpg`: morning, afternoon, evening, night), and a dollhouse of every building
  with floors by day and at night. Composed in Python by `simile papercraft-preview` on the
  side-view maps; part 5 draws the game's own scene.
- `sheets/`: contact sheets of every committed piece. `fronts.jpg` shows each front by day and
  with its glow map added at night.
- `paintings/`: every FLUX.2 Klein 4B painting the committed pieces are cut from, as JPEG. Fronts
  and glow maps wider than a house are painted a unit at a time (`-0`, `-1`, `-2`).
- `rejected/`: every other painting, in the order it was painted (`<time>-<hash>.jpg`): the first
  runs, the café painted whole and in slices, the seeds tried for the tower and Garden Flats, and
  items re-prompted after a look. The PR says why each was replaced.
- `plans/`: the flat plans the fronts are redrawn from, and the sketches for stairs, the ladder,
  the ledge, the lift and the white fittings.
- `timings.jsonl`: the paintings the build made, with key, size and seconds, on an M2 Max at
  8-bit. Seed trials made outside the build aren't in it.
