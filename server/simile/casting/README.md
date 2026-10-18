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
fills the village's roles, then draws the rest.

**The village's roles come first** (#235). `content/characters/tables/roles.toml` names them, in
order: the Daily Grind's barista, the noodle bar's cook, and hosts for the maker space and the
gallery. A pick whose job fits a role holds it. For each role still open, casting draws a character
whose job fits, the one farthest from the cast so far among the best three. A role nobody in the
library fits stays open, and a cast smaller than the roles fills the first ones.

**Then everyone else**, so that the cast has:

- **elders:** `elders` (2) residents over `elder_age` (60) in a cast of 10, scaled to its size,
  with a trade from `occupations.toml`, working or retired. A role holder can be one.
- **makers:** `maker_share` (7 in 10) of the residents outside a role with a job from
  `makers.toml`. The rest have a job from `occupations.toml`, or none.
- **no repeated job families:** each draw prefers a job family nobody in the cast has, and nobody
  else gets a job a filled role names, like a second barista.

Each of these gives way when the library can't meet it. `distance` compares two characters across
values (their RMS difference), origin, age, job family and gender, with the weights in
`CastingConfig`. A job family is the job's `makers.toml` family or its ISCO-08 sub-major group in
`occupations.toml`. `spread` is the mean distance between residents. Each draw picks at random
among the best three candidates for one of:

- **spread**: farthest from everyone cast so far
- **conflict** (a fifth of the cast): values at least `conflict` (0.45 RMS) from someone's
- **affinity** (a fifth): values within `affinity` (0.3 RMS) of someone's

It refuses more residents than the village map has houses, and two residents with the same
`reference_clip`. A character without a clip clashes with nobody.

## Binding

`bind(chosen, pins, seed, game_date)` gives each resident a house from the village map at random,
and each role to the first resident whose job fits it, in the order `cast` filled them. A role
holder's `workplace` is the role's interior, with its `shifts` and `pay`, and their `Npc` has the
same. Everyone else's are left for E3 (#243). Then it binds the pins, then open hooks between
residents. A one-way hook binds to the same kind on
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

## Variety

`uv run simile cast-variety --count 10 --seeds 5` casts from the pool with seeds 0 up and reports,
for each cast and on average: distinct job families, residents who make or study something (a job
from `makers.toml`, one in `occupations.toml` marked `makes`, or a student), residents outside the
roles whose job family another of them has, elders, and the spread of ages.
