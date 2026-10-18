# simile.social

R1's relationship model: how one NPC feels about another, as pure functions over the
`Relationship` in `simile.schema.social`. Nothing here stores anything or calls Claude. R2 keeps
the relationships, B3 applies each conversation's events, B1 and B2 read the scores, and B2's
prompts describe them.

Each direction is its own `Relationship`: `like`, `trust` and `respect` from 0 to 1 with neutral at
0.5, `familiarity` from 0 (strangers) to 1, the `baseline` the scores drift back to, and `flags`.

## Meeting

`meet(owner, about)` starts the scores at the owner's baseline, set by their own core values:
`0.5 + sum(weight * (value - 0.5))`, with the weights in `baseline_weights`. Connection and
compassion make someone like strangers more, security makes them trust strangers less, and
ambition makes them respect strangers less. Familiarity starts at 0.

## Encounters

`apply_events(rel, events, now)` is one encounter, such as a conversation, in which `rel.about` did
`events` to `rel.owner`. `apply_event` is the same with one event.

- **Adding up.** Each event shifts the aspects it names by `valence * magnitude * max_shift` (0.3).
  The shifts add up per aspect and move each score once, so splitting an event in two changes
  nothing, and the good and bad in one conversation net out first.
- **Negativity bias.** A negative event weighs `negativity_bias` (2.5) times as much.
- **The curve.** Each step away from neutral is harder than the last: every `resistance_step`
  (0.15) further from 0.5, a move away is ten times harder. A typical good conversation takes a
  neutral score to 0.65, 10 more take it to 0.8 and 100 more to 0.95, and the same below neutral.
  Moving toward neutral isn't resisted, even past it, so an old friend's betrayal lands in full: a
  bad conversation as strong as a typical good one takes like from 0.95 to 0.575. Neutral is 0.5
  for everyone, so a warm baseline of 0.71 is a head start worth about three good conversations.
- **Familiarity** closes `familiarity_gain` (6%) of its gap to 1 once per encounter, events or not.

## Decay

`decay(rel, elapsed)` moves like, trust and respect back toward the baseline, halving the distance
every 2 days for like, 4 for respect and 8 for trust. Familiarity halves toward 0 every 90 days.
Decay sets how high a pair gets: from a neutral baseline, with a typical good conversation every
hour like peaks at about 0.82, every six hours at 0.73 and every day at 0.68.

A stored relationship is as of its `last_interaction`. Read it through `as_of(rel, now)`, and store
`apply_events(as_of(rel, now), events, now)`, so each stretch of time decays once.

## Traits

Each owner's P1 `Traits` (0-1, 0.5 neutral) bend the numbers above. They come from the world's
cast through P4's `load_cast()`, read once per cast. Anyone outside a cast, including everyone in
today's village, is neutral, and their numbers are exactly as above. Pass `traits=` to
`apply_events`, `decay` or `as_of` to use others. Each trait multiplies something by
`spread ** (2 * trait - 1)` (`trait_factor`), which is 1 at neutral, with each spread in
`RelationshipConfig`:

- **negativity_bias** multiplies `negativity_bias` (`negativity_bias_spread`, 2), but a bad event
  never weighs less than a good one.
- **first_impressions** multiplies the shifts of the owner's first encounter with someone, while
  familiarity is still 0 (`first_impressions_spread`, 2).
- **forgiveness** divides the half-lives of a grudge, a score below its baseline
  (`forgiveness_spread`, 3). Warmer-than-usual feelings fade as before.

## Flags

Facts that outlast the scores (`FlagKind`, from the owner's side): `about` owes the owner, the
owner holds a grudge, `about` made a promise, broke one, saved the owner's life or told them a
secret. `open_flag` adds one and `resolve_flag(rel, id, when)` closes it, e.g. a debt repaid.
Flags never move the scores or decay, and B3 opens and resolves them from what the LLM extracts.

A loan between residents (E6) leaves a `debt` flag the lender holds about the borrower:
`loan(lender, borrower, amount, conversation, when)` makes it, reading "a loan of 100". Its id
ends `/loan/100`, so `lent(flag)` reads the amount back from the flag, and a `debt` flag B3 opens,
whose id is `<conversation>/<n>`, never reads as a loan. `owed(rel)` is the oldest loan
`rel.about` hasn't paid `rel.owner` back.

## describe

`describe(rel, name)` puts the relationship in the second person for a prompt:

> You like Mei a lot but don't trust them. You know them well. Mei still owes you for the bridge
> incident.

A score is mentioned once it's `mild_feeling` (0.1) from neutral and is strong from
`strong_feeling` (0.3). Feelings on the same side as the first are joined with "and", the rest come
after "but". You "barely know" them below `barely_known` (0.2) familiarity, "know them well" from
`well_known` (0.6), and "a little" in between. Each open flag gets a sentence, oldest first.

Every constant is in `RelationshipConfig`, passed as `config=` to the functions that use them.
