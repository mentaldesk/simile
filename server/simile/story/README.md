# simile.story

P48: Aris, who one morning is gone. Each world makes its disappearance once, when it's created, with
no LLM call: who distrusted her bionics, who saw her last, and who knows what. The facts live in the
sim, in S2's `Disappearance` (`investigation_of(app).disappearance`), and residents only voice
them. Nobody in the village made her vanish: what they saw only points the way underground. B5's
conversations with the player tell, lie about or keep back what each resident knows (see
[*Telling*](../conversation/README.md#telling) in the conversation README).

## Aris and her workshop

[`content/story/story.toml`](../../../content/story/story.toml) has Aris, her workshop, the maker
space, and the street she was last seen on (`last_seen`, Banyan Row). Her one clue is a cell on
the workshop's ground floor, so the map stays as it is: `aris_notes`, her notebook on the
workbench, with a few pages of her own besides the one that matters. A fact's `found_in` is a clue,
and `load_story().clue(id)` says where it is and what the journal calls it. The content also has
the lines Aris wrote about those who distrusted her, the residents' memories, and the cover
stories.

## Who distrusted her

The residents at or below `distrusts_from` (-1) on S11's bionics `level` of their tolerance
([`simile.social`](../social/README.md#bionics)) distrusted her, least tolerant first. If nobody is
that far, the least tolerant resident distrusts her alone. In the default village that's Tobias
(-2), Henrietta (-2), Mirela (-1) and Raymond (-1).

## The facts

Her workshop was found open the day before the world starts (`gone_before`, 26 hours), and she was
last seen the evening before that, on the five minutes between 21:20 and 22:00 (`seen_between`):

| Fact | Who knows it | Leads to |
|---|---|---|
| `gone`: one morning her workshop was found open, her tea cold and her tools on the bench, and nobody saw her leave | everyone, told to anyone | `notes`, `last_seen` naming its witness |
| `notes`: her lines about one or two distrusters, by initial | found in `aris_notes` | each noted distruster's `distrust_<id>` |
| `distrust_<id>`: they distrusted her bionics and said she wasn't one of them any more | the distruster (`did`), and a bystander who heard it (`witnessed`) | `passed`, for the passer |
| `last_seen`: the witness saw her heading down Banyan Row's steps towards the old metro, with the passer going the other way | a witness | `lift_log`, `passed` |
| `passed`: one distruster passed her that evening and said nothing | the passer (`witnessed`) | `lift_log` |
| `lift_log`: Aris rewired the metro's dead terminal, which logged the lift going down to the sewers the night before her workshop was found open | found in `metro_terminal`, with the datajack (S8) | `hatch_log` |
| `hatch_log`: a maintenance hatch deep in the sewers, stamped with Apex's mark, took a key with Aris's mark that night, onto a shaft towards the Apex towers | found in `sewers_hatch`, with the datajack (S9) | |

The passer is one of the noted distrusters, so the notes lead to `passed` even with nobody else to
see her. Witnesses and bystanders are residents who didn't distrust her, each once before anyone
twice. The logs are dated 15 and 75 minutes after she was last seen.

How willing each knower is:

- **A witness** tells anyone they trust at least 0.5 plus 0.3 × Security, 0.2 × Peace of Mind,
  -0.3 × Justice and -0.2 × Honesty, each from 0.5 (`tells_from`), up to `most_wary` (0.9). Below
  that they keep quiet, or, below `witness_lies_below` (0.4) Honesty, lie with a cover story like
  "I was home all evening."
- **A distruster** tells from `admits_from` (0.75) trust, or tells anyone if they're strongly
  against bionics and their Honesty is at least `distruster_lies_below` (0.6). Below that they keep
  quiet, or, if they're less honest than that, deny it: "Aris and I always got on fine." and, as the
  passer, "I didn't see her that evening." In the default village Henrietta and Raymond lie, and
  Tobias says it out loud.
- **Everyone** tells `gone` to anyone.

Each knower gets one `observation` memory of each fact they know, in their own words, with its
`fact_id`, dated when it happened, with `salience` and `valence` by how they know it. A distruster's
memory of her going ends "Good riddance, if you ask me." R2's `recall` leaves these out, so nobody
brings her up in a scene or makes a work about it until the player asks: only `MemoryStore.facts`
returns them, for telling the player. Once a resident has told the player something, B3's memory of
that conversation holds it (see [*Telling*](../conversation/README.md#telling)).

## When it's made

The lifespan makes it on startup when the world has no disappearance: a new world, a fresh start,
every `SIMILE_DB=:memory:` run, and once for a save from before it. A world with no residents gets
none. A cast world (P9) draws it from the cast's seed, and any other world at random. It runs after
persistence has restored the save, in a crash-safe order:

1. It forgets any memories with a `fact_id`: those of an old incident, or of a start that stored
   them and then died before saving.
2. It makes the disappearance.
3. It keeps only the journal entries that are still true word for word (the lift and hatch logs)
   and the town's (`town_*`), and drops their leads to facts that no longer exist.
4. It stores the new memories, then sets the disappearance, drops any old incident and saves the
   world, so it's made at most once and its memories are never lost.

A save from an incident keeps the residents' conversation memories, which have no `fact_id` and can
still mention the attack; a new game has the clean story. A world whose logs don't match when she
was last seen gets them again (`logged`) on its next start, and is saved. The hatch is a jack in
every level of the sewers (`simile.street.sewers.HATCH`), so its cell is each level's own and isn't
in `story.toml`.

```bash
cd server
uv run simile story disappearance --seed 3 --facts   # saves nothing
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
  or nearer is picked up instead, as the client shows. The reach is the client's, so they agree.
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
  mind bionics, or like them), or else is whoever takes to bionics best. Never a distruster while
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
to it, and the clinic and scrap trader below. Their ids start `town_`, so none is ever the
disappearance's.

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

