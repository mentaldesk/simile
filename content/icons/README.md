# Icons

Pictures of things on their own, painted by FLUX.2 [klein] 4B in #329's cartoon, as the tunnels'
creatures are. The character screen's body map draws them at each part's place, and its Gear tab
draws a tile for each kind of item the player carries. Made from
`server/` on Apple Silicon by

```bash
uv sync --extra images
uv run simile icons paint                     # every icon whose catalogue entry changed
uv run simile icons paint kidney --force --paintings /tmp/icons   # one again, saving its painting and cut-out
```

Don't edit them by hand. CI never paints; the tests check what's committed. Painting waits while
another image model, an Ollama model, or a `simile creatures` or `simile icons` run is using the GPU.

**[`preview.webp`](preview.webp)** shows the character screen's Body tab in four bodies: whole, a
kidney sold, fully fitted with a grade 2 cell and grade 3 legs, and a stage 1 body whose legs have
since been retired. It's a screenshot of the client, taken by hand: take it again when the map or its icons change.
**[`previews/gear.webp`](previews/gear.webp)** is the same for the Gear tab: carrying one of every
item, and nearly nothing.

## Files

- **`<id>.webp`**: each icon cut out on transparency, cropped to it with 2 px to spare, at most 256
  px long: WebP at quality 85, as the dolls' are.
- **`icons.json`**: every icon in the catalogue, in its order, by id:

  ```json
  {
    "version": 1,
    "icons": {
      "kidney": {"file": "kidney.webp", "size": [245, 260], "hash": "9b2fabf5eb136f31"}
    }
  }
  ```

  **`size`** is the picture's width and height in pixels, and **`hash`** what it was painted from:
  its catalogue entry, its prompt and the pipeline's `version`. An icon whose hash no longer
  matches is painted again; nothing else is.

`content/icons/` stays under 1 MB (`tests/icons/test_content.py`).

## The body map's

| Icons | What they are |
|---|---|
| `eye`, `vertebra`, `stomach`, `kidney`, `legs`, `feet` | The player's own organs. |
| `<organ>_sold` | Where one was, sold: a patch of skin stitched shut. |
| `power_cell`, `datajack`, `infrared_eye`, `bionic_legs`, `spring_feet` | Each bionic, every grade of its line alike. |

The client mirrors the left kidney, so both face the spine.

## The items'

Every item the server defines has one, by its item id: the lamp, the ration pack, the metro's and
the sewers' salvage, and the recipes' parts. `tests/icons/test_items.py` finds every item in the
server's code, config and maps, and fails for one without an icon. `unknown_item`, a box with a
question mark, is the Gear tab's picture for an item with none of its own.

## Adding icons

Add an `Icon` to `server/simile/icons/catalogue.py`, in a tuple of its own if it starts a new set,
such as the items, then `uv run simile icons paint`: only the new one is painted. Its `words` say
what it is; the prompt adds the cartoon's style words and asks for it alone in the middle of a
plain grey background. Give a pair of things `pieces=2`. The client finds it by id with `iconUrl`
in `client/src/ui/icons.ts`.

## How they're made

`server/simile/icons/`:

1. **Painted from words** in the style of the tunnels' cartoon reference
   (`content/papercraft/references/cartoon/street.jpg`), with the scenery's `painter.CARTOON` words.
2. **Cut out** with the dolls' cut (#309's IS-Net and key, without the floor shadow), and specks
   apart from it cut away, as the creatures are.
3. **Checked**, and painted again with another seed, a few times at most, keeping the best, if it's
   empty, cut off by the edge of the painting, or not in its `pieces`: a pair must be in two pieces
   of about a size, and anything else in one. One that comes out wrong by eye gets a `reroll`.
4. **Cropped** to the icon, or to the share of it its `keep` box says: FLUX paints legs with feet
   however it's asked, so the legs keep the top of the painting and the feet are an icon of their
   own. Then scaled down to at most 256 px long.

Each painting is cached in `server/data/icons/paintings/` by everything it was painted from, so
cutting and scaling can be retuned without painting again.
