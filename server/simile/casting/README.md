# simile.casting

P4: turns library characters (`content/characters/pool/`, P1's `Character`) into a village's
residents, hand-picked or drawn at random. Nothing here calls Claude.

## A world is a data directory

A village lives in a data directory: the folder of `$SIMILE_DB` (`server/data/` by default). A
cast is a `cast/` folder beside the save:

```
<data>/simile.db          the save: R2 and the saved world, as today
<data>/cast/cast.json     the Cast: game date, seed, each resident's Character as cast, home, bonds
<data>/cast/npcs/*.json   the residents as Npcs
```

`load_npcs()` reads `cast/npcs/` when the data directory holds a cast and `content/npcs/`
otherwise. The default data directory never gets one, so `make dev` always runs today's ten
residents.

Casting writes only `<data>/cast/`. It refuses:

- `server/data/` and anything in it, and anywhere in `content/`
- a data directory with a saved village (a saved world, or anything R2 keeps; news alone doesn't
  count) in `$SIMILE_DB` or in any SQLite file there, whatever its name
- a `cast/` folder that isn't a cast

A cast that never ran is replaced. To recast a world that did run, `simile reset` it first.

```bash
cd server
SIMILE_DB=/tmp/world/simile.db uv run simile cast --random 10
SIMILE_DB=/tmp/world/simile.db uv run simile headless --speed 10   # or make dev
```

`--pick a,b,c` casts those characters, alone or with `--random N` to fill up to N.
`--pin actor:kind:target` (repeatable) binds a bond between two characters and casts both.
`--data` names the directory instead of `$SIMILE_DB`, `--seed` repeats a cast, and `--date` sets
the day the village starts, which has to fit every resident's age and past.

## Choosing

`cast(characters, count, picks, pins, seed)` takes the picks and everyone pinned as given, then
draws the rest. `distance` compares two characters across values (their RMS difference), origin,
age, occupation group and gender, with the weights in `CastingConfig`. `spread` is the mean
distance between residents. Each draw picks at random among the best three candidates for one of:

- **spread**: farthest from everyone cast so far
- **conflict** (a fifth of the cast): values at least `conflict` (0.45 RMS) from someone's
- **affinity** (a fifth): values within `affinity` (0.3 RMS) of someone's

It refuses more residents than the village map has houses, and two residents with the same
`reference_clip`. A character without a clip clashes with nobody.

## Binding

`bind(chosen, pins, seed, game_date)` gives each resident a house from the village map at random,
binds the pins, then binds open hooks between residents. A one-way hook binds to the same kind on
the opposite side, a mutual one to the same kind. Each pair bonds once and each hook once. A pin
uses the matching hooks when the residents have them. Drawn bonds:

- prefer like-minded residents for `old_friend` and opposed ones for `rival`, `betrayal` and
  `estranged_sibling`
- keep ages within reach (20 years for siblings and old friends, 15 for exes, 25 for rivals)
- only make siblings of residents from the same origin

Ages are the game date's year minus the birth year.

## History

The cast's history goes into R2 when a server or headless run starts and the store holds nothing
of the cast's residents (the `running` hook in `lifespan.py`). So it's seeded on the first run,
and again after `simile reset` or with `SIMILE_FRESH=1`, at that run's start time `now`:

- **Bonds:** each side gets a `Relationship` that starts at their baseline from `meet`, shifted by
  the bond (`BONDS` in `config.py`), and that baseline moves to those scores, so the bond is where
  the feelings settle. One-way kinds open a flag owned by the target about the actor: `debt`,
  `secret`, `grudge` for a betrayal, `saved_life`. Each side keeps a `past` memory about the
  other, stamped `now`, salience 0.8: a sentence naming them ("Tom owes me money.") and their own
  hook's words.
- **The past:** each `PastMemory` becomes a `past` memory stamped one sim minute before `now` per
  year ago. They keep their order, and recall, which ranks salience × recency with a 12-hour
  half-life, still gives one from 60 years back 94% of its recency. So at the start the most
  salient ones surface first, and they fade with the rest over the first day or so. Stamped at
  their real dates, they would never surface.

## Voices

Pool characters have no reference clip yet, so V1 never loads a voice for them: their lines go out
with `voiced: false` and show as text, paced at the 200 words a minute B2 uses for a voice with no
measured rate. `Cast.unvoiced()` lists them.
