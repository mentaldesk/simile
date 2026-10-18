# simile.gallery

Residents' paintings on the gallery's walls. Every `painting` interactable on a map (K2's
`painting_1` to `painting_13` on `gallery`) is a frame, and each frame shows one painting.

## Who paints

- **Painters**, residents whose craft is `painting`, make something for the gallery whenever they
  finish a `create` stay. They paint where writers write (B1's `writing_places`).
- **Muralists** paint for the gallery too: after each mural, and whenever no wall is worth
  painting. The gallery wraps B1's `mural_wall` hook (`taking_turns`), which then names the
  muralist's home rather than a wall, so they paint the canvas there and B1 calls `create` with
  their home's id. None of today's residents is a painter, so for now the three muralists fill the
  gallery.

M8's `Maker` makes the painting (`works/README.md` has how), with its SVG checks and its renderer
in a child process under the same time and memory limits as murals. Once `works` is up, the
gallery's `running` hook gives the maker its `hang`, and without it nobody paints for the gallery.

## Hanging

`Gallery.hang` stores the painting's PNG and SVG in the `paintings` table of the memory store's file
and hangs it in a frame (the `hung` table): the first empty one, nearest the gallery's door first, or
else in place of the painting hung longest ago. Paintings taken down keep their pictures, and the
`Work` stays in `works`.

Each new client gets `paintings` with every frame, hung or empty, and everyone gets it again when a
painting goes up. `GET /api/gallery/<work_id>.png` serves a painting's PNG from the `paintings`
table, and 404s for anything else.

## Visitors

B1 sends residents to the gallery as an outing. Once one has arrived and is staying, `Visitors`
walks them from painting to painting: the nearest they haven't seen first, then any but the one
they've just looked at, `linger` (2 to 5 sim minutes) at each. A new goal or a conversation stops
the tour.

- **Looking.** At someone else's painting they haven't seen, a resident says how it lands in one
  Haiku call through L1, below conversations' priority, as at the terminals and murals. The reply
  becomes a `work` memory `about` the artist with `work_id` and the painting's first 3 tags, so
  they talk about it later (M10). If the call fails, they try again after `look_again` (a sim
  hour). What's been seen is read back from memories, so a restart doesn't repeat it.
- **The player** remembers each painting they stand at, once, with no call. The client's panel
  shows it up close (`client/src/world/iso/README.md`).

Every constant is in `GalleryConfig`.

## By hand

```bash
cd server
uv run simile gallery paint kofi   # a canvas from what's on his mind, hung in $SIMILE_DB
uv run simile gallery paint kofi --png kofi.png   # and the picture saved too
```
