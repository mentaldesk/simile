# simile.behaviour

What each NPC does next. Every NPC has needs that rise over time, and when they've been somewhere
long enough they score every option and pick one, walking there with W2's `walk_to`.

`behaviour_of(app)` returns the server's `Behaviour`, created on first use with N1's NPCs from
`content/npcs/`. Its lifespan puts every NPC at home, ticks the decision loop on the sim loop, and
sets F3's snapshot to the NPCs' real positions.

## Deciding

- **Activities.** Go home, the coffee shop, the square, a news terminal, the park, the noodle bar,
  the maker space, wander, seek someone out (an NPC or the player), or idle. `sleep` and `talk` are
  set by the loop rather than chosen.
- **Score** = base + values + needs + time of day + people − walking time. Values enter as
  `weight * (value - 0.5)`: Connection pulls towards people, PeaceOfMind home and to the park (and
  away from seeking company), Adventure to wander, Creativity to the maker space. Needs (`social`,
  `curiosity`, `rest`, `news`, 0 to 1) pull towards whatever meets them. The coffee shop
  peaks in the morning, the noodle bar at lunch and dinner, and home in the two hours before bed.
  The activity just finished scores less.
- **Loneliness.** `social` feels urgent on a convex curve, `need ** 3` (`urgency`), so a little
  barely registers and a lot crowds out everything else. An option scores the relief it brings:
  the area under that curve between the need now and after a typical stay (`effects` over the
  middle of its `dwell`; seeking someone out promises `talk_minutes` of talking). The same chat is
  worth far more to someone desperate than to someone who's just had one. Connection sets how fast
  `social` rises (Peace of Mind slows it), so high-Connection NPCs get lonely and go looking for
  company, and low-Connection ones mostly keep to themselves. Talking meets it fast. `curiosity`
  and `rest` still enter linearly through `need_weights`; the needs in #74 can move to the same
  curve.
- **The news.** `news`, wanting to catch up, is on the same kind of curve (`need ** 2`), and only a
  terminal meets it. It rises with Knowledge and Open Mindedness and falls for NPCs low in both,
  so some read every couple of hours and some never do. The `news_interest` hook says how
  interesting the best article they haven't read is (0 to 1), and a terminal's relief is scaled by
  it, so a gripping article pulls harder than a so-so one. With nothing worth reading, the
  terminals aren't an option.
- **People.** Affinity is a weighted sum of R1's like, trust, respect and familiarity, read from R2
  with `as_of`, or `meet` for strangers. Seeking someone scores their affinity, scaled up by
  Connection. A place scores the affinity of everyone at or heading to it: friends attract,
  people they dislike repel, and a crowd draws high-Connection NPCs and puts off low ones. Nobody
  seeks someone asleep, at home, talking or who refused them in the last 45 minutes.
- **Choice.** The best place for each activity goes into a softmax over activities, so three
  terminals don't make the news three times as likely. `Behaviour(seed=...)` makes it repeatable.
- **Night.** Each NPC has a bedtime (21:00 to 23:45) and a wake time (05:30 to 09:00) from their
  values. Outside them they go home and sleep, whatever the scores say.
- **When.** An NPC decides when their stay somewhere runs out (a few minutes for a wander, up to an
  hour at home or the maker space), not every tick. Needs update every 5 sim seconds.

Every weight and constant is in `BehaviourConfig`.

## Hooks for other modules

`behaviour_of(app).hooks` holds the interfaces other tasks implement. Each starts as a stub. Plug
in from your own lifespan; `set` returns a function that puts back what it replaced:

```python
restore = behaviour_of(app).hooks.set(
    request_conversation=engine.request,  # (a, b) -> bool
    conversations=engine.live,  # () -> list[Conversation], for the snapshot
)
yield
restore()
```

| Hook | Called | Stub |
|---|---|---|
| `request_conversation(a, b)` | When `a` walks up to `b` (an NPC id or `"player"`) | Declines |
| `read_news(npc)` | With the `Npc` when they reach a terminal | Does nothing |
| `news_interest(npc)` | With the `Npc` at each decision: how interesting the best unread article is, 0 to 1 | 0, so nobody goes to the terminals |
| `conversations()` | For each snapshot | `[]` |

Hooks run inside a tick, so they mustn't block. One that raises is logged and counts as a decline.

If `request_conversation` returns True, both NPCs are paused with the goal `talk <other>` until the
conversation engine calls `resume` on each. Otherwise the seeker hangs around for a few minutes.

## Reading and steering NPCs

| | |
|---|---|
| `pause(npc, talking_to=None)` | Stops their walk and their decisions. Does nothing for the player. |
| `resume(npc)` | They decide again on the next think. |
| `restore(npc, goal, needs, since, until, cooldowns)` | Puts back a saved NPC (I3) after the clock is set: stops their walk and publishes one `GoalChosen`. With no `until` they decide on the next think. Everyone's needs rise from now. |
| `goal(npc)` | Their `Goal`: `activity` and `target`, a location or entity id. |
| `needs(npc)` | `{Need: 0-1}`. |
| `state(npc)` | JSON for F3's `npc_state`: goal, needs, last decision's scores, bedtime. |
| `minds` | Each NPC's `Mind`, with mutable `needs`. |

Every new goal is published on the bus as `GoalChosen(npc, activity, target)`.

## Fast-forward

```bash
cd server && uv run simile behaviour simulate --hours 24 --seed 0
```

Runs memory, world and behaviour on a `FakeWallClock` as fast as the CPU allows (a sim-day in
about 15 s) and prints where everyone spent their time: minutes near others by Connection, places
by hour and who was out at night. Conversations and news stay stubbed, so nothing calls Claude:
there's always an article of middling interest unread, and reading it does nothing.
