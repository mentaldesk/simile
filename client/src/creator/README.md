# Character creator

Browse the character library and make your own characters. Open <http://localhost:5173/?creator>,
or *Characters* on the title menu. It's a DOM overlay over the game, built on the server's library
(`server/simile/library/`), jobs (`server/simile/jobs/`) and voice routes (`server/simile/voicelib/`).

- **Library** (`library.ts`): premade characters, read-only, and your own. Open one, import an
  exported `.zip`, start a new one, or change your own look.
- **A character** (`editor.ts`): five sections, each with a lock and a reroll. A new character is
  written by *Write character*: whatever you set first goes into P3's brief, and anything you edit
  locks its section. *Reroll unlocked*, or a section's *Reroll*, writes those sections again and keeps
  the rest. Save, export and delete live in the bar.
  - **Look**: the appearance controls. Saving draws the sprite as a P10 job and shows it, where the
    server can draw sprites.
  - **Values**: the four latent traits and the presets move all 24 values at once, through the same
    model P3 samples from (`values.ts`). A value set by hand in the advanced view keeps its place
    relative to the traits. The sample line is a `voice` reroll of the character with these values,
    so one Claude call each: it waits for the sliders to settle, never asks twice at once, and asks by
    itself only a few times before it waits for *New line* (`sample-line.ts`).
  - **Background**: P3's skeleton fields. A reroll draws the facts and tension behind the biography
    again, so rerolling the background rerolls the biography too, unless that's locked.
  - **Biography**: life events, the prose, the verbal habits (mannerisms, drawn from P3's table)
    and the ties, rerolled together for the same reason. Generation streams the reply as it's
    written, and the critic's suggestions can be accepted or ignored one by one.
  - **Voice** (`voice.ts`): design from the description, record or upload the line, or pick a
    resident's voice from the library, then *Try it*. The microphone is recorded as raw samples and
    sent as 16-bit PCM WAV (`wav.ts`), since the server refuses the WebM that browsers record.
    Picking a designed voice saves the description that made it.
- **Your look** (`player-look.ts`): the same appearance controls, saved through `/api/player` and
  drawn as the `player` sprite job.

`draft.ts` holds a character's state: what's on screen, what's saved, the locks, the brief and the
reroll sections, and the checks before saving. `character.ts` is generated from the server's JSON
Schema by `character.test.ts`.
