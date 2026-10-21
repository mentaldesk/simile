# Dolls

The paper-doll rig: each piece of a doll an image in a container, and a pose a set of joint
angles. An area without scenes; part 5's side-view scene and part 8's creator draw with it. The
files and the manifest are in [`content/dolls/README.md`](../../../content/dolls/README.md).

## Using it

```ts
import { dolls, flatDoll, makeDoll } from '../dolls';

const odalys = await makeDoll(scene, x, groundY, 'odalys', dolls.odalys, 245);
odalys.setPose('walking', 'west', time / 1000);

const preview = await makeDoll(scene, x, y, 'draft', await flatDoll(appearance), 245);
```

- **`dolls`** has every committed doll by id, its atlases' URLs resolved. **`flatDoll(appearance,
  character?)`** asks the server for a flat doll for any look; **`loadDoll(url)`** reads a doll a
  job published.
- **`makeDoll(scene, x, y, id, doll, height?)`** draws the flat pieces at once and the painted ones
  when their atlas has loaded. Its origin is on the ground under the hips, and `height` is how
  many pixels the standing doll is, hair included.
- **`PaperDoll.setPose(pose, facing, phase, options)`**: `pose` is the sim's `Pose` or `'jumping'`,
  and `phase` how far through its cycle it is, any number, so `time / period` works. Eastward
  facings draw the side facing right, westward ones left, `north` the back and `south` the front.
  `options.seated` sits for `reading` and `working` (at a desk); `options.on` says whether
  `climbing` is on a `ladder` (the default facing `north` or `south`) or `stairs` (the default
  from the side). `options.run`, 0 to 1, turns `walking` into a run: leaning in, the knees higher,
  the elbows bent and pumping, a longer stride and a moment with both feet off the ground. Values
  between blend the two, so the walk doesn't snap into a run. Planted poses stand on the ground,
  except a run in the air. A ladder climb or a jump keeps the standing
  hip height, so the caller moves the doll up the ladder or along the arc.

The far arm and leg draw behind and darker, and each piece casts a small shadow on the ones
behind it.

## The maths

`rig.ts` is Phaser-free: `posed(doll, pose, facing, phase, options)` gives each piece's position,
angle and stretch, back to front, and `rig.test.ts` checks every pose in every facing for every
committed doll. `paper-doll.ts` is the Phaser side.

## Looking at them

With `make dev` (or `npx vite` in `client/`), `/src/dolls/preview.html` draws them with this rig:

| Query | What it shows |
|---|---|
| `show=lineup` | everyone from the side, front and back, four to a row |
| `show=views` | a row for each of `facings` (east, south, north), a column for each doll, in `pose` |
| `show=poses&who=kofi` | every pose in each facing |
| `show=walk&who=kofi,priya` | the walk cycle, in `frames` steps |
| `show=run&who=kofi,priya` | a row each: walking, running from the side, front and back, and walking into a run and back as Shift goes down and up, at the side scene's cadence |
| `show=climb&who=kofi` | a ladder from the back and stairs from the side |
| `show=flat&appearance=<base64 JSON>` | the flat-doll route's doll for any look |

`height` sets the dolls' size (245, street size, by default), `flat` draws only the flat
pieces, and `phase` stops the animation there.
