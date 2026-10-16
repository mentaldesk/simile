# simile.voicing

Voices the conversations the player can hear, in each NPC's own voice (README: *Only voicing what
the player can hear*). It runs only when V1 does (`SIMILE_VOICE=1` with the voice extra, see
[`voice/README.md`](../voice/README.md)). Otherwise nothing here starts and every `line` goes out
with `voiced: false`.

## Startup

The `running` hook registers every NPC with a `voice.reference_clip` with V1, about 0.15 s each on
an M2 Max, then follows the bus and ticks on the sim loop.

## Earshot

- A conversation is in earshot once the player is within `earshot` (4 tiles) of one of its NPCs,
  and stays in it until they're further than `out_of_earshot` (5.5) from all of them. Nothing is in
  earshot while no client is connected. At the client's zoom the screen shows about 4 tiles above
  and below the player, so a conversation starts being voiced only once it's on screen.
- Coming into earshot voices the next line on, including one already written and waiting for its
  turn. Leaving it cuts the line being said and drops the rest.
- The player's own conversation is always in earshot: B5 ends it beyond 6 tiles.
- At most `max_voiced` (2) conversations are voiced at once, the player's included. V1 makes speech
  about 2.6x faster than it plays on an M2 Max: with two conversations it ran up to 2 s behind the
  bubbles, with three up to 13 s, and dropped lines. Another conversation coming into earshot stays
  unvoiced, from its next line on, until one of them ends or leaves earshot. The player starting a
  conversation silences the farthest voiced one instead.
- C2 draws bubbles within the same 4 tiles, so the player hears the conversations whose bubbles they
  see. C3 plays the player's own partner at full volume. It caps an overheard voice at a third
  (about −9.5 dB) within 2 tiles and fades it to silence at 5.5, so it's about −24 dB at 4 tiles.
  `server/tests/voicing/test_client_earshot.py` keeps both sides' distances the same.

## Lines

- A line starts generating on `LineDrafted`: a line ahead for NPC conversations, and as soon as each
  sentence has streamed for the player's. B2 and B5 pace every line by its word count either way,
  so a conversation lasts as long whether it's voiced or not.
- An NPC conversation's lines go to V1 whole rather than split into sentences, because B2 hands
  over each line once it's fully written. B5 already makes each sentence of a reply its own line.
- The protocol forwarder sends `voiced: app.state.voiced(line)` with each `line`: whether audio is
  being made for it. Its `audio_chunk`s follow the `line` message, and the last one is header-only
  with the last flag set, even when the line is cut short.
- A line's chunks wait until the line before it in the same conversation has finished playing on
  the client, so speakers never talk over each other. The server mirrors C3's timeline to know
  when that is: a line plays 100 ms after its first chunk arrives.
- Within a line, chunks go out `lead` (0.5 s) ahead of what the client is playing, so a cut line
  falls silent within about 0.8 s.
- When the player says something, the NPC's audio stops and the sentences they hadn't reached are
  dropped. So are lines left unspoken when a conversation ends, while the line being said finishes.
- Lines in the player's conversation are `Priority.PLAYER`, the rest `OVERHEARD`. V1 finishes the
  sentence it's on before the next, so a player sentence restarts any overheard sentence still
  generating behind it, or cuts it short if it's already being heard. With an overheard
  conversation voiced next to the player, replies reach their first chunk in 0.2 to 0.3 s instead
  of up to 1 s.
- A line that fails to generate before its turn is unvoiced. One that fails during it ends early.

Every constant is in `VoicingConfig`.

## Tests

`server/tests/voicing/` drives `Voicing` with V1's `FakeSynthesiser`, so it runs in CI without MLX.
