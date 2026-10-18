# simile.behaviour

What each NPC does next. Every NPC has needs that rise over time, and when they've been somewhere
long enough they score every option and pick one, walking there with W2's `walk_to`.

`behaviour_of(app)` returns the server's `Behaviour`, created on first use with N1's NPCs from
`content/npcs/`. Its lifespan puts every NPC at home, ticks the decision loop on the sim loop, and
sets F3's snapshot to the NPCs' real positions.

## Deciding

- **Activities.** Go home, the coffee shop, the square, a news terminal, the park, the noodle bar,
  the maker space, the gallery, wander, seek someone out (an NPC or the player), idle, or make
  something (`create`). `sleep` and `talk` are set by the loop rather than chosen.
- **Score** = base + values + needs + time of day + people − walking time. Values enter as
  `weight * (value - 0.5)`: Connection pulls towards people, PeaceOfMind home and to the park (and
  away from seeking company), Adventure to wander, Creativity to the maker space, and
  Open-mindedness, Knowledge, Creativity and Peace of Mind to the gallery. Needs (`social`,
  `curiosity`, `rest`, `news`, `inspiration`, 0 to 1) pull towards whatever meets them. The coffee
  shop peaks in the morning, the noodle bar at lunch and dinner, and home in the two hours before
  bed. The activity just finished scores less. Curiosity is met fastest at the maker space, but
  also at the square, the coffee shop and the park, by wandering and by reading, so it sends people
  all over town rather than into one room.
- **Loneliness.** `social` feels urgent on a convex curve, `need ** 3` (`urgency`), so a little
  barely registers and a lot crowds out everything else. An option scores the relief it brings:
  the area under that curve between the need now and after a typical stay (`effects` over the
  middle of its `dwell`; seeking someone out promises `talk_minutes` of talking). The same chat is
  worth far more to someone desperate than to someone who's just had one. Connection sets how fast
  `social` rises (Peace of Mind slows it), so high-Connection NPCs get lonely and go looking for
  company, and low-Connection ones mostly keep to themselves. Talking meets it fast. Talking with
  the player meets `player_relief` (0.5) of that, and seeking them out promises only as much, so a
  chatty player doesn't become the village's social life. `curiosity` and `rest` still enter
  linearly through `need_weights`; the needs in #74 can move to the same curve.
- **The news.** `news`, wanting to catch up, is on the same kind of curve (`need ** 2`), and only a
  terminal meets it. It rises with Knowledge and Open Mindedness and falls for NPCs low in both,
  so some read every couple of hours and some never do. The `news_interest` hook says how
  interesting the best article they haven't read is (0 to 1), and a terminal's relief is scaled by
  it, so a gripping article pulls harder than a so-so one. With nothing worth reading, the
  terminals aren't an option.
- **Making things.** Residents with a craft (`Npc.craft`) have an `inspiration` need, on the same
  kind of curve as the news (`need ** 2`, from a lower base), so it builds slowly and then wins. It
  rises with Creativity and Self-actualization, from about one work every two sim-days for the
  least creative crafter to one a day for the most, and never without a craft. `create` meets it: a
  stay of about an hour, and the need is met all at once as they leave (`finishing`), when B1 calls
  the `create` hook. A stay cut short by a nudge or bedtime makes nothing, but a talk only pauses
  it, and afterwards they go back for the rest of the stay. Nobody starts one with less than a
  typical stay left before bed.
- **Where they make things.** Writers write at home, the coffee shop or the maker space, wherever
  their values fit best (`writing_places`): Peace of Mind, Independence, Security and Tradition at
  home, Connection, Pleasure and Open-mindedness at the coffee shop, and Ambition and Success at the
  maker space, which starts 0.1 behind (`writing_base`) because its regulars already crowd it.
  Creativity plays no part, since every crafter has plenty and it already draws people to the maker
  space. Walking time and company count as for any place, so a writer who dislikes crowds goes
  elsewhere when it's busy. Someone writing at home is at home, so nobody seeks them out there.
  Muralists paint the wall the `mural_wall` hook names, standing on its tile, and without a wall
  they don't create.
- **People.** Affinity is a weighted sum of R1's like, trust, respect and familiarity, read from R2
  with `as_of`, or `meet` for strangers. Seeking someone scores their affinity, scaled up by
  Connection. A place scores the affinity of everyone at or heading to it: friends attract,
  people they dislike repel, and a crowd draws high-Connection NPCs and puts off low ones. Nobody
  seeks someone asleep, at home, talking or who refused them in the last 45 minutes.
- **Choice.** The best place for each activity goes into a softmax over activities, so three
  terminals don't make the news three times as likely. `Behaviour(seed=...)` makes it repeatable.
- **Night.** Each NPC has a bedtime (21:00 to 23:45) and a wake time (05:30 to 09:00) from their
  values. Outside them they go home and sleep, whatever the scores say.
- **Indoors.** The coffee shop, noodle bar, maker space and gallery are inside their buildings.
  Walking time to them counts the walk to the door, a step through it and the walk inside, each in
  a straight line (`Places.walk_minutes`), and a walk to them goes through the door. Only someone
  within `near` on the same map is company. A wander from indoors heads out, to somewhere near the
  door.
- **The gallery** is an occasional outing (base -0.1) for the open-minded: Open-mindedness for
  seeing things another way, Knowledge, Creativity for others' art, and Peace of Mind for a quiet
  room. Creativity counts for less than at the maker space, so the makers keep making. A stay of
  15 to 40 minutes meets curiosity, more slowly than the maker space.
- **When.** An NPC decides when their stay somewhere runs out (a few minutes for a wander, up to an
  hour at home or the maker space, an hour and a quarter making something), not every tick. Needs
  update every 5 sim seconds.

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
| `create(npc, wall)` | With the `Npc` when they finish a stay making something, and the wall's id for a mural (`None` for writing) | Does nothing |
| `mural_wall(npc)` | With the `Npc` at each decision, for muralists: a `MuralSpot` with the wall's id and the tile to stand on, or `None` | `None`, so muralists don't paint |

Hooks run inside a tick, so they mustn't block. One that raises is logged and counts as a decline.

If `request_conversation` returns True, both NPCs are paused with the goal `talk <other>` until the
conversation engine calls `resume` on each. Otherwise the seeker hangs around for a few minutes.

## Reading and steering NPCs

| | |
|---|---|
| `pause(npc, talking_to=None)` | Stops their walk and their decisions. Does nothing for the player. |
| `resume(npc)` | They decide again on the next think, or go back to what they were making. |
| `nudge(npc, goal, bonus)` | Adds `bonus` to `goal`'s score at their next decision, which they make on the next think, stopping where they are if walking. False, changing nothing, if they're paused or asleep. The ambient director nudges through it. |
| `available(seeker, other)` | Whether `seeker` could seek `other` out: B1's rules for who is sought, and `seeker`'s cooldowns. |
| `at_home(npc)` | Whether they're at or heading home, to rest, sleep or make something there. |
| `restore(npc, goal, needs, since, until, cooldowns)` | Puts back a saved NPC (I3) after the clock is set: stops their walk and publishes one `GoalChosen`. With no `until` they decide on the next think. Everyone's needs rise from now. |
| `goal(npc)` | Their `Goal`: `activity` and `target`, a location, entity or, for a mural, wall id. |
| `needs(npc)` | `{Need: 0-1}`. |
| `state(npc)` | JSON for F3's `npc_state`: goal, needs (inspiration only with a craft), last decision's scores, bedtime. |
| `minds` | Each NPC's `Mind`, with mutable `needs`. |
| `leave_player_alone` | A set of NPC ids, empty to start. While they're in it they don't seek out the player, and B5 doesn't have them greet the player. |

Every new goal is published on the bus as `GoalChosen(npc, activity, target)`.

## Fast-forward

```bash
cd server && uv run simile behaviour simulate --hours 24 --seed 0
```

Runs memory, world and behaviour on a `FakeWallClock` as fast as the CPU allows (a sim-day in
about 15 s) and prints where everyone spent their time: minutes near others by Connection, places
by hour, who was out at night, and what each resident with a craft made per sim-day. Conversations,
news and works stay stubbed, so nothing calls Claude: there's always an article of middling
interest unread, and reading it does nothing. Muralists paint M7's walls in turn, moving on to
the next after each mural, and making something does nothing. `simulate(..., npcs=...)` runs
another cast.
