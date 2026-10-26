# simile.story

S12: Aris, who is missing, and the night she was attacked. Each world makes its own incident once,
when it's created: who attacked her and why, who saw what, and who knows it. The facts live in the
sim, in S2's `Incident` (`investigation_of(app).incident`), and residents only voice them. B5's
conversations with the player tell, lie about or keep back what each resident knows (see
[*Telling*](../conversation/README.md#telling) in the conversation README).

## Aris and her workshop

[`content/story/story.toml`](../../../content/story/story.toml) has Aris, for the motive's writer,
and her workshop, the maker space. Its two clues are cells on the workshop's ground floor, so the
map stays as it is: `aris_notes`, her notebook on the workbench, with a few pages of her own besides
the one that matters, and `door_frame`, where the attackers left a scrap of cloth. A fact's
`found_in` is one of them, and `load_story().clue(id)` says where it is and what the journal calls
it.

## The attackers

Each grievance in the content is something Aris did that someone can't forgive (a repair that
failed them, what she does to her own body, the rules she breaks, a deal she cost them, a public
humiliation), with the core values that make it rankle. A resident's fit to one is the sum of each
weight times how far that value is from 0.5, over the sum of the weights, from -0.5 to 0.5. Their
hostility is their best fit plus `harm` times how far their Compassion is below 0.5.

- Everyone at `hostile_from` (0.2) or more is a suspect. With today's residents that's Henrietta,
  Raymond, Marguerite and Priya.
- One, two or three of them attack her (`attackers`: 40%, 35%, 25%, while there are enough), drawn
  by how far each is past the bar. If nobody reaches it, the most hostile attacks alone.
- Each attacker's grievance is drawn from those within `grievance_spread` (0.15) of their best.

## The motive

One `structured` call with Sonnet (`purpose="story-motive"`) writes the backstory from the
attackers' names, jobs, personas, values and grievances, and where several of them met the evening
before (one of the content's `meeting_places`): the motive, and for each attacker what Aris
did to them in the third person and in their own words, their memory of the night, the alibi,
deflection and denial they give instead of the truth, and the line Aris wrote about them, naming
them by their initial. Every alibi, deflection and denial stays vague and points at nobody, neither
a resident nor a stranger, since #283's bounds rule out making up facts about people. A reply that
doesn't validate gets one retry, as L1 does. A call that fails,
times out after `write_for` (180 s) or runs on the fake LLM leaves it to the content's templates, so
a world always has an incident.

## The facts

Placed a week before the world starts (`night_before`, 23:00 to 23:20), with Aris's workshop found
open the day before it starts (`gone_before`):

| Fact | Who knows it | Leads to |
|---|---|---|
| `gone`: she was attacked, wouldn't say who, and a week later vanished | everyone, told to anyone | `notes`, `shouting` |
| `notes`: what she wrote about one attacker (each, if nobody else lives there), by their initial | found in `aris_notes` | that attacker's `grudge_`, `shouting` |
| `cloth`: a scrap of one attacker's top colour on the door frame | found in `door_frame` | `seen`, or with nobody to see, their `there_` |
| `shouting`: heard from the workshop that night | a witness | `seen` |
| `seen`: someone who looked like that attacker, and any others, leaving the lane | a witness | that attacker's `there_`, `meeting` |
| `meeting`: the attackers together the evening before, with two or more | a witness | each `there_` |
| `grudge_<id>`: the attacker rowed with Aris, and why | the attacker, and a witness | their `there_` |
| `there_<id>`: the attacker was in the lane, not where they say | the attacker | |
| `attack`: who did it | the attackers | |
| `lift_log`: Aris rewired the metro's dead terminal, which logged the lift going down to the sewers the night before her workshop was found open | found in `metro_terminal`, with the datajack (S8) | `hatch_log` |
| `hatch_log`: a maintenance hatch deep in the sewers, stamped with Apex's mark, took a key with Aris's mark that night, onto a shaft towards the Apex towers | found in `sewers_hatch`, with the datajack (S9) | |

Every lead goes from what the player can find or ask about towards an attacker, so each attacker's
`there_` can be reached from the notes, the cloth or `gone`. Witnesses are residents other than the
attackers, each once before anyone twice.

How willing each knower is:

- **A witness** tells anyone they trust at least 0.5 plus 0.3 × Security, 0.2 × Peace of Mind,
  -0.3 × Justice and -0.2 × Honesty, each from 0.5 (`tells_from`), up to `most_wary` (0.9). Below
  that they keep quiet, or, below `witness_lies_below` (0.4) Honesty, lie with a cover story like
  "I didn't see anything that night".
- **An attacker** lies about `attack` and their `there_` with their deflection and alibi, and owns
  up only to someone they trust `owns_up_to` (0.95), and only if their Honesty is at least
  `owns_up_from` (0.6). They own up to their grudge from `admits_grudge_from` (0.75) trust, and
  deny it below.
- **Everyone** tells `gone` to anyone.

Each knower gets one `observation` memory of each fact they know, in their own words, with its
`fact_id`, dated when it happened, with `salience` and `valence` by how they know it. A resident
hostile enough to be a suspect remembers her going as good riddance. R2's `recall` leaves these
out, so nobody brings the incident up in a scene or makes a work about it until the player asks:
only `MemoryStore.facts` returns them, for telling the player. Once a resident has told the player
something, B3's memory of that conversation holds it (see
[*Telling*](../conversation/README.md#telling)).

## When it's made

The lifespan makes it on startup when the world has no incident: a new world, a fresh start, every
`SIMILE_DB=:memory:` run, and once for a save from before it. A world with no residents gets none.
A cast world (P9) draws it from the cast's seed, and any other world at random. It runs after
persistence has restored the save. First it forgets any memories with a `fact_id`, which can only
be left from a start that stored them and then died before saving the incident. Then it stores
the new memories, and only then sets the incident and saves the world, so the incident is made at
most once and its memories are never lost. The log says only that it was made, not who did it.

A world whose incident predates S8 or S9 gains the fixed `lift_log` and `hatch_log` (`logged`) on
its next start, dated 20 and 19 hours before its `gone`, and is saved. The hatch is a jack in every
level of the sewers (`simile.street.sewers.HATCH`), so its cell is each level's own and isn't in
`story.toml`. A save from before the incident gets one rather than none, since without it an old village has no
story short of `simile reset`. It's dated a week before the save's own time, which can fall within
what the village has already lived through, but its memories stay out of `recall`, so nobody brings
it up until the player asks.

```bash
cd server
uv run simile story incident --seed 3 --facts   # one Sonnet call, saves nothing
```

## The journal

S13: what reaches the player goes into S2's journal (`investigation_of(app).journal`), saved with
the world. `Journal` (`journal.py`) writes it, and `Recorder` (`recording.py`), which the module's
`running` hook starts, says when:

- **Told.** Once a resident is set up for what they know (`PlayerTalk.tellings`, see
  [*Telling*](../conversation/README.md#telling)), their next line to the player writes each fact
  they tell, as it really happened (`what`), with its leads. A truth goes by the stance alone,
  whatever the model makes of it: a check on its words would miss a paraphrase, and never pass
  on the fake LLM.
- **Lied to.** A fact they lie about is written as their cover, in quotes, with no leads, once
  their lines in the conversation, joined, hold it word for word (`says`, in `saying.py`, which
  ignores case, quotes, apostrophes, punctuation and spacing). Joined, because a cover of two
  sentences comes as two lines. A cover they're set up with but never asked for, and so never
  give, isn't written, and neither is anything they keep back. Nothing in the conversation calls
  the recorder: it hears `LineSpoken` and reads the player's talk.
- **Found.** A `pick_up` (E) within `clue_reach` (half a tile) of a clue's cell, from
  `load_story().clues`, writes each fact found in it (`found_in`), with its leads. The clue is a
  claim on `pick_up` (`claimers_of` in [`simile.player`](../player/README.md)), so a pile as near
  or nearer is picked up instead, as the client shows. The reach is the client's, so they agree,
  and it keeps the workshop's door, beside the door frame, on E.
- **The flush.** With the infrared eye fitted, a lie is `flushed: true` and the truth `false`
  (`flushed`). Without the eye, and for a clue, it's `null`. S8's flush on a line uses `says` and
  `flushed` the same way (`simile.conversation.flush`), so the face and the journal agree.
- **Leads.** An entry opens its fact's leads, less those to facts the journal already has, and
  closes every lead to its own fact, a lie included.
- **Once.** A truth already in the journal isn't written again, whoever tells it, nor a lie the same
  resident already told, unless the eye now catches the flush it couldn't see before: then the lie
  moves to the end, flushed.

The `journal` message goes to each client on connect and to all of them whenever it changes.

- **Places.** What a resident tells the player of the old metro, the way down, the clinic or the
  scrap trader, as they know it or as a rumour, is written as told, by the same rule as a truth
  (see [*The town*](#the-town)). The metro's entry opens a lead to the way down.

Every constant is in `StoryConfig`.

## The lens

P17: the clinic's infrared eye needs an `infrared_lens` (P4), a part of 0.2 kg. One resident has
it, out of an old thermal camera, and gives it to the player once they trust them enough
(`lens.py`, which the `running` hook starts).

- **Who.** P20: someone who wouldn't turn against a player turning cyborg. The keeper is drawn at
  random from the residents whose S11 bionics `level` is at least `tolerates_from` (0: they barely
  mind bionics, or like them), or else is whoever takes to bionics best. Never an attacker while
  anyone else would do. The draw is from the world's seed (the cast's, or 0 for the village in
  `content/`), so it's the same on every start and nothing is saved. In the default village that's
  Desmond.
- **Saying so.** Once they trust the player `mentions_from` (0.58), checked every `lens_every` (60
  sim seconds), they gain a memory about the player of still having it and that they'd give it to
  them once they trust them a little more. R2's `recall` brings it to mind in conversations with
  the player, so they can bring it up.
- **The hand-over.** In a conversation with the player, once the keeper has spoken and it's the
  player's turn, the sim checks R1's trust in them, once per conversation. From `gives_from` (0.62)
  the lens goes into the player's items, and the keeper says a stock line through B5's
  `interject` handing it over, which later replies see in the transcript. They remember giving it,
  about the player, which marks it given across restarts: they never give it twice. If the player
  can't carry it, the keeper says so instead and offers it again in a later conversation. The
  model never decides any of this.
- **Only once they've talked.** Both need the keeper to remember a conversation with the player
  (B3's `conversation` memory about them), so a keeper who trusts newcomers that much from the
  start, or warms to them on seeing their bionics, doesn't give it away before they've spoken.
  With good conversations (trust events of 0.5 valence and magnitude) every 6 sim hours, any
  tolerant resident of the default village trusts the player `mentions_from` after at most two
  and `gives_from` after at most four. Once a sim day, it can take Marguerite five.

The player's items are saved with the world at the next autosave, so a crash within those 10
seconds loses a lens the keeper remembers giving.

## The town

#384: what residents know of the village, in `town.py`. Each `TownFact` is something about a place
and what it's for: the café, the noodle bar, the maker space, the gallery, the news terminals, the
park, the square and the river promenade, then the old metro under the promenade, the stairway down
to it, and the clinic and scrap trader below. Their ids start `town_`, so none is ever an
incident's.

Who knows what is drawn from the world's seed (the cast's, or 0 for the village in `content/`) and
each resident, so it's the same on every start and nothing is saved. Each resident gets a time in
the village, from none up to their adult years, and for each fact a roll against its chance of
knowing it (`knows`) or only having heard it (`heard`), moved by:

- **Time here** (`tenure`): an old hand is likelier to know it than a newcomer.
- **Values**: Adventure, Open-mindedness and Connection make the metro's details likelier, Security
  less likely. Connection helps with everything.
- **Job, interests and street** (`words`, `near`): salvage, repair or the river, or living or
  working on Banyan Row, make the metro likelier; whoever lives or works at a place knows it.

Anyone who knows what's down there knows of the metro. Over many seeds most residents know every
amenity, nearly all at least have heard of the metro, and a quarter or fewer know the way down, the
clinic or the scrap trader, mostly as rumour.

