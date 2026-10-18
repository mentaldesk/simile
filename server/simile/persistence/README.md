# simile.persistence

The village carries on where it left off. R2's database already keeps relationships, flags,
memories and events as they happen, and which news each NPC has read is their `news` memories.
This module keeps the rest in its own `saved_world` table of the same file (`$SIMILE_DB`, or
`server/data/simile.db`): the sim time and, for each NPC, their tile and the map it's on, goal,
needs, when they chose the goal and will next decide, and whom they're avoiding. E3's money goes
there too: what each resident holds and the last day rent was paid for, with E4's fridges and each
shop's latest batch. Each entry in E3's ledger is added to a `saved_ledger` table at the first save
after it's made.

## Saving

- **Every 10 real seconds** (`save_every`) while the loop runs. The snapshot is taken between ticks
  and written on a thread, so a tick never waits for the disk. Real seconds rather than sim seconds,
  so a crash loses the same 10 seconds of your time, and the disk sees the same load, at any
  `--speed`.
- **On shutdown**, once the loop has stopped: conversations still going on end there and then with
  B2's `end`, so B3 reflects on them, reflections under way get up to 20 real seconds
  (`reflection_wait`) to finish, and the world is saved. Reflections still going after that are
  logged and lost; L1 calls have no timeout of their own. A crash skips all this, so the village
  resumes from the last autosave.

## Restoring

When the server starts, after B1 has put everyone at home, the clock goes back to the saved time and
each NPC back to their tile, inside or out, and B1's `restore` gives them back their goal, needs and
cooldowns. Their money comes back, and the ledger opens on it, with what was in the fridges and
left of the noodle bar's batch. A save from before the interiors has no maps, and puts everyone on
the village. A save from before money starts everyone with their own `money` from `content/npcs/`,
and the next midnight's rent is their first. A save from before fridges stocks them as a fresh
start does, and the noodle bar cooks a new batch when its keeper next arrives.
Anyone who was walking or talking decides again on their first think, within 5 sim seconds. NPCs who
weren't saved carry on from B1's first start, and saved ones who are no longer in `content/` are
ignored. A save this version can't read is logged and ignored. `simile headless --duration` counts
from the restored time.

## Starting afresh

```bash
cd server && uv run simile reset            # asks first; --yes doesn't
SIMILE_FRESH=1 uv run simile headless       # or SIMILE_FRESH=1 make dev
```

Both forget the saved world, its ledger and everything R2 holds (`MemoryStore.clear`), but keep
the news.
`SIMILE_FRESH=1` does it on every start while it's set.

With `SIMILE_DB=:memory:`, as in every test, nothing outlives the process, so this module does
nothing: no saving, no restoring, and conversations going on at shutdown are left as B2 leaves them.

Every constant is in `PersistenceConfig`.
