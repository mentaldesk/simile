# Previews for #311, the side-view scene

Not for merging: delete it after review. The work is on the PR's branch, `task/311-side-view-scene`.

Everything here is the game's own `SideScene`, in headless Chromium (Playwright, Metal) through
`?side`'s dev harness, which dispatches a stand-in snapshot on the side-view maps and moves the
residents by the protocol. The murals and paintings are the starter works in `content/works/`.

- `screens/`: 1440×900 at 2× unless named by size.
  - `street-<id>.jpg` and `street-<id>-night.jpg`: each street at 13:00 and 23:00, and
    `street-banyan_row-river.jpg` down the steps by the river in the evening.
  - `times.jpg` (and `time-*.jpg`): the square at 07:30, 14:00, 19:00 and 23:00.
  - `dollhouse-<building>.jpg`: the player inside, the front lifted off.
  - `climb-stairs.jpg`, `climb-ladder.jpg`, `climb-loft-ladder.jpg`, `lift-ride.jpg`: the player
    partway up the café's stairs, the park ladder, the maker space's loft ladder and the gallery's
    lift.
  - `murals.jpg` and `murals-blank.jpg`: the corner shop's and the Daily Grind's walls with their
    murals and without, `murals-house_10.jpg` a mural on a house with floors.
  - `text-layers.jpg`: the harness panel, the log, a target's name and a speech bubble over it.
  - `size-*.jpg`: 1280×720, 1920×1080, 2560×1440 at 2×, 3440×1440 and a 390×844 phone at 3×.
- `clips/`: GIFs at 640 px. `walk` (along the High Street), `enter` (the café's front coming off),
  `climb` (the café's stairs), `ladder` (the park lookout), `steps` (down to the river), `lift`
  (the gallery) and `day` (a whole sim day on the square, 36 sim minutes a frame).
