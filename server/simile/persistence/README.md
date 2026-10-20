# simile.persistence

The village carries on where it left off. R2's database already keeps relationships, flags,
memories and events as they happen, and which news each NPC has read is their `news` memories.
This module keeps the rest in its own `saved_world` table of the same file (`$SIMILE_DB`, or
`server/data/simile.db`): the sim time and, for each NPC, their tile and the map it's on, goal,
needs, when they chose the goal and will next decide, and whom they're avoiding, with everyone's
open intentions (what they've said they'll do). E3's money goes
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
cooldowns, and `restore_intentions` what they'd said they'd do. Their money comes back, and the
ledger opens on it, with what was in the fridges and left of the noodle bar's batch. A save from
before the interiors has no maps, and puts everyone on today's village. A save from before the
side view (#314) is moved onto it as it loads (below). A save from before intentions
has none. Needs B1 no longer has are dropped. A save from before money starts everyone with their
own `money` from `content/npcs/`, and the next midnight's rent is their first. A save from before
fridges stocks them as a fresh start does, and the noodle bar cooks a new batch when its keeper
next arrives.
Anyone who was walking or talking decides again on their first think, within 5 sim seconds. NPCs who
weren't saved carry on from B1's first start, and saved ones who are no longer in `content/` are
ignored. A save this version can't read is logged and ignored. `simile headless --duration` counts
from the restored time.

## Saves from today's maps

Before #314 the village was isometric, on `village` and its interiors `coffee_shop`, `gallery`,
`maker_space` and `noodle_bar`. No side-view map reuses those ids, so a position saved on one of
them is from then. When it isn't on a loaded map, `restore` moves it to the matching place on the
side-view maps through [`old_cells.csv`](old_cells.csv), a table from each walkable cell of today's
maps, in runs along each row, to a cell on the new ones, with what matched it:

- `spot <id>`, `door <id>` or `interactable <id>`: the spot, the door's end on the same side, or
  the stand, with the same id. Every id is kept on the new maps.
- `location <id>`: the entry of the location it was in, the smallest if there are two.
- `near door <id>` or `near location <id>`: the nearest door, or place, on today's map, and its
  door's end or entry on a street, or for a house, the street in front of its front door.

Nothing else in a save is on the maps: memories, relationships, money, intentions, works, murals by
wall id, paintings by frame id and casts by house id carry over untouched. The table is committed,
so old saves still load once #315 deletes `content/map/`. While both maps exist,
`uv run simile old-cells` rewrites it, and a test fails if it's out of date.

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
