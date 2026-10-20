# Client–server protocol

The client and the sim server talk over one WebSocket at `/ws`. In development the client connects
to its own origin and Vite proxies `/ws` to the server on port 8000.

- **Text frames** carry one JSON message each, with a `type` field naming the message.
- **Binary frames** go from the server to the client only, and are always an [`audio_chunk`](#audio_chunk).

The server is authoritative, except for the player's position, which the client sends.

The message models are in [`server/simile/protocol/messages.py`](../server/simile/protocol/messages.py),
built on the F2 domain schemas in `server/simile/schema/`. The TypeScript types in
[`client/src/net/protocol.ts`](../client/src/net/protocol.ts) are generated from them.

## Conventions

The village is drawn from the side (#306): a map per street and a map per floor. The isometric
maps it replaced are gone (#315), but some defaults still name their village, `"village"`, and the
interiors' ids; this document says where.

- Field names are `snake_case` on both sides.
- Every field is always present. Optional values are `null`, never missing. The exceptions are a
  position's `map`, an entity's `pose` and `facing`, an article's `long_summary` and a wall's
  `map`, below.
- Timestamps are sim time: ISO 8601 in UTC, e.g. `"2026-03-14T09:10:03Z"`. UTC is village time.
- A **position** is `{"x": 4.5, "y": 6, "map": "village"}` in tiles, measured like F2's `Tile`:
  `(4, 6)` is standing on tile (4, 6), and fractions are part-way between tiles while walking.
  `map` is the map it's on: `"village"`, or an interior's id, such as `"coffee_shop"`.
  - The server always sends `map`. A client may leave it out of `player_move`, which means the
    village, so clients that predate interiors keep working.
  - So the generated TypeScript has `map?: string`, and the client can keep using `Position` as a
    plain point. Read it as `position.map ?? 'village'`. K5 (#171) may tighten the type.
  - On a side-view map, x runs along the street and y counts rows down from the top. `map` is a
    street's or a floor's id. A tile is about 1.1 m, as on the isometric maps, so distances in
    tiles mean the same in both. A resident stands on a cell with ground under it, or on a
    climbable cell (stairs or a ladder), and fractions are mid-step or mid-climb.
- An entity's **pose** is what it's doing: `"standing"`, `"walking"`, `"sitting"`, `"reading"`,
  `"working"`, `"looking"`, `"climbing"` (on stairs or a ladder) or `"riding"` (in a lift). Its
  **facing** is the way it faces on the map, x east and y south: `"east"`, `"south_east"`,
  `"south"`, `"south_west"`, `"west"`, `"north_west"`, `"north"` or `"north_east"`, in order of
  angle from east round through south. Both are F2 types, `Pose` and
  `Facing` in `server/simile/schema/world.py`, so the world and the sim's events can use them too.
  - On a side-view map, the three eastward facings draw them facing right and the three westward
    ones left. `north` draws their back, looking into the picture (at a mural or a terminal), and
    `south` their front.
  - The server always sends both. Without them an entity is standing, facing south-east. As with
    `map`, the generated TypeScript has them optional: read `entity.pose ?? 'standing'` and
    `entity.facing ?? 'south_east'`.
  - Sitting, reading, working and looking come with #264's spots, which face along the grid:
    `north`, `east`, `south` or `west`.
  - The server doesn't track the player's, so the player's entity is always `standing`, facing
    `south_east`.
- Entity ids are F2 `Id`s. The player is always `"player"`.
- The maps aren't sent: the client bundles the village and its interiors as Tiled maps. F2's
  `Door` and `Interactable` in `server/simile/schema/world.py` describe their doors and the things
  you can use inside, and a `Location` says which map it's on. Interactable ids go over the wire
  only in [`paintings`](#paintings).
  - A `Door`'s `kind` is `"door"`, `"stairs"`, `"ladder"` or `"lift"`, and it's left out for a
    door. A door joins a street or the village (`outside`) and a building's ground floor
    (`inside`), or two streets, with `outside` on the street whose id comes first alphabetically:
    `"high_street"` before `"mill_lane"`. Stairs, a ladder or a lift join two floors' maps, with
    `outside` the lower and `inside` the upper. Stairs and ladders within one map aren't doors:
    they're climbable cells on the map.
  - No two links share an end tile. The client finds a link from its end tile, and the server's
    `door_ends` (`server/simile/world/paths.py`) keys links by their end tiles, so it would drop
    one of two that share a tile. A lift serving three or more floors, or two flights of stairs
    meeting on a landing, has a separate end tile on the middle floor for each link. #308's map
    loader rejects a map that breaks this.
  - A `Location`'s `map`, `area` and `entry` are where you arrive. On side-view maps its `floors`
    are its building's other floors, each a `MapArea` (a `TileArea` with a `map`) on a map of its
    own. It's left out when empty.
- A message the server can't parse is logged and ignored. The connection stays open.

## Server → client

### `snapshot`

The whole world. The server sends it first on every connection, including reconnections, and the
client replaces whatever it had.

| Field | Type | |
|---|---|---|
| `time` | timestamp | Sim time now. |
| `map_id` | string | The map the player starts on, e.g. `"village"`, or on side-view maps a street's id. |
| `entities` | `Entity[]` | Every NPC and the player: `id`, `kind` (`"npc"` or `"player"`), `name`, `position`, `pose` and `facing`. Each position has its own `map`. |
| `conversations` | `Conversation[]` | Conversations still going on, with their lines so far (F2 `Conversation`). |

Until the sim has a world of its own, the snapshot comes from F2's fixtures in
`server/tests/fixtures/`: the NPCs at their front doors, the player in the town square, and the one
conversation that hasn't ended. Its `time` is the sim clock's.

### `clock`

`time` (sim time) and `speed` (sim seconds per real second, more than 0). The server sends it
straight after every `snapshot`, when the speed changes, and as each sim minute starts, so the client
can keep its own clock in between: sim time now is about `time` + `speed` × the real seconds since
it arrived.

### `entity_moved`

`entity_id`, `position`, `pose` and `facing`. On its way somewhere an entity is `walking`, facing
the way it's going, so the client can still work the facing out from the direction of travel. When
it settles, say at a seat, an `entity_moved` gives the pose and facing it stays in. That can be at
the position it's already at, so the pose or facing can change on its own.

An entity going through a door arrives as an `entity_moved` onto the other map, and the client
snaps it there rather than walking it. The `entity_moved` before that is the door's tile on the map
it's leaving, a step's time earlier.

On a side-view map:

- An entity on a run of stairs or ladder cells within one map is `climbing`.
- One taking stairs, a ladder or a lift to another floor's map gets an `entity_moved` at the
  link's end on the map it's leaving, `climbing` or `riding`. It holds that for the climb or ride,
  then arrives on the other map as through a door.
- The client finds the link from that end tile, which no other link shares, and plays a climb or
  a ride by its `kind`.

### `conversation_started`

`conversation`: an F2 `Conversation`, usually with no lines yet.

### `conversation_ended`

`conversation_id`, `ended` (timestamp).

### `line`

`line`: an F2 `Line` (`id`, `conversation_id`, `speaker`, `text`, `timestamp`, and `duration`, the
estimated seconds to say it). `voiced`: whether `audio_chunk` frames will follow for `line.id`.
When it's `false`, show the text for `duration` seconds.

### `npc_state`

`npc_id`, and `state`, an open JSON object for the debug overlay (I2). Each module puts its own keys
in `state`, for example `{"goal": "coffee_shop"}`. The keys aren't part of the contract and can grow
without changing the protocol. The server sends it only for the NPC the client is watching
([`watch_npc`](#watch_npc)).

### `news`

`articles`: the articles at the news terminals, newest first. Each has its `news_id` (the F2
`NewsItem` id), `title`, `source` (the feed's display name, e.g. `"The Atlantic"`, or empty),
`summary` (plain text), `long_summary`, `url` (the original article) and `read`, whether the player
has read it. `long_summary` is three or four short paragraphs separated by blank lines, at most 4,000
characters. It's left out when there isn't one, and the client shows `summary` instead.
The server sends it in reply to [`list_news`](#list_news) and [`read_news`](#read_news), and the
client shows the latest one. Hub subscribers don't know which connection a message came from, so the
reply goes to every client, which is fine with one player. A client ignores `news` while its news
panel is closed.

### `works`

`works`: residents' writing at the terminals, newest first. Each has its `work_id` (the F2 `Work`
id), `title`, `artist` (`id` and `name`), `form`, `text` (the piece itself, line breaks and all),
`statement` (the artist on what it's saying), `created` (sim time) and `read`, whether the player
has read it. `form` is the work's own, copied from the artist's craft when they made it, so it
doesn't change if their craft does. The server sends it in reply to [`list_works`](#list_works) and
[`read_work`](#read_work), to every client, as with `news`.

`notices`: the notice board beside the works, newest first. A notice is a shopkeeper's offer, event
or invitation, not a work, so it's never in `works`. Each has its `notice_id`, `title`, `text`,
`poster` (`id` and `name`) and `created` (sim time). It's empty while nobody has put one up.

### `murals`

`walls`: every wall that takes a mural, painted or not. The server sends it after the `snapshot`
and `clock` on connect, and again to everyone whenever a mural changes, and the client replaces
what it had.

| Field | Type | |
|---|---|---|
| `id` | string | The wall's id. |
| `map` | string | The map it's on, such as a street on side-view maps. Left out on the village, so it was absent from every wall on the isometric maps: read it as `wall.map ?? 'village'`. |
| `x`, `y` | integer | The building's tile at the west end of a south face or the north end of an east face: on its south row or east column, whatever storeys the mural spans. The face runs along that tile's south edge (`y + 1`) or east edge (`x + 1`). On a side-view map, the standing cell at the wall's west end, on the street in front of it. |
| `width` | integer | Tiles, running east from (`x`, `y`) for a south face, or south for an east face. |
| `face` | `"south"` or `"east"` | Which way the wall faces. Every wall on the side-view maps faces `"south"`, the camera; `"east"` was only on the isometric village. |
| `bottom`, `top` | number | The mural's lower and upper edges, in storeys up from the ground there: `0` is the ground and `1` the top of the ground floor. Fractions are fine, and `top` is above `bottom`. |
| `mural` | `Mural` or `null` | What's painted there now, or `null` while it's blank. |

A `Mural` has its `work_id`, `title`, `artist` (`id` and `name`), `statement`, and `image`, the URL
of its picture, `/api/works/<work_id>.png`. A new mural is a new work with its own id, so the URL
changes when the wall is painted over. A mural's F2 `Work.wall` is the wall's `id`.

### `paintings`

`frames`: every `painting` interactable, hung or empty. As with `murals`, the server sends it after
the `snapshot` and `clock` on connect, and again to everyone whenever a painting changes, and the
client replaces what it had. Clients that predate the gallery ignore it.

| Field | Type | |
|---|---|---|
| `id` | string | The F2 `Interactable`'s id, e.g. `"painting_1"`. |
| `map` | string | The map the interactable is on, e.g. `"gallery"`. |
| `painting` | `Painting` or `null` | What hangs there now, or `null` while the frame is empty. |

A `Painting` has its `work_id` (an F2 `Work` with the `painting` medium), `title`, `artist` (`id`
and `name`), `statement`, and `image`, the URL of its picture on the sim server. The client uses
`image` as given. Each work has its own URL, so it changes when a new painting replaces one. A
painting's F2 `Work` has no `wall` and doesn't say where it hangs.

### `audio_chunk`

A binary frame: part of a line's audio, as Qwen3-TTS produces it. A 12-byte header, then the
samples. All integers are little-endian.

| Offset | Size | Type | Field |
|---|---|---|---|
| 0 | 4 | uint32 | Line id: the `line.id` of the `line` message it voices. |
| 4 | 4 | uint32 | Sequence number: 0 for a line's first chunk, then 1, 2, … |
| 8 | 1 | uint8 | Flags. Bit 0 is set on the line's last chunk. The other bits are 0. |
| 9 | 3 | | Reserved, 0. Keeps the samples 4-byte aligned. |
| 12 | 2 × n | int16[n] | Samples: 24 kHz, mono, 16-bit signed PCM. n may be 0. |

The frame is always an even number of bytes. Senders send the `line` message before any of its
chunks, and its chunks in sequence order. A line's audio may stop early, for example when the player
walks out of earshot, so its last chunk can be empty, with only the flag set.

Example: line 7, chunk 2, last, samples 1, -2, 32767:

```
07000000 02000000 01000000 0100 feff ff7f
```

`AudioChunk.encode` and `.decode` in `server/simile/protocol/audio.py`, and `encodeAudioChunk` and
`decodeAudioChunk` in `client/src/net/audio.ts`, both test against these bytes.

## Client → server

### `player_move`

`position`. The client sends the player's position as it changes, and the server trusts it.
Going through a door is a `player_move` with the other map's `map`. A position without `map` puts
the player on the village. Side-view maps have no village, so there the server ignores a position
without `map`, as it ignores a position on any map it doesn't know.

### `player_say`

`text` (not empty) and `target`, the id of the NPC the player is talking to.

### `watch_npc`

`npc_id`: the NPC whose [`npc_state`](#npc_state) the debug overlay wants, or `null` to stop. The
client sends it when the overlay opens on an NPC or switches to another, and with `null` when the
overlay closes. Each one replaces the last, so there's one watched NPC at most. Nothing is watched
until the client sends one, so it sends it again after each `snapshot`: a reconnection may be to a
restarted server.

### `list_news`

No fields. The client sends it when the player opens the news at a terminal, and the server
replies with [`news`](#news).

### `read_news`

`news_id`: the article the player reads. The server stores it as the player's own `news` memory,
with its `news_id`, and replies with [`news`](#news), where it's now `read`. An unknown `news_id`
stores nothing, and still gets a `news` reply.

### `list_works`

No fields. The client sends it when the player opens residents' writing at a terminal, and the
server replies with [`works`](#works).

### `read_work`

`work_id`: the work the player reads. The server stores it as the player's own `work` memory, with
its `work_id`, and replies with [`works`](#works), where it's now `read`. An unknown `work_id`
stores nothing, and still gets a `works` reply.

## Sim events

`server/simile/protocol/lifespan.py` forwards the sim's bus events to every client:

| Sim event | Message |
|---|---|
| `EntityMoved` | `entity_moved` |
| `ConversationStarted` | `conversation_started` |
| `LineSpoken` | `line`, with `voiced` from `app.state.voiced(line)` while earshot voicing (I1) runs, else `false` |
| `ConversationEnded` | `conversation_ended`, with the clock's time if the conversation's `ended` isn't set |

So most modules publish on the bus rather than calling the hub.

## Using it on the server

`hub_of(app)` returns the `Hub` for the running server, creating it on first use, so any module can
get it from its lifespan whatever the lifespan order.

```python
from simile.protocol import EntityMovedMessage, PlayerSayMessage, Position, hub_of

hub = hub_of(app)
hub.broadcast(EntityMovedMessage(entity_id="mei", position=Position(x=4.5, y=6)))
hub.broadcast(audio_chunk)  # an AudioChunk goes out as a binary frame
unsubscribe = hub.subscribe(PlayerSayMessage, on_player_say)
stop = hub.greet(current_murals)  # returns a server message, or None to send nothing
hub.snapshot = world_snapshot  # returns a SnapshotMessage; the fixtures at sim time by default
```

- `broadcast` queues the message for every connected client and returns at once, so it's safe to
  call from a tick or an event bus handler. Each client gets its messages in the order they were
  broadcast, after its snapshot.
- The protocol lifespan sets `hub.clock`, which sends the `clock` after each snapshot. Without the
  lifespan, a new client gets only the snapshot.
- `greet(greeter)` adds a message for each new client, such as `murals` or `paintings`. The hub
  calls every greeter after the snapshot and clock, in the order they were added, and sends what
  each returns unless it's `None`, before any broadcast. One that raises is logged and skipped. Call
  the returned `stop()` when your lifespan exits.
- Subscribers to client messages are called on the event loop, in the order they subscribed, and
  mustn't block. One that raises is logged and doesn't affect the others.
- Call the hub from the event loop. From a worker thread, such as a TTS model running in one, use
  `loop.call_soon_threadsafe(hub.broadcast, chunk)`.

## Using it on the client

```ts
import { server } from '../net';

server.on('snapshot', (snapshot) => world.reset(snapshot));
server.on('entity_moved', ({ entity_id, position }) => world.move(entity_id, position));
server.on('audio_chunk', ({ lineId, sequence, last, samples }) => audio.play(lineId, samples));
server.send({ type: 'player_move', position: { x: 14, y: 12.5 } });
```

- `server.on(type, handler)` takes any server message `type` or `'audio_chunk'`, types the handler's
  argument to match, and returns a function that unsubscribes.
- `server` connects to `/ws` on the page's origin when `client/src/net/` loads, at startup.
  Messages aren't replayed, so subscribe when your module loads. A scene that starts later should
  read state that a module-level subscriber keeps.
- Under vitest it doesn't connect, so tests can import it. `server.dispatch(text)` or
  `server.dispatch(arrayBuffer)` handles a frame as if the server had sent it, which also suits dev
  harnesses, and `vi.spyOn(server, 'send')` sees what a module sends.
- After a disconnection it reconnects with backoff (250 ms, doubling, at most 5 s), and the server
  sends a fresh `snapshot`.
- `send` returns `false` and drops the message while disconnected.

## Changing a message

1. Change the models in `server/simile/protocol/messages.py`. Changes to the protocol go in their
   own PR.
2. `cd server && uv run simile protocol` writes `server/simile/protocol/protocol.schema.json`.
3. `cd client && npx vitest run src/net/protocol.test.ts -u` regenerates `client/src/net/protocol.ts`.
4. Update this document, and commit all of them.

CI fails if either generated file is out of date: `server/tests/protocol/test_export.py` checks the
JSON Schema, and `client/src/net/protocol.test.ts` checks the TypeScript.
