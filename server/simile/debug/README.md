# simile.debug

The server side of the debug overlay (I2). When a client sends `watch_npc`, the overlay sends
`npc_state` for that NPC straight away and then every `INTERVAL` (0.5) real seconds, until a
`watch_npc` with `null`. Nothing is sent while nobody is watching, and `simile headless` doesn't
start it.

The state is read on the event loop, outside the tick, from B1's `Behaviour`, B2's
`ConversationEngine` and R2's `MemoryStore` (`Village.npc_state`). One NPC is watched for the whole
server, not per client: the hub doesn't say which client a message came from.

## The state

| Key | |
|---|---|
| `name`, `occupation`, `time` | Who they are, and the sim time the state is from. |
| `goal`, `activity`, `target`, `walking`, `paused`, `since`, `until`, `needs`, `options`, `bedtime`, `wake` | B1's `state(npc)`. |
| `values` | Their top 5 core values, highest first. |
| `relationships` | Up to 12 they know, most familiar first: `about`, `like`, `trust`, `respect`, `familiarity` (R1 `as_of` now) and up to 4 `flags` (`kind`, `description`, `open`), open ones first. |
| `memories` | What R2's `recall` gives them now, up to 6: `kind`, `content`, `timestamp`, `salience`, `valence`. |
| `conversation` | `null`, or B2's `state(npc)` (`id`, `talking_to`, `engagement`, `facing`, `leaving`) with the last 12 `lines` (`speaker`, `text`, `timestamp`). |

Text is cut at 280 characters, so a state stays well under 16 KB.
