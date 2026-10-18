# simile.worlds

P9: the server side of the title menu's *New world*. It casts library characters (P4) into a new
world, in a data directory of its own. Today's village, its save and `content/` are never touched.

## Routes

| Route | What it does |
|---|---|
| `GET /api/worlds` | `{"current": {...}, "houses": 10}`: the world the server is running and how many houses the village has. |
| `POST /api/worlds/draw` | Draws a cast without making it: `{"residents": [ids]}`, the picks first. Writes nothing. |
| `POST /api/worlds` | Makes a new world (201) and reports it. |

Both POSTs take:

```json
{"count": 6, "picks": ["kamran_malik"], "pins": [{"kind": "rival", "actor": "kamran_malik", "target": "chloe_clarke"}]}
```

`count` is how many residents, at most one per house. `picks` are cast as given, and so is everyone
pinned. The rest are drawn the way `simile cast` draws them. Any library character can be picked,
the player's own too. An optional `seed` repeats a draw. A request casting can't make gets 422
with `{"error": reason}`: an unknown id, someone picked twice, more picks than `count`, more
residents than houses, or a pin that isn't a bond between two residents. A body over 16 KB gets 413.

`current` has the world's `name` ("Today's village" for the residents in `content/npcs/`), whether
it's that `default` village, its data directory and its residents.

## Where new worlds live

`$SIMILE_WORLDS`, else `server/worlds/`, which is gitignored. Each new world gets a folder named
after the time it was made, `server/worlds/2026-10-18-1432/`, with the cast in `cast/` and, once
the server runs it, the save in `simile.db`. Nothing is ever replaced, so calling it again makes
another folder. A player character's voice clip is copied into the world's `clips/`. A folder in
`server/data/` or `content/` is refused with 409, as casting refuses it.

## Starting a new world

The server runs one world at a time, and it doesn't switch worlds while it runs: every module's
startup hook would have to run again. So `POST /api/worlds` answers with the command that starts
the server on the new world, and the menu shows it:

```bash
SIMILE_DB=worlds/2026-10-18-1432/simile.db SIMILE_LIBRARY=data/library make dev
```

Run it from the repo root, after stopping `make dev`. The paths are relative to `server/`, where the
server runs. `SIMILE_LIBRARY` keeps the player's characters, whose library otherwise sits beside
`$SIMILE_DB`. Add `SIMILE_VOICE=1` or anything else as usual. The same command comes back to that
world later, and a plain `make dev` opens today's village.

## What's missing

The report lists, for each resident, what they still need:

- `voice`: no reference clip yet, so their lines show as text (P4's *Voices*)
- `sprite`: no sprite in `content/art/characters/`, so the client draws a stand-in
