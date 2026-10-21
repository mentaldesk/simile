# Dolls

The residents' painted figures, and the flat paper doll the creator shows while one is painted. An
area without scenes; the side-view scene and the creator draw with it. The files and the manifest
are in [`content/dolls/README.md`](../../../content/dolls/README.md).

## Using it

```ts
import { dolls, flatDoll, makeDoll, makeFigure } from '../dolls';

const odalys = await makeFigure(scene, x, groundY, 'odalys', dolls.odalys, 245);
odalys.setPose('walking', 'west', time / 1000);

const preview = await makeDoll(scene, x, y, 'draft', await flatDoll(appearance), 245);
```

- **`dolls`** has every committed figure by id, its atlas's URL resolved. **`flatDoll(appearance,
  character?)`** asks the server for a flat doll for any look; **`loadDoll(url)`** reads a figure
  a job painted. `isFigure` tells the two apart.
- **`makeFigure(scene, x, y, id, figure, height?)`** draws a `SpriteFigure` once its atlas has
  loaded. Its origin is on the ground under the middle of its head, and `height` is how many
  pixels the standing figure is.
- **`SpriteFigure.setPose(pose, facing, phase, options)`** is `PaperDoll`'s: `pose` is the sim's
  `Pose` or `'jumping'`, and `phase` how far through its cycle it is, any number. Each pose plays
  its painted frames by phase (`sprite.ts`):
  - `walking` plays the walk, a stride and a passing step, bobbing and swaying a little, and the
    run once `options.run` is past a half;
  - `sitting` sits, and so do `reading` and `working` when `options.seated`; they, `looking` and
    `riding` otherwise stand;
  - `climbing` walks up stairs and climbs a ladder from behind, turning from side to side, by
    `options.on`, which defaults to stairs from the side and a ladder facing north or south.

  Westward facings mirror the frames. North and south show the three-quarter figure, as Paper
  Mario does.
- **`makeDoll`** draws the flat doll with the rig (`rig.ts`, `PaperDoll`): every pose is a set of
  joint angles over its pieces. Only the creator's instant preview uses it.

## Looking at them

With `make dev` (or `npx vite` in `client/`), `/src/dolls/preview.html` draws them as the game
does:

| Query | What it shows |
|---|---|
| `show=lineup` | everyone facing east, south and north, four to a row |
| `show=views` | a row for each of `facings` (east, south, north), a column for each figure, in `pose` |
| `show=poses&who=kofi` | every pose in each facing |
| `show=walk&who=kofi,priya` | the walk cycle, in `frames` steps |
| `show=run&who=kofi,priya` | a row each: walking, running from the side, front and back, and walking into a run and back as Shift goes down and up |
| `show=climb&who=kofi` | a ladder from the back and stairs from the side |
| `show=flat&appearance=<base64 JSON>` | the flat-doll route's doll for any look, with the rig |

`height` sets their size (245, street size, by default), and `phase` stops the animation there.
