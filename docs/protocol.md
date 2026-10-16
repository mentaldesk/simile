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

- Field names are `snake_case` on both sides.
- Every field is always present. Optional values are `null`, never missing.
- Timestamps are sim time: ISO 8601 in UTC, e.g. `"2026-03-14T09:10:03Z"`. UTC is village time.
- A **position** is `{"x": 4.5, "y": 6}` in tiles, measured like F2's `Tile`: `(4, 6)` is
  standing on tile (4, 6), and fractions are part-way between tiles while walking.
- Entity ids are F2 `Id`s. The player is always `"player"`.
- A message the server can't parse is logged and ignored. The connection stays open.

## Server → client

### `snapshot`

The whole world. The server sends it first on every connection, including reconnections, and the
client replaces whatever it had.

| Field | Type | |
|---|---|---|
| `time` | timestamp | Sim time now. |
| `map_id` | string | Which map to load, e.g. `"village"`. |
| `entities` | `Entity[]` | Every NPC and the player: `id`, `kind` (`"npc"` or `"player"`), `name`, `position`. |
| `conversations` | `Conversation[]` | Conversations still going on, with their lines so far (F2 `Conversation`). |

Until the sim has a world of its own, the snapshot comes from F2's fixtures in
`server/tests/fixtures/`: the NPCs at their front doors, the player in the town square, and the one
conversation that hasn't ended. Its `time` is the sim clock's.

### `entity_moved`

`entity_id`, `position`. There's no facing: the client works it out from the direction of travel.

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

### `player_say`

`text` (not empty) and `target`, the id of the NPC the player is talking to.

### `watch_npc`

`npc_id`: the NPC whose [`npc_state`](#npc_state) the debug overlay wants, or `null` to stop. The
client sends it when the overlay opens on an NPC or switches to another, and with `null` when the
overlay closes. Each one replaces the last, so there's one watched NPC at most. Nothing is watched
until the client sends one, so it sends it again after each `snapshot`: a reconnection may be to a
restarted server.

## Sim events

`server/simile/protocol/lifespan.py` forwards the sim's bus events to every client:

| Sim event | Message |
|---|---|
| `EntityMoved` | `entity_moved` |
| `ConversationStarted` | `conversation_started` |
| `LineSpoken` | `line`, with `voiced` `false` until earshot voicing (I1) exists |
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
hub.snapshot = world_snapshot  # returns a SnapshotMessage; the fixtures at sim time by default
```

- `broadcast` queues the message for every connected client and returns at once, so it's safe to
  call from a tick or an event bus handler. Each client gets its messages in the order they were
  broadcast, after its snapshot.
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
