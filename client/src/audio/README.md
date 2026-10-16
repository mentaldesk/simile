# Audio

Plays NPC speech from the server's [`audio_chunk`](../../../docs/protocol.md#audio_chunk) frames,
from where the speaker stands.

- Each line gets its own voice (buffer sources → gain → stereo panner), so overlapping lines play
  at the same time.
- A line's chunks are scheduled back to back, 100 ms after its first chunk arrives. A chunk that
  arrives after the audio before it has finished starts another 100 ms buffer. The audio context
  runs at 24 kHz, the TTS rate, so chunks join sample for sample.
- Chunks carry a line id, so the speaker comes from the `line` messages and the lines in `snapshot`
  and `conversation_started`. A chunk that arrives before its line plays unpositioned until the line
  arrives.
- The player's own conversation partner plays at full volume wherever they are, panned up to 0.3
  towards their side. A line is the partner's if its conversation includes the player, as told by
  `snapshot`, `conversation_started` and `conversation_ended`, so a goodbye said as the
  conversation ends still plays at full volume.
- Overheard voices are capped at a third of full volume (about −9.5 dB) within 2 tiles of the
  listener and fall to silence at `SILENT_BEYOND` (5.5), where the server stops voicing them
  (`out_of_earshot`). Pan follows the speaker's direction, up to 0.8 either side. `spatial.ts`
  has both mixes, and `server/tests/voicing/test_client_earshot.py` fails if `SILENT_BEYOND` and
  `out_of_earshot` drift apart.
- Browsers keep audio suspended until the page gets a key press or click. Chunks that arrive before
  then are dropped.

## Positions

The world (C1) tells audio where the speakers and the listener are, in float tiles:

```ts
import { setPositionProvider } from '../audio';

const removeProvider = setPositionProvider({
  positionOf: (entityId) => sprites.get(entityId)?.tile, // undefined if unknown
  listenerPosition: () => playerSprite.tile,
});
// On shutdown: removeProvider();
```

Audio asks every animation frame while a voice is playing, so return where things are right now,
mid-step included. Until a provider is set, or while it returns `undefined` for the speaker or the
listener, voices play unpositioned: full volume, centred.

## Dev harness

Run `npm run dev` in `client/` and open <http://localhost:5173/?audio-harness>. It plays each WAV in
`voice-lab/voices/` from a fixed source, streamed as `audio_chunk` frames through `server.dispatch`
at an uneven pace like the TTS's, with a `line` message first. The first source is the player's
partner, in a conversation the harness starts with `conversation_started`; the rest are overheard.

- Arrow keys move the listener.
- `1`, `2`, … stream that WAV. Space streams them all at once.
- `C` streams each WAV through the real player into an `OfflineAudioContext` and compares what comes
  out with what went in. Any gap or overlap shows up as `GAPS`.

It only loads in development with the `audio-harness` flag, and isn't in production builds.
