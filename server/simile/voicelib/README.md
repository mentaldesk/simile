# simile.voicelib

The server side of the creator's voice step. A player character gets its voice in one of three
ways, and each ends the same way: a reference clip, set with the library's `save_clip`, and its
transcript as `voice.reference_line`.

| Way | Needs | How |
|---|---|---|
| Design from a description | Apple Silicon, both voice-lab virtualenvs | a `voice_design` job, then pick a candidate |
| Record or upload | Apple Silicon, both voice-lab virtualenvs | upload to `voice/recording` with what it says, which starts a `voice_check` job, then pick it |
| The voice library | nothing | `GET /api/voices`, then pick one |

Once a character has a clip, *Try it* speaks any line in its voice through V1's voice service.

## Routes

| Route | What it does |
|---|---|
| `GET /api/voices` | The voice library (below). |
| `GET /api/voices/{id}/clip` | A library voice's clip, to listen to. |
| `POST /api/characters/{id}/voice/recording?transcript=...` | Checks a recording, and what it says (below). 202 with the job. |
| `POST /api/characters/{id}/voice/pick` | Gives the character the voice picked (below). 200 with the character. |
| `POST /api/characters/{id}/voice/try` | `{"line": "..."}`, at most 300 characters. 200 with the character saying it, as a 24 kHz mono WAV. |

Errors are `{"error": reason}`: 403 for a premade character, 404 for an unknown character, voice or
job, 413 for a body that's too big, 415 for a recording that isn't WAV, MP3 or M4A, and 422 for
anything else that's refused. A recording when this machine can't check one, or *Try it* when the
server runs unvoiced (without `SIMILE_VOICE=1`), gets 503 with the reason. *Try it* for a character
without a clip gets 409.

Jobs are P10's: watch them on `/ws/jobs/{id}`, and fetch the files in their `result` from
`/api/jobs/files/...`. `/api/jobs/capabilities` says whether `voice_design` and `voice_check` can
run here, so the creator can offer the library alone when they can't.

## Designing

`POST /api/jobs` with `{"kind": "voice_design", "params": {"description": "...", "reference_line":
"..."}}`. `count` (1-6, default 4) is how many candidates, and `seed` makes a round repeatable;
without one the server picks it.

`voice-lab/voice_job.py design` has VoiceDesign say the reference line in `count` voices, as
`design_npcs.py` does, then clones each one saying the line again with the game's clone model, so
the player hears what the game will make of it. It checks each candidate the way `design_npcs.py`
does (length, loudness, clipping, Whisper, accent) but doesn't redesign: the player listens and
picks. A round of four takes about a minute on an M2 Max once the models have downloaded.

```json
{
  "description": "A Fife accent. A woman in her fifties, low and even.",
  "reference_line": "Mind the step on your way out, the frost has been at it again.",
  "seed": 1978829904,
  "candidates": [
    {
      "seconds": 6.4,
      "heard": "Mind the step on your way out, the frost has been at it again.",
      "word_error_rate": 0.0,
      "accent": "scotland 81%, england 12%",
      "clone_accent": "scotland 64%, england 30%",
      "problems": [],
      "warnings": [],
      "n": 1,
      "clip": "/api/jobs/files/voice_design/3f9c2a7d1b6e4c08_1.wav",
      "clone": "/api/jobs/files/voice_design/3f9c2a7d1b6e4c08_1_clone.wav"
    }
  ]
}
```

`problems` are `design_npcs.py`'s failed checks, and `warnings` says when the clone loses the
accent. Neither stops the player picking a candidate.

## Recording or uploading

`POST /api/characters/{id}/voice/recording` takes the audio as the body, and exactly what it says
as `?transcript=`. Without one, the clip has to say the character's `reference_line`. The transcript
becomes the character's line when the recording is picked, so it's refused before the upload is
read unless it's 12-25 words, without a `!`, as `import_voices.py` requires. The audio is refused,
with the reason, when it's empty or over 10 MB, or isn't a WAV, MP3 or M4A file by its first bytes.
A WAV has to decode in full with Python's `wave`, at most 60 s, so a browser recording should be
sent as 16-bit PCM WAV. WebM, which is what most browsers record, isn't taken. MP3 and M4A are
decoded by the job, which reports a file that won't, and refuses one over 60 s before any of the
slow checks.

The job runs `voice-lab/voice_job.py check`, which runs `import_voices.py`'s checks on the
transcript: it converts the clip to 24 kHz mono, Whisper must hear the transcript, the clip must be
5-25 s, and the transcript must be 12-25 words without a `!`. The accent classifier listens to the
clip and to `SAMPLE_LINES` cloned from it, the `samples`, and warns about a North American accent.
The result says whether the recording is `usable`. One with `errors` isn't kept, so it has no
`clip`:

```json
{
  "seconds": 8.1,
  "heard": "...",
  "word_error_rate": 0.58,
  "accent": "scotland 72%, ireland 15%",
  "sample_accents": ["...", "...", "..."],
  "errors": [],
  "problems": ["word error rate 58%", "ending missing"],
  "warnings": [],
  "reference_line": "...",
  "clip": "/api/jobs/files/voice_check/3f9c2a7d1b6e4c08.wav",
  "samples": ["/api/jobs/files/voice_check/3f9c2a7d1b6e4c08_1.wav", "..."],
  "usable": false
}
```

## Picking

`POST /api/characters/{id}/voice/pick` takes one of:

- `{"design": "<job id>", "candidate": 2}`: a designed candidate, with the line it says.
- `{"recording": "<job id>"}`: a checked recording, with its transcript. Refused with the problems
  unless it's `usable`, which leaves the voice as it was.
- `{"library": "henrietta"}`: a copy of a library clip, with its transcript.

It saves the clip with `save_clip`, then sets `reference_line` to what the clip says if that's
different, since the clone model needs the right transcript. The description is left alone.

## The voice library

`content/voices/library.json` tags the residents' clips in `content/voices/` by `accent`, `age`
(`young`, `middle-aged` or `older`) and `gender` (as `Character`'s). It only tags them: their clips,
transcripts and `imported.json` stay as they are, and picking one copies the clip.

```json
{"id": "henrietta", "accent": "Scottish", "age": "older", "gender": "woman",
 "reference_line": "...", "clip": "/api/voices/henrietta/clip"}
```

## Greetings

Once a character's voice is set, `pick` drops its old greetings and starts a `voice_greetings` job
(`{"character": "<id>", "library": "<resident>"}`, the second only for a library voice), which
moves four greetings into the library's `greetings/` folder as `<id>_<n>.m4a`, where
`GET /api/greetings/{id}` finds them. The result lists them with their `lines`, `seconds` and the
ElevenLabs `voice` that said them, if any. A job for a clip that changed while it ran keeps nothing
(`"stale": true`).

- **With an ElevenLabs key** (`ELEVENLABS_API_KEY` or the Keychain item `elevenlabs-api-key`, looked
  for when the server starts), the job needs only a Mac. It runs
  [`voicing/eleven.py`](../voicing/eleven.py), which says them with `eleven_v4` in a voice from the
  ElevenLabs library, with the audio tag for the character's leading tone (`[warmly]`). A voice
  picked from the library brings its resident's ElevenLabs voice. Otherwise it searches the library
  for the accent the voice description names ("A Fife accent"), then the character's origin, by
  gender and age band, and takes one of the three most used, narration first. It costs about 50
  credits a character.
- **Without one**, it needs Apple Silicon and voice-lab's MLX virtualenv, and runs
  [`voicing/speak.py`](../voicing/speak.py) there, which says them in the character's own voice with
  V1's model, a second or so each once the model has loaded.

The greetings come from `lines_for` in [`voicing/greetings.py`](../voicing/greetings.py), with no LLM
call: three in the tone the character's values lean to most (formal, warm, brisk or playful), and a
fourth in their next tone, or a hello their speaking style quotes ("Kia ora!"). Where the job can't
run, a voice picked from the library brings that resident's own greetings, and any other voice has
none until it can.

## Where it writes

Nothing here writes to `content/`. Greetings go in the library's `greetings/` folder. Uploads wait in `<jobs>/voice_check/uploads/` until their job
moves them into its work directory. One whose job is cancelled or fails first is deleted when the
job ends, and the server cancels its waiting check jobs when it stops. It also deletes any upload a
day old when it starts, which only a killed server leaves. Each kind keeps the files of its latest
20 jobs in `<jobs>/<kind>/`, so picking from an older round says it's gone. `<jobs>` is
`$SIMILE_JOBS`, or `server/data/jobs/`.
