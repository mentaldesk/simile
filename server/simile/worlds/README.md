# simile.worlds

The server side of the title menu's worlds. P9 casts library characters (P4) into a new world, in
a data directory of its own; today's village, its save and `content/` are never touched. P29 lists,
opens, renames and deletes worlds, switching the running server from one to another.

## Routes

| Route | What it does |
|---|---|
| `GET /api/worlds` | `{"current", "houses", "worlds", "supervised"}`: the world the server is running, how many houses the village has, every world, and whether a supervisor runs the server, so it can switch worlds. |
| `POST /api/worlds/draw` | Draws a cast without making it: `{"residents": [ids]}`, the picks first. Writes nothing. |
| `POST /api/worlds` | Makes a new world (201) and reports it. With `"open": true` it opens it too, and answers `"opening": true`. Without a supervisor it doesn't open it, and answers `"opening": false`. |
| `GET /api/worlds/{id}` | One world, as in the list. |
| `PATCH /api/worlds/{id}` | Renames it: `{"name": "Ash Lane"}`, 1 to 64 characters. Answers with the world. |
| `DELETE /api/worlds/{id}` | Deletes its folder (204). 409 for today's village and for the world running. |
| `POST /api/worlds/{id}/open` | Switches the server to it (202, `{"id", "opening": true}`). 200 with `"opening": false` if it's running already, 409 without a supervisor (below). |

An unknown id gets 404. Each world in `worlds`:

```json
{"id": "2026-10-18-1432", "name": "Ash Lane", "default": false, "running": true,
 "made": "2026-10-18T14:32:05+13:00", "played": "2026-10-19T09:10:00Z",
 "day": 3, "time": "2026-10-20T15:42:10Z", "player": "Visitor", "residents": 6}
```

Today's village is `"id": "today"`, first and `"default": true`; the others follow, newest first.
`name` is the folder's name until it's renamed. `day` and `time` are where its save is, from 1 on the
first day anything happened in it, and null before it's first saved. `played` is null if it's never
been opened. Worlds have no player of their own yet, so `player` is the configured name for all.

Both POSTs that make a cast take:

```json
{"count": 6, "picks": ["kamran_malik"], "pins": [{"kind": "rival", "actor": "kamran_malik", "target": "chloe_clarke"}]}
```

`POST /api/worlds` also takes an optional `name` and `open`.

`count` is how many residents, at most one per house. `picks` are cast as given, and so is everyone
pinned. The rest are drawn the way `simile cast` draws them. Any library character can be picked,
the player's own too. An optional `seed` repeats a draw. A request casting can't make gets 422
with `{"error": reason}`: an unknown id, someone picked twice, more picks than `count`, more
residents than houses, or a pin that isn't a bond between two residents. A body over 16 KB gets 413.

`current` has the world's `id` (null if `$SIMILE_DB` isn't one of the worlds), its `name` ("Today's
village" for the residents in `content/npcs/`), whether it's that `default` village, its data
directory and its residents.

## Where new worlds live

`$SIMILE_WORLDS`, else `server/worlds/`, which is gitignored. Each new world gets a folder named
after the time it was made, `server/worlds/2026-10-18-1432/`, with the cast in `cast/` and, once
the server runs it, the save in `simile.db`. Nothing is ever replaced, so calling it again makes
another folder. A player character's voice clip is copied into the world's `clips/`. A folder in
`server/data/` or `content/` is refused with 409, as casting refuses it. `worlds.json` beside them
keeps their names, when each was made and last played, which was played last, and which the menu
asked to open next. If it can't be read, it's moved aside to `worlds.json.bad` and started afresh.

## Switching worlds

`make dev` and `./run.sh` run `simile worlds serve`, a small supervisor that runs `simile serve` in
a process of its own. Opening a world records it as the one to open next, then asks the supervisor
(`SIGUSR1` to `$SIMILE_SUPERVISOR`) to restart the server: the server shuts down as it does on
Ctrl-C, saving the world, and starts again on the new world's save. Once it's up, its `running`
hook records it as the last world played. Nothing in memory survives the switch, so no module needs
to know about it. With `--reload`, uvicorn's reloader is the process the supervisor restarts.

The server runs in a session of its own, so Ctrl-C reaches only the supervisor. It sends the server
SIGTERM, which shuts it down and saves. Ctrl-C again sends SIGINT to the server's whole process
group, the worker under the reloader too, which stops it without waiting.

The switch takes a second or two, as long as the server takes to start. Meanwhile requests fail and
the client's WebSocket reconnects by itself, as it does after any restart, and gets the new world's
snapshot. The menu that opened the world polls `GET /api/worlds` until `current.id` is the new one,
then reloads the page.

A plain `make dev` opens the last world played, or today's village if there's none or it's been
deleted. A world that fails to start isn't recorded as played, so the next `make dev` opens the one
before it. If a world that used to start stops starting, `SIMILE_DB=data/simile.db make dev` opens
today's village instead, and the menu can open another from there. `$SIMILE_DB` set when it starts
opens that save instead, and `SIMILE_FRESH=1` starts the world it opens afresh; neither carries over
to the worlds opened after it. Each world uses the player's character library, `$SIMILE_LIBRARY` or
`server/data/library/`.

`simile serve` on its own runs only the world `$SIMILE_DB` names, and opening a world there gets
409. `POST /api/worlds` still reports the `restart` command that starts the server on the new world
without the menu, which works with either.

## What's missing

The report lists, for each resident, what they still need:

- `voice`: no reference clip yet, so their lines show as text (P4's *Voices*)
- `sprite`: no doll in `content/dolls/`, so the client draws a stand-in, another resident's doll
