# simile.voice

Text to speech in each NPC's own voice: Qwen3-TTS (`mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit`)
cloning their reference clip on MLX, so it needs Apple Silicon.

## Running voiced

The server runs unvoiced unless you install the `voice` extra and set `SIMILE_VOICE=1`:

```bash
cd server && uv sync --extra voice
SIMILE_VOICE=1 make dev
```

The first start downloads the model from Hugging Face (about 3 GB). After that, loading it adds
about 3 seconds to startup (nearer 20 when the weights aren't in the OS file cache) and uses about
3 GB of memory. `simile headless` never loads it. The `@pytest.mark.mlx` tests in
`server/tests/voice/` need the extra too.

## Speaking

`voice_of(app)` returns the `VoiceService`, or `None` when the server runs unvoiced.

```python
from contextlib import aclosing

from simile.voice import Priority, voice_of

voice = voice_of(app)
await voice.add_voice(npc.id, npc.voice)
async with aclosing(
    voice.speak(npc.id, "Leave it with me till morning.", Priority.PLAYER)
) as speech:
    async for pcm in speech:
        ...
```

- `add_voice(npc_id, voice)` loads and encodes the F2 `Voice`'s `reference_clip` (relative to the
  repository root) once, so later lines skip that work. It raises `ValueError` if the voice has no
  clip yet. `has_voice(npc_id)` says whether an NPC can be voiced.
- `speak(npc_id, sentence, priority)` yields the sentence's audio: 24 kHz mono 16-bit little-endian
  PCM, as the F3 `audio_chunk` frame carries it, in chunks of about a quarter of a second. Chunks are
  always whole samples. It raises `KeyError` for an NPC without a voice.
- The iterator ending is the only end-of-sentence signal, so a line's last `audio_chunk` is the
  header-only one F3 allows, with the last flag set.
- The sentence joins the queue when you start iterating. One sentence is spoken at a time, since
  mlx-audio keeps a stream's decoder state on the model and one stream already keeps the GPU busy.
  `PLAYER` goes before `OVERHEARD` (the default), and sentences of equal priority go in the order
  they were asked for. A sentence already being spoken isn't interrupted.
- To cancel, stop iterating: close the iterator (`aclose()`, or `aclosing` as above) or cancel the
  task that iterates it. A queued sentence is dropped; one being spoken stops within one chunk.
- An error while speaking is raised from the iterator. The next sentence still plays. Iterating
  after the service has stopped raises `RuntimeError`.
- A sentence that runs past 3 s plus 1 s per 5 characters is cut off with a warning, so a
  generation that never ends can't hold the queue.

## Tests

`FakeSynthesiser` speaks instantly without MLX, so code that uses the service can run in CI:
`VoiceService(FakeSynthesiser())` is a working service. `gate(sentence)` holds a sentence before
each chunk until the test releases it, and sentences in `failing` raise.
