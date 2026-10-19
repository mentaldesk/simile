# simile.behaviour

What each NPC does next. Every NPC has needs that rise over time, and when they've been somewhere
long enough they score every option and pick one, walking there with W2's `walk_to`.

`behaviour_of(app)` returns the server's `Behaviour`, created on first use with N1's NPCs from
`content/npcs/`. Its lifespan puts every NPC at home, ticks the decision loop on the sim loop, and
sets F3's snapshot to the NPCs' real positions.

## Deciding

- **Activities.** Go home, the coffee shop, the square, a news terminal, the park, the noodle bar,
  the maker space, the gallery, wander, go for a walk (`exercise`), seek someone out (an NPC or the
  player), idle, make something (`create`), or go to work. `sleep` and `talk` are set by the loop
  rather than chosen.
- **Score** = base + values + relief − price + work + time of day + people − walking time. Values enter as
  `weight * (value - 0.5)`: Connection pulls towards people, PeaceOfMind home and to the park (and
  away from seeking company), Adventure to wander, Creativity to the maker space, and
  Open-mindedness, Knowledge, Creativity and Peace of Mind to the gallery. The coffee shop peaks in
  the morning and home in the two hours before bed. The activity just finished scores less.
- **Relief.** Needs (`social`, `curiosity`, `rest`, `news`, `inspiration`, `hunger`, `boredom`,
  `relaxation`, `exercise`, 0 to 1) rise over time, and being somewhere changes them by its `effects` each hour.
  Each need has an urgency curve, `need ** power` (`urgency`, 3 unless it says otherwise), and one
  function prices any change to it (`worth`): its weight times the area under the curve between
  the level before and after. An option scores the relief it would bring over a typical stay
  (`effects` over the middle of its `dwell`, plus its `finishing`; seeking someone out promises
  `talk_minutes` of talking), so adding a need to a place's `effects` is enough to send people
  there for it. The same relief is worth far more to someone desperate than to someone who's just
  had it: on `need ** 3`, a meal from hunger 0.9 to 0.3 is worth 80 times the same meal straight
  afterwards.
  Curiosity and rest are on straight lines (`power` 1), as they always pulled. Curiosity is met
  fastest at the maker space, but also at the square, the coffee shop, the park, the gallery, by
  wandering and by reading, so it sends people all over town rather than into one room.
- **Loneliness.** `social` is on `need ** 3`, so a little barely registers and a lot crowds out
  everything else. Connection sets how fast it rises (Peace of Mind slows it), so high-Connection
  NPCs get lonely and go looking for company, and low-Connection ones mostly keep to themselves.
  Talking meets it fast. Talking with the player meets `player_relief` (0.5) of that, and seeking
  them out promises only as much, so a chatty player doesn't become the village's social life.
- **Sociability.** A resident's P1 `sociability` trait, from the world's cast, multiplies how fast
  `social` rises and divides how fast talking meets it, by up to `sociability_spread` (2) at 1, and
  the other way round at 0. So a sociable resident gets lonely sooner and takes longer to have had
  enough: they look for company more often, and come to a conversation lonelier, which the
  conversation engine reads as keener to talk. Neutral (0.5), as for everyone in today's village,
  changes nothing.
- **Hunger.** Hunger goes from full to urgent in 4 to 5.5 hours (faster with Pleasure). Asleep, it
  rises at `rise_asleep` 0.3 of that, so they wake hungry and breakfast puts the next meal around
  midday. Home meets it slowly, and the noodle bar and the coffee shop quickly. They only eat
  once hunger reaches its `appetite` (0.75), and then until they're full or leave, so a coffee
  isn't a meal. Nothing on the clock says when to eat. P1's traits don't touch it.
- **Urgent needs.** Above its `critical` level (0.9), hunger makes them drop what they're doing
  and decide again straight away, walking off mid-stay or mid-walk, unless what they're doing
  meets it. A stay cut short brings none of its `finishing`. Being held lets go too, but only
  then: the café's customers and barista are held at the coffee shop, which feeds them. Asleep or
  talking, nobody's interrupted. Wants (social, curiosity, rest, the news, inspiration) never
  interrupt.
- **What's there.** A place meets a need only as far as the `supply` hook says it can now, 0 to 1,
  in what it scores and what it does. E4's economy plugs it in: a shop feeds people only while
  it's staffed and its batch lasts, and home only while there's food in the fridge. The café wraps
  it, so the Daily Grind also feeds nobody while its barista is off shift. A meal once started
  is finished, even if it was the last or the place shuts.
- **Money.** `finances` is how far their money (E3's `money` hook) is below their savings target,
  as a share of it, so it doesn't rise on its own. The target is `savings` (300), raised by
  Security. A price is valued on finances' own curve, a straight line (`power` 1, weight 100)
  that has no ceiling, so it barely registers for someone at or above their target, bites
  harder the shorter they are, and still counts once they have nothing. Pleasure makes a price
  feel smaller (`thrift_values`). The `price` hook says what a goal would cost: groceries for a
  meal at home, a drink and a meal at the shops.
- **Work.** A resident with a `workplace` and `shifts` sets off for each shift `punctuality` (15)
  minutes early at Discipline 1 and as late at 0, give or take `set_off_jitter`, after the walk
  from home. From then until the shift ends work scores `shift_weight` (2) more: less than an
  urgent meal is worth, so an urgent need still wins, and they decide then and there, dropping
  what they're doing. A shift gets them up `ready` (45) minutes before they set off, in time for
  breakfast. Once there they stay until it ends: a talk only pauses it, as it does making
  something, and urgent needs take them off for a while. Each working day, they skip its shifts with a
  chance of up to `skip` (0.3) at Responsibility 0, falling to nothing at `skip_below` (0.5), and
  less the shorter of money they are, so a split shift doesn't double the chance of missing work. After a shift, a wage earner still at work can stay on for up to
  `overtime` (2) hours, a stay of `dwell` at a time, scored by Ambition and Success
  (`overtime_values`) and what it pays (the `earnings` hook) on the finances curve, so the
  ambitious and the short of money stay on. Working at home is being at home, so nobody seeks
  them out; working at a shop they live above isn't.
- **The news.** `news`, wanting to catch up, is on the same kind of curve (`need ** 2`), and only a
  terminal meets it. It rises with Knowledge and Open Mindedness and falls for NPCs low in both,
  so some read every couple of hours and some never do. The `news_interest` hook says how
  interesting the best article they haven't read is (0 to 1), and a terminal's relief is scaled by
  it, so a gripping article pulls harder than a so-so one. With nothing worth reading, the
  terminals aren't an option.
- **Making things.** Residents with a craft (`Npc.craft`) have an `inspiration` need, on the same
  kind of curve as the news (`need ** 2`, from a lower base), so it builds slowly and then wins. It
  rises with Creativity and Self-actualization, on its own from about one work every two and a
  half sim-days for the least creative crafter to one a day for the most, and never without a
  craft. `create` meets it: a stay of about an hour, and the need is met all at once as they leave
  (`finishing`), when B1 calls the `create` hook. A stay cut short by a nudge or bedtime makes
  nothing, but a talk only pauses it, and afterwards they go back for the rest of the stay. Nobody
  starts one with less than a typical stay left before bed, or with a need past its critical
  level.
- **What stirs them.** Each new memory a crafter forms raises their inspiration too: a
  conversation, with a resident or the player, an article read, or someone else's piece read or
  mural or painting seen (`inspiring`), but not making their own, nor anything from before the game.
  B1 hears of each from the memory store (`MemoryStore.listen`). A memory adds `inspiration_weight`
  (0.15) × its salience × its intensity, where intensity is `calm` (0.3) + 0.7 × |valence|, so a
  strongly felt memory counts for more. It adds `inspiration_craft` (1.5) times as much again if
  its topics touch their craft (a word of its medium, `craft_words`, or of its form), and
  `inspiration_values` (0.5) more if they touch one of their 3 strongest values (`value_words`).
  One memory adds at most `inspiration_cap` (0.35), and memories at most `inspiration_hourly` (0.4)
  a sim hour. Talking through a mural idea with the player (salience 0.8, valence 0.7, "mural
  idea") takes Kofi from 0.30 to 0.58, close to the 0.65 at which he'd go and paint, and the work
  draws on his strongest memories, so what stirred him is what he makes.
- **A fresh start.** Inspiration starts between 0 and 0.8, and the `head_starts` (2) crafters with
  the most who are awake at home, aren't muralists (who need a wall) and aren't off to work start
  partway through making something at home, with `head_start` (4 to 12) minutes left. So the first
  new work comes within about a quarter of an hour, and then about one an hour across today's
  village (`simulate` below).
- **Where they make things.** Writers write, and painters paint for the gallery, at home, the
  coffee shop or the maker space, wherever their values fit best (`writing_places`): Peace of
  Mind, Independence, Security and Tradition at
  home, Connection, Pleasure and Open-mindedness at the coffee shop, and Ambition and Success at the
  maker space, which starts 0.1 behind (`writing_base`) because its regulars already crowd it.
  Creativity plays no part, since every crafter has plenty and it already draws people to the maker
  space. Walking time and company count as for any place, so a writer who dislikes crowds goes
  elsewhere when it's busy. Someone writing at home is at home, so nobody seeks them out there.
  Muralists paint the wall the `mural_wall` hook names, standing on its tile, and without a wall
  they don't create. When it's a muralist's turn to paint for the gallery, the gallery's hook names
  their home instead.
- **People.** Affinity is a weighted sum of R1's like, trust, respect and familiarity, read from R2
  with `as_of`, or `meet` for strangers. Seeking someone scores their affinity, scaled up by
  Connection. A place scores the affinity of everyone at or heading to it: friends attract,
  people they dislike repel, and a crowd draws high-Connection NPCs and puts off low ones. Nobody
  seeks someone asleep, at home, talking, out strolling or who refused them in the last 45 minutes.
- **Intentions.** What a resident said they'd do (an `Intention`, which B3 extracts from
  conversations) is one of these options: make something (`create`), go to a place (`go`), look
  someone up (`seek`) or read the news (`news`). From when it's due until it's done or expires,
  each option that does it scores `promise_weight` (2) more, as a shift does: any `create` unless
  it names a wall or place that's on offer, any terminal unless it names one, the place for `go`,
  and the person for `seek`. It isn't forced: nothing is added while a need is past its critical
  level, so they eat first and then go. When one falls due they drop what they're doing, once, to
  decide again, unless they're doing it already, on a shift or have an urgent need.
  - **Reliability.** When it falls due they decide once whether to follow it through. Reliability
    is the weighted mean of Responsibility (0.6) and Discipline (0.4), and they let it slide with a
    chance of up to `lapse` (0.3) at 0, falling to nothing at `reliable_from` (0.5). Then it gets
    no bonus and usually expires. None of P1's traits bears on follow-through.
  - **Making something.** One to make something they follow lifts their inspiration to
    `inspiration_start` (0.65) when it falls due. A muralist still paints the wall `mural_wall`
    names (`Walls.pick` prefers one they said they'd paint), or with the gallery's turns a canvas
    at home, and without either can't keep it.
  - **Done.** It's kept as soon as they start on it: when they arrive at the place, terminal,
    wall or writing place, or start talking with whom they meant to look up, even if they didn't
    choose it for the bonus, from `keep_early` (60) minutes before it's due. One to make
    something is kept by the next stay making something, whenever it is, and the work they make in
    that stay is that one: B1 hands it to the `create` hook. A stay cut short makes nothing, as
    always.
  - **Expiry.** One that's still open at its `expires` is dropped as broken. B3 sets it when it
    extracts one, from its config.
  - At most `intentions` (3) are open at once, and the same kind and target only once.
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
- **Stays.** A stay lasts from the shortest to the longest of its `dwell` (15 to 60 minutes at
  home or the park, 15 to 45 at the coffee shop). From the shortest on they look again every
  `reconsider` (2) minutes, and leave once the best other option, less `switch` (0.15), is worth
  more than staying on for another typical stay. Staying is scored like any option but with no
  walk, nothing new and no repeat penalty, a meal they've started counts whatever their appetite,
  and a stay that relieves nothing adds to their boredom. So a stay ends once it has done what it
  can for them. Making something (`seen_through`) lasts a draw between the two, since its worth
  comes at the end, and a shift lasts until it ends.
- **Boredom** rises only while a stay relieves little: at its full rate where nothing is relieved,
  and not at all once what's relieved an hour is worth `relieved` (0.5) on the needs' curves. It
  rises faster with Adventure, Freedom and Open-mindedness, and more slowly with Peace of Mind and
  Tradition. Anything new meets it: arriving somewhere other than their last stay (`novelty`, 0.3,
  but not home, work or idling), talking, reading an article, making something, a walk, and a
  night's sleep. It's on a straight line (`power` 1), so a little registers.
- **Variety.** Before leaving, a bored resident may move to another free spot in the same place
  that suits what they're there for: another painting, the bar, or a bench with a friend on it,
  chosen as W2 chooses spots. It eases boredom by `new_spot` (0.15), and they move once that's
  worth more than `spot_switch` (0.04). A place without spots has nowhere to move to.
- **Relaxation**, separate from `rest`, which is sleepiness. It rises slowly awake, faster with
  Peace of Mind and Pleasure, at work, making something and at the maker space, and in busy places:
  `busy` (0.03) an hour for each other person near them out of home, up to `crowd_cap`, divided by
  the sociability trait's factor, so a crowd wears out a loner faster. It's met sitting in the park
  (on a bench over Lotus Lake), at the gallery, reading at a terminal, at the coffee shop and at
  home, fastest in the park. So residents aren't always busy, and their lingering looks chosen.
- **Exercise** rises through the day, faster with Discipline and Adventure, and a walk meets
  it. A walk goes round one of the `loops` on the village map, around Lotus Lake or through the
  village, lap after lap from the tile nearest them, for 15 to 40 minutes or until it stops paying.
  A wander meets a little.
- **Wandering** is a stroll from one tile to another near it, for 3 to 10 minutes.
- **Idle** is a fallback: 1 to 3 minutes standing where they are, scored below everything else.
- **When.** An NPC decides when their stay somewhere stops paying or runs out, not every tick. Needs
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
| `create(npc, wall, intention)` | With the `Npc` when they finish a stay making something, the wall's id for a mural (`None` for writing), and the `Intention` the stay kept, or `None` | Does nothing |
| `mural_wall(npc)` | With the `Npc` at each decision, for muralists: a `MuralSpot` with the wall's id and the tile to stand on, or `None` | `None`, so muralists don't paint |
| `supply(goal, need)` | For a goal at a place, when scoring it and while someone's there: how much of what it does for `need` it can do now, 0 to 1 | 1 everywhere |
| `money(npc)` | With the `Npc` every think: what they hold, or `None` | `None`, so finances stay at 0 |
| `price(npc, goal)` | With the `Npc` for each option: what it would cost them | 0 |
| `earnings(npc, goal)` | With the `Npc` for staying on at work: what an hour pays | 0 |

Hooks run inside a tick, so they mustn't block. One that raises is logged and counts as a decline.

If `request_conversation` returns True, both NPCs are paused with the goal `talk <other>` until the
conversation engine calls `resume` on each. Otherwise the seeker hangs around for a few minutes.

## Reading and steering NPCs

| | |
|---|---|
| `pause(npc, talking_to=None)` | Stops their walk and their decisions. Does nothing for the player. |
| `resume(npc)` | They decide again on the next think, or go back to what they were making. |
| `nudge(npc, goal, bonus)` | Adds `bonus` to `goal`'s score at their next decision, which they make on the next think, stopping where they are if walking. False, changing nothing, if they're paused, held or asleep. The ambient director nudges through it. |
| `hold(npc, target, goal)` | Walks them to `target` (a location id or tile) and keeps them there with `goal` until `release`: no decisions, no sleep, and nobody seeks them out. A talk pauses the hold, and afterwards they walk back. The café keeps its barista at the till and its customers in the queue this way. |
| `release(npc, stay=None)` | Ends a hold. With a `stay` they keep the held goal where they are for that long, as if they'd just arrived, and can be sought out; otherwise they decide on the next think. |
| `available(seeker, other)` | Whether `seeker` could seek `other` out: B1's rules for who is sought, and `seeker`'s cooldowns. |
| `at_home(npc)` | Whether they're at or heading home, to rest, sleep or make something there. |
| `working(npc)` | Whether they're at their workplace working: there for work, or held there with a goal at it. |
| `savings(npc)` | Their savings target, in money. |
| `restore(npc, goal, needs, since, until, cooldowns)` | Puts back a saved NPC (I3) after the clock is set: stops their walk and publishes one `GoalChosen`. With no `until` they decide on the next think. Everyone's needs rise from now. |
| `goal(npc)` | Their `Goal`: `activity` and `target`, a location, entity or, for a mural, wall id. |
| `needs(npc)` | `{Need: 0-1}`. |
| `inspire(memory)` | Raises the owner's inspiration for a new memory, within the caps, and returns by how much. The lifespan hands it every memory stored. |
| `traits_of(npc)` | Their `Traits` from the cast, or neutral ones. |
| `state(npc)` | JSON for F3's `npc_state`: goal, needs (inspiration only with a craft, finances only with money), money, their next shift, last decision's scores, which of those an intention raised and by how much (`reasons`), their open `intentions` (with `following`, null until due), bedtime. |
| `intend(intention)` | Takes on what a resident said they'd do. False, changing nothing, if B1 couldn't act on it (a place that isn't one of B1's, someone who isn't here, `create` without a craft, an unknown terminal), it has expired, or they already have it or `intentions` open. |
| `intentions(npc=None)` | A resident's open intentions, or everyone's, soonest due first. |
| `restore_intentions(intentions)` | Puts back saved ones (I3), after the clock is set, for residents still here. |
| `options(npc)` | What they could say they'll do now, by B1's ids: the places they can go (home included), the terminals, and where they'd make something (their writing places, or for a muralist what `mural_wall` names). B2's and B3's prompts list it. |
| `minds` | Each NPC's `Mind`, with mutable `needs`. |
| `leave_player_alone` | A set of NPC ids, empty to start. While they're in it they don't seek out the player, and B5 doesn't have them greet the player. |

Every new goal is published on the bus as `GoalChosen(npc, activity, target)`, every intention
kept as `IntentionKept(intention)`, and every one that expired as `IntentionBroken(intention)`.

## Fast-forward

```bash
cd server && uv run simile behaviour simulate --hours 24 --seed 0
```

Runs memory, on an in-memory store, world, behaviour and E3's economy on a `FakeWallClock` as fast
as the CPU allows (a sim-day in about 15 s) and prints where everyone spent their time: minutes
near others by Connection, places by hour, who was out at night, the share of waking time in each
place, every meal by the hour it started and where, each need's mean, most and time at 0.9 or more,
the longest anyone was awake and urgently hungry, what each resident with a craft made per
sim-day, when the first work came and how many came a sim hour after it, each place's share of
stay time spent on a spot, and the share of waking time walking, talking and still in each place,
and of that, off a spot. Then every shift (on time, late, skipped, hours and overtime), the hours
each shop was due on shift, staffed and sold out, every batch, the grocery orders, each resident's
money every 12 sim hours, and where the money went. The economy decides when the shops serve. The
café doesn't run, so whoever arrives at the Daily Grind while its barista is at work and hasn't had
a drink in the last 90 minutes is served one, as the café does. Conversations,
news and works stay stubbed, so nothing calls Claude: there's always an article of middling
interest unread. Reading it, and each conversation, leaves a stand-in memory of middling strength
on two topics from a short list, so new memories raise crafters' inspiration. Muralists paint M7's walls in turn, moving on to
the next after each mural, and making something does nothing. `simulate(..., npcs=..., traits=...)`
runs another cast.

Every request to talk is declined unless you pass `--talk MINUTES`: then each is accepted, the
conversation lasts that long, and the summary adds how many conversations each resident started,
by sociability, and how many there were a sim hour.

With `--intentions HOURS`, every that many sim hours each resident who's awake says they'll do
something at random, to someone at random: half due now, to expire 2 sim hours later, and half due
in 1 to 6 hours, to expire a day after that. The summary adds how many each took on, kept, broke
and still had open, by reliability, how long after falling due they were kept, and the longest any
was seen open past its expiry.
