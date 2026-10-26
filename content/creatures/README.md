# Creatures

The tunnels' dangers: rats, recycler bots, wild dogs and bats (the design's *Dangers*), painted
by FLUX.2 [klein] 4B in #329's cartoon, as the tunnels' scenery is. Each has a walk, run or fly
cycle and an attack. Made from `server/` on Apple Silicon by

```bash
uv sync --extra images
uv run simile creatures paint                 # every creature whose catalogue entry changed
uv run simile creatures paint dog --force --paintings /tmp/creatures   # one again, saving its paintings and guides
uv run simile creatures preview               # draw preview.webp and cycles.webp again, painting nothing
```

Don't edit them by hand. CI never paints; the tests check what's committed. Painting waits while
another image model or an Ollama model is using the GPU.

**[`preview.webp`](preview.webp)** shows them in a sewer room beside the player at play size, then
every frame at twice that, and **[`cycles.webp`](cycles.webp)** plays each pose.

## Files

For each creature, `rat`, `bot`, `dog` and `bat`:

| File | What it is |
|---|---|
| `<id>.json` | The manifest, below. |
| `<id>.webp` | Every frame, cut out, in one atlas: WebP at quality 85, as the dolls' are. |

`content/creatures/` stays under 2 MB (`tests/creatures/test_content.py`).

## The manifest

```json
{
  "id": "dog",
  "hash": "d31740d53399fd2e",
  "version": 1,
  "ppm": 80,
  "moves": "walk",
  "size": [2.2, 1.51],
  "painted": "dog.webp",
  "frames": {
    "stand": {"frame": [0, 0, 180, 125], "anchor": [89.8, 123.0]},
    "run": {"frame": [510, 0, 180, 102], "anchor": [90.8, 121.0]},
    "...": {}
  },
  "poses": {"stand": ["stand"], "run": ["run", "run_pass"], "attack": ["attack"]}
}
```

- **`ppm`** is atlas pixels a metre, the dolls' 80, so a creature draws at the same scale as the
  residents and the player: scale it by the scene's `PPM` over this.
- **`size`** is the first frame's width and height in metres, nose to tail and sole to top: a
  starting point for its body's box.
- **`frames`**: each frame's place in the atlas (x, y, width, height) and its **`anchor`**, from
  the frame's top-left, which goes where the creature is:
  - **`moves: "walk"`** (rats, bots and dogs): the ground under the middle of the first frame.
    Every frame keeps it, so a frame with all four paws in the air, the gallop or a leap, has its
    anchor below the frame and draws in the air.
  - **`moves: "fly"`** (bats): the middle of the first frame, in the air.
  - A frame marked **`"hangs": true`**, the bat's `roost`, hangs from its anchor instead: the top
    of the frame, where its feet hold the ceiling.
- **`poses`**: the frames each pose plays through its cycle, one after another. Every frame faces
  right, seen from the side; mirror it to face left.
  - `rat`: `stand`, `walk`, `attack`.
  - `bot`: `stand`, `walk` (a limp: a step and back), `attack` (its grabber reaching to recycle you).
  - `dog`: `stand` (snarling), `run` (a gallop), `attack` (a leap with its jaws open).
  - `bat`: `fly` (wings up, level, down, level), `attack` (a dive with its mouth open), `roost`.
- **`hash`** is what the creature was painted from: its catalogue entry, its prompts and the
  pipeline's `version`. A creature whose hash no longer matches is painted again; nothing else is.

## How they're made

`server/simile/creatures/`, with each creature in `catalogue.py`:

1. **The first frame from words** (`stand`, or the bat's `glide`), in the style of the tunnels'
   cartoon reference (`content/papercraft/references/cartoon/street.jpg`), with the scenery's
   `painter.CARTOON` words, a little dirty, or for the bot `painter.GRIMY`, the sewers' properly
   grimy version, so it looks broken and old. Seen from the side, facing right, on light grey.
2. **Every other frame is an edit of a frame before it, over a guide** drawn from that frame's
   painting: FLUX keeps an edit's subject where it was and redraws little of it, so asked in words
   alone for a gallop it paints the dog standing.
   - **Rubbed out**: boxes over the legs, or a bat's wings, painted over in the background's grey,
     which FLUX fills in the new pose.
   - **Mirrored**: the bat's raised wings reflected down under its shoulders, for the downstroke.
   - **Turned**: the bat tipped forward to dive.
   - **Flipped**: the bat upside down, its wings rubbed out, to roost.
3. **Cut out** with the dolls' cut (#309's IS-Net and key, without the floor shadow), and specks
   apart from the body cut away.
4. **Checks.** A frame is painted again with another seed, a few times at most, and the best kept,
   if it's cut off by the edge of the painting, in pieces, its average colour more than ΔE 10 from
   the first frame's, or half or twice its size. A frame that comes out off-model by eye gets a
   reroll in its creature's `rerolls`.
5. **Scaled** so the first frame is the creature's `length` wide at 80 px/m, and every other frame
   by the same factor, so each is the size it was painted at beside the first. Then packed into
   the atlas with the dolls' packer.

Each painting is cached in `server/data/creatures/paintings/` by everything it was painted from, so
cutting and scaling can be retuned without painting again.
