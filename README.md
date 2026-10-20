# Previews for #314, the cut-over to the side view

Screenshots from headless Chromium against `make dev`, with the fake LLM (`SIMILE_LLM=fake`), no
voices and no news fetching, each run on its own temporary data directory. Nothing here is part of
the game; this branch only holds pictures for the PR.

- `01`–`17`: a fresh village. The menu's `?play` opens the side view on the High Street; the
  player uses a terminal, a mural, the café's door, the counter, the stairs, the street steps to
  Banyan Row, the gallery's lift and a painting.
- `20`–`27`: a copy of the maintainer's own save, made on today's isometric maps and loaded on the
  side view. Everyone is where the table in `server/simile/persistence/old_cells.csv` put them,
  the murals are on their walls and the paintings in their frames.
- `28`: the side scene's dev harness (`?harness=side&at=banyan_row:17`) at house 10's door, where E
  looks at the mural and the door's hint stays, for ↑.
