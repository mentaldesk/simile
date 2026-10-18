# simile.library

The server side of the character library: the premade characters in `content/characters/pool/`,
the player's own characters, and the player's look. P8's creator and P9's new-world screen use it.

## Routes

| Route | What it does |
|---|---|
| `GET /api/characters` | Every character, premade ones first and then the player's, each by name. |
| `GET /api/characters/{id}` | One character. 404 if there's none. |
| `POST /api/characters` | Saves a new player character (201). It gets a new id if a player character has its id. |
| `PUT /api/characters/{id}` | Replaces a player character. The id can't change. |
| `DELETE /api/characters/{id}` | Deletes a player character and its clip (204). |
| `POST /api/characters/generate` | Writes a draft from a partial brief, streamed (below). Saves nothing. |
| `POST /api/characters/reroll` | Writes sections of a character again, streamed. Saves nothing. |
| `GET /api/characters/{id}/export` | A player character as one file (below). |
| `POST /api/characters/import` | Saves the character in an exported file as a player character (201). |
| `GET /api/player`, `PUT /api/player` | The player's look, as `{"appearance": {...}}`. Until it's set, the built-in look from `simile.art.characters`. |

The server sets `source` (always `player`), `created`, `updated` and `version` on everything it
saves, and `voice.reference_clip` (see *Voice clips*). A POST starts at version 1, and each PUT adds
one.

Premade characters are read-only. A PUT, DELETE, reroll, export or POST of one gets 403. Bad input
gets 422 with `{"error": reason}`, and a body over 256 KB (12 MB for an import) gets 413.

## Generating

`generate` takes P3's `Brief` as JSON. Each `Character` field it sets is locked, even when it's set
to null, and so are its `values`, `latent` traits and census `facts`. `{}` rolls a whole character.
The draft's id is never one the library already has.

`reroll` takes `{"character": {...}, "sections": ["biography"]}`, with P3's sections: `name`,
`identity`, `values`, `past`, `biography`, `hooks`, `voice` and `appearance`. Everything outside
them is kept, the id too, and `version` goes up by one.

Both answer 200 with `application/x-ndjson`, one JSON object per line:

- `{"type": "call", "purpose": "character-biography"}` when a Claude call starts: the biography,
  then `character-critic`. A reply that doesn't fit the schema is asked for again in another call.
- `{"type": "text", "text": "..."}` for each piece of that call's reply, the JSON as Claude writes it.
- Last, `{"type": "done", "character": {...}, "suggestions": [...], "notes": [...], "warnings":
  [...]}`, or `{"type": "error", "error": "..."}`.

`suggestions` are the critic's changes, `{"field": "past[2]", "current": "...", "suggested": "..."}`,
which only the player applies. `warnings` says when the draft is a near-copy of a library
character. That check runs a local embedding model (fastembed), which loads, and downloads the
first time, after the first draft is written. It never loads at startup.

Leaving early stops the Claude call. Two can run at once, and a third gets 429.

**A reroll draws the census facts and the tension again.** `Character` doesn't keep the class,
education, family, health, secret, wound or want the biography was written from, so P3 draws them
afresh on every reroll. Rerolling `biography` alone gives a backstory with a new secret, while the
kept `past` and `hooks` still tell the old one. Reroll `past`, `biography` and `hooks` together for
a new story that holds together. `name`, `voice` and `appearance` can be rerolled on their own.

## Where it keeps things

Player characters live in the data directory, beside the database, and never in `content/`. The
library refuses a directory there.

```
$SIMILE_LIBRARY, or library/ beside $SIMILE_DB (server/data/library/ by default)
  characters/<id>.json   a player character
  clips/<id>.wav         its reference clip, if it has one
  player.json            the player's look
```

With `SIMILE_DB=:memory:` it's `server/data/library/`. A file in `characters/` that isn't a player
character with that id is logged and skipped.

## Voice clips

A premade character's `voice.reference_clip` is relative to the repository root, as `Voice` says.
**A player character's is relative to the library directory:** it's `clips/<id>.wav`, or null. The
library sets it, whatever a request or an imported file says. So moving the data directory, or
pointing `$SIMILE_DB` somewhere else, keeps each clip with its character.

For P11 (#189), casting and anything else that reads a clip:

- `library_of(app).clip(character)` is the path of its clip, premade or not.
- `library_of(app).save_clip(id, wav)` gives a player character a clip, once it decodes, and bumps
  its `version`. A voice picked from `content/voices/` goes in this way too, as a copy.
- Editing `voice.reference_line` keeps the clip. Checking that the two still match is P11's.

## Export and import

An export is a zip of `character.json`, with `voice.reference_clip` set to `voice.wav`, and
`voice.wav` if the character has a clip. The sprite isn't in it, because it's drawn again from
`appearance`. Only player characters export: copying premade ones isn't allowed yet.

An import is refused, with the reason, when:

- it's over 12 MB, or isn't a zip, or is damaged
- it holds anything but `character.json` and `voice.wav`, or has a name twice
- a file in it is encrypted, or compressed any way but deflate
- `character.json` is over 256 KB or isn't a valid `Character`
- `voice.wav` is over 10 MB or 60 seconds, or doesn't decode in full as a WAV file

Nothing in the file becomes a path. The two files are read into memory by name, the id has to be a
plain slug, and `reference_clip` is replaced. The character is saved as a player character, with a
new id if its own is taken (`wren_abernethy` becomes `wren_abernethy_2`). It keeps its `created`,
`updated` and `version`, with the timestamps capped at now. Checking the voice itself, its
transcript and accent, is P11's.

## From other modules

`library_of(app)` is the server's `Library`, created on first use: `characters()`, `get(id)`,
`create(data)`, `update(id, data)`, `delete(id)`, `clip(character)`, `save_clip(id, wav)` and
`player()`. It raises `NotFound`, `ReadOnly` for a premade character, and `Refused` with the reason
for bad input. Each reads and writes files, so call it from a thread in async code.
