# simile.ambient

The ambient director: it makes sure the player overhears the village. If no conversation between
residents has been within earshot for a minute, it nudges two residents near the player who would
happily talk to start one. With the defaults the player overhears about one every 10 minutes in the
play-through below. `director_of(app)` returns the server's `Director`, which the `running` hook
ticks on the sim loop.

## Nudging

- **Earshot.** `Earshot` follows the bus and decides as I1 does, with I1's distances by default: a
  conversation between NPCs comes into earshot once the player is within `earshot` (5 tiles) of
  one of its speakers, and stays in it until they're further than `out_of_earshot` (6.5) from all
  of them. Nothing is in earshot while no client is connected or the player isn't on the map.
- **When.** Every `look_every` (5 s), once nothing has been in earshot for `quiet` (1 minute) and
  at least `retry` (60 s) after its last nudge. The quiet only counts while a client is connected,
  the player is on the map and they aren't in a conversation of their own, so it never nudges
  while the player is talking. It starts again whenever a conversation is in earshot or the
  player's own ends. It waits while `max_conversations` NPC conversations are already going on
  elsewhere, since B2 would decline another.
- **Who.** Two residents who would each accept the other: both score above `accept_bar` (0) on
  B2's `accept_score`, which weighs how they feel about each other, their values, their social need
  and what they're doing. Both are already out in public: each is free to be sought out by the
  other as B1 has it (not asleep, at home or heading there, talking, or cooling off from the
  other), and neither is standing in a house. The target is staying put within `earshot` of the
  player, and the seeker is within `reach` (24 tiles) of them. The pair whose less keen member is
  keenest wins, then the target nearest the player.
- **How.** Through B1's scores, with `Behaviour.nudge`: seeking the target out gets `bonus` (0.6)
  at the seeker's next decision, which they make on the next think. They walk over as for any seek,
  and B2's `request` decides as it always does, so the director never moves anyone or starts a
  conversation itself. Each nudge is published as `Nudged(seeker, target)`.

Every constant is in `AmbientConfig`, `enabled` among them. `director_of(app).config = ...` changes
it while the server runs.

## The scripted play-through

```bash
cd server && uv run simile ambient playthrough --runs 20
```

Plays a scripted player through the village and reports how often they overhear the residents
talking, and what that costs in LLM calls. Each run starts a fresh village in memory at 09:30, runs
it for `--warmup` (60) sim minutes with nobody connected, then connects a player at the square for
`--minutes` (30), at 1x. Nothing calls Claude:

- **The player** walks between the square, the coffee shop, the maker space, the park and the
  noodle bar, lingering 45 to 120 s at each. At half the stops they walk up to the nearest free
  resident within 12 tiles they haven't talked to for 10 minutes and say hello. They answer anyone
  who greets them, say two to four lines, each 4 to 10 s after the resident finishes, then
  goodbye. That's about 9 conversations with the player in 30 minutes.
- **The fake LLM** (`Padded`) writes a B2 scene as a script as long as its plan, in lines of 16
  words, as long as Haiku 4.5's in B2's comparison, the first streamed after 2.3 sim seconds and
  each next 0.4 s later. Replies to the player are 33 words, as in D2's soak, 1.1 s to their first
  sentence and 2 s in all, and a reflection takes 13.9 s, I4's medians. Each line touches two
  values, 60% of the time from the speaker's top five. Reflections store nothing.

The report gives the mean, least and most over the runs of: the share of the time an NPC
conversation was in earshot, overheard conversations (ones the player heard a line of) every 5
minutes, the longest stretch without one, NPC and player conversations, nudges, and LLM calls per
sim hour by purpose. `playthrough(prepare=...)` gets the app between the warm-up and the player
joining, to try other settings.
