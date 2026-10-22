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

A save from before the incident gets one rather than none, since without it an old village has no
story short of `simile reset`. It's dated a week before the save's own time, which can fall within
what the village has already lived through, but its memories stay out of `recall`, so nobody brings
it up until the player asks.

```bash
cd server
uv run simile story incident --seed 3 --facts   # one Sonnet call, saves nothing
```

Every constant is in `StoryConfig`.
