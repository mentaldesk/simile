# simile.voicing

Voices the conversations the player can hear, in each NPC's own voice (README: *Only voicing what
the player can hear*). It runs only when V1 does (`SIMILE_VOICE=1` with the voice extra, see
[`voice/README.md`](../voice/README.md)). Otherwise nothing here starts and every `line` goes out
with `voiced: false`.

## Startup

The `running` hook registers every NPC with a `voice.reference_clip` with V1, about 0.15 s each on
an M2 Max, then follows the bus and ticks on the sim loop.

## Earshot

- A conversation is in earshot once the player is within `earshot` (5 tiles) of one of its NPCs,
  and stays in it until they're further than `out_of_earshot` (6.5) from all of them. Nothing is in
  earshot while no client is connected, and nothing on another map, so the player inside a building
  hears nobody outside it.
- Distance is along x, the street, so someone up a ladder is as near as someone on the ground below
  them. Each floor and each street is its own map, so nobody on another floor or street is in
  earshot. `distance.py` measures it for voicing, the ambient director and the player's
  conversations.
- Coming into earshot voices the next line on, including one already written and waiting for its
  turn. Leaving it cuts the line being said and drops the rest.
- The player's own conversation is always in earshot: B5 ends it beyond 6 tiles.
- At most `max_voiced` (2) conversations are voiced at once, the player's included. V1 makes speech
  about 2.6x faster than it plays on an M2 Max: with two conversations it ran up to 2 s behind the
  bubbles, with three up to 13 s, and dropped lines. Another conversation coming into earshot stays
  unvoiced, from its next line on, until one of them ends or leaves earshot. The player starting a
  conversation silences the farthest voiced one instead.
- C2 draws bubbles within the same 5 tiles, so the player hears the conversations whose bubbles they
  see. C3 plays the player's own partner at full volume. It caps an overheard voice at a quarter
  (about −12 dB) within 2 tiles and fades it to silence at 6.5, so it's about −31 dB at 5 tiles.
  `server/tests/voicing/test_client_earshot.py` keeps both sides' distances the same.

## Lines

- A line starts generating on `LineDrafted`: a line ahead for NPC conversations, and as soon as each
  sentence has streamed for the player's. B2 and B5 pace a line by its speaker's measured
  rate, or by its audio once all of it is made. The running hook makes `Voicing` the engine's
  `audio`: `duration(line)` is how long a line's audio plays, jitter buffer included, so the `line`
  message carries it and the bubble lasts as long as the voice. `remaining(line)` is how long until
  it has played on the client, or `None` while it's still being made, and the next line waits for
  it.
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

## Greetings

Each resident has three or four greetings recorded once, which the client plays when they start
talking to the player, whether or not the server is voiced (C3's
[`greetings.ts`](../../../client/src/audio/greetings.ts)). They're in
[`content/voices/greetings/`](../../../content/voices/greetings/): `lines.json` has what each
resident says, written by hand in their way of talking and without anyone's name, and `<id>_<n>.m4a`
is line *n*, AAC at 32 kb/s, about 12 KB each and 600 KB in all.

```bash
cd server && uv run simile greetings [npc ...] [--audition] [--force]
```

- With an ElevenLabs key, `simile greetings` says each line with `eleven_v4` in the resident's voice
  from the ElevenLabs library, chosen in
  [`content/voices/elevenlabs.json`](../../../content/voices/elevenlabs.json) with the audio tags it
  says before each line (`"delivery": "[slowly]"`). That's how residents get their accents, which
  V1's model can't do. The key is `ELEVENLABS_API_KEY`, or the macOS Keychain item
  `elevenlabs-api-key`; `eleven.py` reads it in code and never prints or logs it. Every line spends
  ElevenLabs credits, about 12 for a greeting, and the command says how many it used.
- Without a key, or for a resident with no ElevenLabs voice, it says them with V1's model and seed,
  cloning the resident's clip as V1 does (`uv run --extra voice simile greetings`). Greetings already
  made with ElevenLabs stay as they are until their lines change.
- Both trim the silence around each greeting and encode it with macOS's `afconvert`. ElevenLabs'
  are levelled to the same loudness. A line's `take` picks another seed, for when one comes out
  wrong.
- It says only the lines that are missing or out of date, unless `--force`. `made.json` keeps which
  engine made each resident's and a digest for each line: its words and take, and the ElevenLabs
  voice and delivery or the clip and transcript. Bumping `greetings.SYNTHESIS` makes them all again.
  `make test` fails while any are out of date.
- `--audition` says only each resident's first line, to hear a new voice before paying for the rest.
  The next run says the others.
- For V1's model it waits while mflux, a papercraft or doll build, or an Ollama model is loaded
  (`gpu.py`), so two models never share the GPU's memory.
- `speak.py` imports nothing from simile, so the creator's greetings job can run it in voice-lab's
  MLX virtualenv ([voicelib](../voicelib/README.md#greetings)).

To choose a resident's voice, search the library (`GET /v1/shared-voices`, which costs nothing) for
their accent, gender and age, preferring voices tagged `narrative_story`, then audition it. Their
previews are free to listen to.

`GET /api/greetings/{id}` lists a resident's greetings, `{"greetings": ["/api/greetings/kofi/kofi_1.m4a",
...]}`, and an empty list for anyone without. A player character's come from the library's
`greetings/` folder, and only once they're newer than its clip, so a new voice never greets in the
old one. `GET /api/greetings/{id}/{name}` serves one as `audio/mp4`.

## Tests

`server/tests/voicing/` drives `Voicing` with V1's `FakeSynthesiser`, so it runs in CI without MLX.
The test that says a greeting with the real model is `@pytest.mark.mlx`. Greetings tests use
`eleven.FakeElevenLabs`, and a fixture keeps every test from reading the real key or reaching
ElevenLabs.
