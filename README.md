# Previews for #310, paper-doll residents

Not for merging: delete it after review. The work is on the PR's branch, `task/310-paper-dolls`.

- `screens/`: the PR's pictures at full size. All but two are drawn by the client's rig,
  through `client/src/dolls/preview.html`. `before-after*.png` draws the "before" with #295's
  `doll.py` and its painted sheets. `scale-scenery.png` is a Python composite with #309's
  committed fronts and furniture at their 120 px/m.
  - `views-street.png` and `views-2x.png`: everyone from the side, front and back, at street size
    (245 px) and twice that. `views-flat.png`: the same, flat, as they draw before their paint loads.
  - `poses-<id>.png`, one for each resident and the player: every pose (standing, walking,
    sitting, reading, working, looking, climbing, riding, jumping) facing east, south, north and
    west.
  - `walk.gif`, `climb.gif`, `riding.png`: the walk cycle, a ladder from the back and stairs from
    the side, and riding the lift.
  - `flat-route.png`: the flat-doll route's doll for a look nobody has.
- `paintings/used/`: the 24 FLUX.2 [klein] 4B paintings the committed dolls are cut from, as JPEG.
  The front and back sheets, Lachlan's, Tobias's and Mirela's side sheets were repainted after
  review through #319's `EditPainter`.
- `paintings/rejected/`: every other painting, so the misses can be seen:
  - the first prompt's, which named no accessories, so the painter dropped Desmond's backpack
    and Mirela's apron bib;
  - the prompt that also named clothes, which painted legs and shoes under the torsos and a head
    on Lachlan's back torso;
  - the sheets rerolled before review: Ingrid's side (an extra head above her thigh), Lachlan's
    side (a brown patch on his shirt), Ingrid's front and back (the back of her hair off its
    outline) and Odalys's front and back, seeds 0 to 4 (the hair off its outline, or arms and a
    whole body added);
  - every front and back sheet and the cap wearers' side sheets from before review, painted from
    flat pieces with a wedge of shirt between the legs, strands below Desmond's hairline and no
    hair under the caps from the side;
  - after review: Marguerite's front and back at seed 0 (dark strands off the outline), Mirela's
    side at seeds 1 and 2 (her face off its outline, or the belt sliver), and Tobias's side at
    seeds 0 to 3 (his ear drawn forward of its outline).
- `sheets/`: the flat sheets the painter redrew.
