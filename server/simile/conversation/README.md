# simile.conversation

NPCs talking to each other, and to the player, in real time. `conversations_of(app)` returns the
server's `ConversationEngine`, created on first use. Its lifespan plugs `request` and `live` into
B1's hooks, hands `player_say` to `PlayerConversations`, and ticks both on the sim loop.

## A conversation

- **Asking.** B1 calls `request(a, b)` when `a` walks up to `b`. `b` accepts if `acceptance()`
  is positive (at `accept_temperature` 0; otherwise with chance `logistic(score / temperature)`).
  It adds up how `b` feels about `a` (R1's like, trust, respect and familiarity, read from R2 with
  `as_of`, or `meet` for strangers), `b`'s values (Connection, Compassion and Open Mindedness for,
  Independence and Peace of Mind against), their social need, which weighs most (someone lonely
  accepts almost anyone, someone who's just talked mostly doesn't), and what they're busy with:
  someone at a terminal or the maker space, or looking for someone else, is less keen, and someone
  who was looking for `a` is very keen. Someone with an urgent need, one at or past B1's critical
  level for it (hunger at 0.9), loses `accept_urgent` (5), which declines even a friend they were
  looking for. `accept_score(a, b)` is that score. Anyone already talking is declined, and so is
  anything beyond `max_conversations` (2) conversations between NPCs. The player's doesn't count:
  I1's `max_voiced` already caps how many are voiced. Requests involving the player go to
  `engine.player_request` (see below).
- **Starting.** Both are paused with B1, which stops their walks, and each turns to face the other.
  `a` opens. On the next tick the engine asks for the script.
- **The plan.** What would have decided engagement turn by turn plans the scene instead. Each side
  gets a keenness from 0 to 1: `initial_engagement` (how much they like the other, and Connection),
  plus `keen_social` times their social need above or below 0.5, `keen_topics` times their topic
  interest, `keen_goal` times what they were doing's `accept_goals` score (`seeking_them` if they
  were looking for the other), less `keen_pressing` times their most pressing want (rest, curiosity
  or news) over `pressing`. Topic interest is how much the values of what both sides are likely to
  bring up matter to them, from -1 to 1: B4's articles behind their news topics and the works they
  might bring up, weighted by how much each relates to each value, or for someone with neither,
  their own top three values. Someone at `leave_below` or less wants to wrap up after `min_lines`,
  someone at 1 after `long_talk` (30), in a straight line between. A need with a critical level in
  B1 (hunger) past `drain_from` (0.75) drains them faster: the lines they'd talk for past
  `min_lines` are divided by up to 1 + `need_drain` (4) at the critical level, in a straight
  line from 1 at `drain_from`. Whoever wants to leave first does (the one approached, on a tie),
  and the scene runs that many lines plus the goodbye and its answer. The direction says each
  side's keenness in words ("keen to talk", "happy to chat", "lukewarm", "would rather not talk"),
  what draws them in (came looking for them, could do with company) and what holds them back (was
  off to read the news, has had plenty of company, itching to catch up on the news): the reasons
  that agree with their keenness in brackets, the others after "though". Then who'll want to leave
  after about how many lines, and the length, ending when the leaver takes their leave and, if a
  need drains them, what it sends them off to do ("to get something to eat"), so
  the goodbye gives the reason.
- **The script.** One L1 `stream()` call with Haiku 4.5 and `purpose="conversation"` writes the
  whole scene. Haiku 5.5 thinks before it writes and can't be told not to: on the same scenes it
  sometimes took over 20 s to its first line, where Haiku 4.5 took 2 to 7 s. The system prompt, the same for every scene, asks for it like a scene in a novel:
  each character knows only their own notes, what's between them and what's been said; they know
  what someone with their life and job would know, and otherwise ask, admit they don't know or give
  their own angle; it's a chat between neighbours, not a consultation; a topic the other doesn't
  take up is let go and nobody goes back over a point; pet words and verbal habits now and then. The
  prompt has, for each side, their persona, backstory, speaking style and mannerisms (as verbal
  habits, to use now and then), values and interests, R1's `describe()` of how they feel about
  the other told in the third person, how their needs feel (see *Needs* below), and, each marked
  as only theirs, any grudge they hold against the other, R2's `recall` (memories of the other,
  then recent or salient ones) and the secrets others told them (open `secret` flags about anyone
  else), the works they might bring up (see *Works*), and B4's `topics_to_raise`. Then what's
  between them, which both know: R2's `shared_history` events and their open debts, promises,
  broken promises and saved lives, and a secret told between them, marked as known only to the
  two. Then where and when they are, and the direction. Each line is the speaker's first name, a
  colon, the line and its `[values: ...]` tag.
- **Works.** Each side's work topics are their memories of works they made, read or saw (`work`
  memories from `simile.works`), up to `works` (2): those about the other first (the other's works,
  or the other painting over theirs), then their strongest by salience × recency, with a
  `works_half_life` of a day, leaving out any below `works_min_score`. Each side also gets their
  memory of making any of their works in the other's topics, so the artist knows a work the other
  might bring up is theirs. In their section, their own works are ones they "might bring up and
  stand by", and both lists are marked as only theirs, with "(Kofi made it.)" after a work when the
  other is the artist. A work memory that's a topic isn't listed again among their memories, so each
  appears once. The engine looks works up through `engine.work`, which the lifespan points at
  `works_of(app)`.
- **Streaming.** Each line is parsed as soon as its newline streams, cleaned like a reply
  (`parse_reply`: tag, stage directions, quotes, cut at the first sentence boundary past
  `max_words`), and played from the first. Lines that don't start with one of the two names
  (narration, headings, anyone else) are left out, and a script is cut at `max_lines`. A script
  with no line within `first_line_timeout` real seconds is asked for once more; if that one misses
  too, the conversation ends before anyone speaks, with a warning. A script that streams to its end
  in under `continue_below` (half) of its planned length, without a goodbye in its last two lines,
  gets one more call, with the lines so far, for the rest ("if it has already ended, write
  nothing"). L1's fakes answer a scene with a whole script (`simile.llm.fake.scene`).
- **Pacing.** A line takes as long as its speaker's voice takes to say it (at least
  `min_line_seconds`), then `turn_gap` before the next. That's the voice's measured rate
  ([*Speaking rates*](../voice/README.md#speaking-rates)), or `words_per_minute` (200) for a voice
  without one. A voiced line whose audio I1 has finished making by the time it's spoken lasts
  exactly as long as its audio instead. And the next line waits while the last one's audio is still
  being made or playing, at most `voice_wait` (3 s) past its end, so speech keeps pace with the
  bubbles. Each line is drafted one line ahead of being spoken, and the script streams far faster
  than it's spoken, so lines follow each other without gaps. `Line.timestamp` is when it starts and
  `Line.duration` how long it lasts. Engagement still moves with each line's values, as for the
  player below, for the debug overlay and the logs, but no longer ends anything.
- **Interruptions.** A resident is pulled out of a conversation when the player starts one with
  them, when their rest, curiosity or news rises past `urgent_need` (0.95) during it, or when a need
  rises past B1's critical level for it, as B1 would pull them away from anything else. The line
  being said finishes, then they say a short goodbye that gives the reason (`GOODBYES`: "Sorry,
  Ana, I'm starving. I'd better get something to eat."), unless they've just said one; if the other
  has, a "Bye" back. Nothing after that is said, and the rest of the script never happened.
  Pulled away before anyone has spoken, the conversation ends with no lines.
- **Ending.** After the last line plays, the conversation ends. So does one whose script fails or
  stops streaming for `line_timeout` real seconds (30) between lines: after its last complete line,
  or with no lines if there wasn't one, which B3 and D1 treat as never having happened. Both NPCs
  resume deciding, unless one is now talking to the player, and neither seeks the other for
  `cooldown` minutes.

Every constant is in `ConversationConfig`.

## Talking with the player

`PlayerConversations` in `player.py` runs conversations between the player and an NPC on the same
engine, so `live`, `conversation(id)`, `talking`, `state` and the events below cover them too. The
player is `Visitor` in prompts (B3 uses the same name), "a newcomer to the village", and NPCs bring
their relationship with `player`, shared history and memories as with anyone else, and the news they
might bring up is their own (B4's `topics_to_raise`), as with a resident. So are their work topics,
as in *Works* above. Nothing the player has read or seen reaches an NPC's prompt. B1 counts a talk
with the player as `player_relief` (half) of one with a resident towards their social need.

- **Starting.** `player_say` to an NPC within `say_range` (4 tiles) starts a conversation, unless
  they're asleep. One put off by the player's bionics turns them down (see *The player's bionics*). One talking to another resident is pulled out of it (see *Interruptions*) and
  answers once that conversation has ended and their goodbye's audio has played. From then on, the player's lines reach the NPC for as long as the
  conversation lasts. Saying something to a different NPC who is awake ends the one going on: the
  old partner says a short canned goodbye, and the new resident's first line waits until it ends.
  Saying it to one who's asleep changes nothing. An NPC who walks up to the player (B1's seek) says
  hello. So does a free NPC within `near` (3 tiles) whose acceptance score beats `greet_bar` (0.5):
  every `look_every` (5 s), each nearby NPC is considered once per `greet_cooldown` (10 min), so
  high Connection NPCs greet strangers and those who dislike the player don't. Nobody greets a
  player who's already talking or not connected, and nobody in B1's `leave_player_alone` greets
  them. Every range here is on the player's own map, so nobody talks through a door.
- **Replies.** Each player line is answered straight away, with no line ahead: one L1 `stream()`
  with `priority=1` and `purpose="player-reply"`. Each sentence becomes its own `Line` as soon as it
  has streamed, with `LineDrafted` at once and `LineSpoken` when the previous sentence has been
  said. A long first sentence is cut after its first clause (a dash or semicolon after 6 words, or a
  comma after 10 that isn't in a list) so its voice starts sooner, and the client shows both pieces
  in one bubble. Sentences are paced as in *Pacing* above, back to back without `turn_gap`. The
  player's lines are spoken when they arrive and have no `LineDrafted`. If the player says something
  while the NPC is still writing or speaking, the NPC stops: the rest of that reply is dropped and
  they answer the new line.
- **News the player mentions.** B4's `mentioned` matches the player's lines since the NPC last
  spoke against each article the NPC read: its title, tags and summary from the news store (looked
  up through `news_of` when needed, or just the title quoted in the memory if it's gone) and the
  topics the NPC took from it. An article counts if they share `NewsConfig.mention_words` (2)
  words, where a word matches its other forms ("colonise", "Colonising"), or if the player names
  the news ("news", "article", "piece", "story", "headline", "read", "paper") and one word is in its
  title, or is one of its one-word tags or topics, exactly, give or take a plural ("Did you see the
  Mars piece?"). A tag like "life sciences" only counts towards the two words. The NPC's
  memory of each article that counts, with their take, follows the transcript in that reply's
  prompt, for at most `mentions` (2) articles, most shared words first. An NPC who didn't read it
  gets nothing and answers from their values.
- **What stuck from one article.** A prompt gives the points a resident kept from one article at
  most (`Memory.points`, "What stuck with you from ..."): in a reply, the article the player just
  mentioned or else their first news topic, after the transcript, and in a scene, the first topic
  with points, the opener's before the other's, in that side's section.
- **Works that have come up.** Each reply's prompt lists the NPC's work topics after the background,
  their own and others' in two lists. A work has come up once a line names its title (quoted, as
  written if it's more than a word, or in any case beside a word for a work or its artist), names a
  mural's wall beside a word for a mural ("mural", "painting", "wall"), or has two of: words from
  its title, tags or topics, however many, other than words for a work; a word for a work ("mural",
  "poem", "piece", "the notice", ...); and its artist (their first name, or for the NPC's own work,
  "my mural" in their line or "your mural" to them). It's left out of the prompts after the NPC's
  next reply, which still has it.
- **Latency.** Replies use `PlayerConfig.model`, Haiku 4.5, because Haiku 5.5 can't turn thinking
  off (see [`llm/README.md`](../llm/README.md)). The nearest free NPC within `near` gets a warm
  Claude Code process for their reply (`llm.warm`), and so does the NPC after each reply.
- **What they know.** The resident's system prompt adds that they know what someone with their life
  and job would know, and otherwise ask, admit they don't know or give their own angle rather than
  expert advice; that it's a chat between neighbours, not a consultation; and that when the player
  changes the subject they go with it, or say once that they'd rather not and let it go.
- **Engagement.** The NPC starts from `start_engagement`, more if they like the player or value
  Connection. After every line they lose `fatigue`, faster with a pressing need as in *The plan*
  above (`drain_from`, `need_drain`), and gain `topic_weight` times how much the values
  it brings up for the first time in the conversation matter to them (from -1 to 1) plus
  `like_weight` times how much they like the player. Each player line and each reply counts as a
  line, and each player line touches the values the NPC's last reply did.
- **Ending.** From `min_lines` on, an NPC whose engagement is below `leave_below` answers with a
  goodbye. With a pressing need, its cue says what the need sends them off to do and asks them to
  say why they're going. A player line within `farewell_wait` (8 s) of that goodbye joins the
  conversation and ends it. If the player says goodbye ("bye", "see you", "gotta go", ...), the
  NPC says goodbye back and it ends. It ends at once if the player walks beyond `leave_range` (6
  tiles) or disconnects. After `silence` (60 s) without a word from the player, the NPC says
  goodbye, or just leaves if the player never answered their hello. A reply that fails or says
  nothing ends it too. Cooldowns are as in B2.

Every constant is in `PlayerConfig`.

## Needs

`needs.py` reads B1's needs live, through `behaviour.needs` and the critical levels in
`behaviour.config.urgency`, and `engine.pressing(npc)` is what they bring to a conversation now.
*Asking*, *The plan*, *Interruptions* and B5's *Engagement* and *Ending* above say what that does.

The prompts describe needs in words, never numbers: each reply to the player has "Right now you're
hungry and tired." after the background, and each side of a scene "Right now Ben is starving."
`MOODS` has the words and where each starts: hungry from 0.75 and starving from 0.9, and tired from
0.6 and exhausted from 0.9. A hungry, tired resident comes across short, and B3 picks that up
from the transcript like anything else.

## Rough edges

Left alone, the model makes everyone kind, candid and agreeable, so low scores become direction.
`rough_edges(npc)` gives a sentence for each low value, stronger below each of 0.4, 0.25 and 0.15
(`LOW`):

- **Honesty:** they shade the truth when it suits them, then lie when it suits them, then lie
  easily and without guilt.
- **Compassion:** they won't soften bad news, then are short with complaints and put themselves
  first, then have no patience for complaints at all.
- **Peace of Mind**, the value that pulls Agreeableness most: they say when they disagree, then
  don't give ground to keep the peace, then can be curt or change the subject.
- **Self-respect** of `HIGH` (0.6) or more with low Compassion: they turn down favours and say no
  without apologising.

B5's system prompt has them after the values, and each side of a scene in the third person
("Henrietta will lie when it suits them"). Every resident's prompt, and the script's rules, also
say not to agree just to be pleasant, and keep to the game's tone: no slurs, abuse or cruelty,
rudeness is curtness and never insults, and a lie stays small and in character, about the speaker,
their reasons, plans or what they did or saw. Nobody makes up facts about the village, its places,
times or people.

## Humour

Left alone, the model jokes in about one reply in twenty, and the same mild way for everyone. A
resident's `humour` (a style and a seriousness, see `simile.characters.humour`) becomes a line after
how they speak, and code decides which lines joke, as it decides lies.

- **The line.** B5's system prompt says it in the second person ("Your humour is dry: understatement
  and wry asides, said plainly. You joke now and then, never in every line."), with the bounds on
  jokes: never cruel, never punching down, and sarcasm dry, never insulting. Seriousness under 0.35
  is "a lot", under 0.65 "often", under 0.9 "now and then", and otherwise "rarely". A `none` style
  is "You are not one for jokes: you say what you mean." A scene has the line for each side in the
  third person, and when either side has a humour, its rules carry the bounds.
- **The roll.** Each B5 reply rolls for a joke with a chance of 1 minus their seriousness, seeded by
  the conversation, the resident and the line, but never straight after a reply that was told to
  joke, so no two replies running joke. The reply prompt says "Work a joke into this line, in your
  own humour." or "No joke in this line: say it plainly." A scene's plan rolls each side's lines
  the same way, seeded by the conversation, and the direction says how many of them joke, never
  all of them.
- Without a humour, nothing is added and the prompts are as they were, scenes included when
  neither side has one.

## Lies

The model avoids deceiving even in character, so code decides when a resident lies, and the prompt
tells the model what the lie is (`temptation.py`).

- **Temptations.** What the game knows a resident would rather not own up to, with no Claude call:
  being short of money (E3's money against their savings target, as for loans); a debt, secret or
  grudge someone holds about them (open `debt`, `secret` and `grudge` flags); a promise they broke
  (B3's "I told Ana I'd ..., and didn't." memory); a shift they skipped or were late to (E3's turns,
  through `engine.missed`); a work of theirs someone's memory of is at or below `went_badly` (-0.3).
  Broken promises and shifts count for `tempted_for` (2 days). In a conversation with the player,
  the player's lines can raise two more: being asked to cover for them, or a complaint about
  something of theirs.
- **Touched.** A temptation comes up when the other's words match it: the player's lines since the
  resident last spoke, or in a scene what the other might bring up (their memories and topics, news,
  works and secrets) and what's between the two. Each kind has its own words in code (`CUES`), and
  the words of what it's about (the promise, the workplace, the work's title, the flag) count too.
  In a scene, someone it's about (the lender, who knows the secret, ...) being there touches it.
- **The roll.** A touched temptation is lied about with a chance from Honesty: none from
  `honest_from` (0.6), rising in a straight line to `lie_most` (0.7) at `lie_peak` (0.1) and below.
  #185's negativity bias bends it by `lie_bias` (1.5): owning up is a bad turn, and weighs more
  with them. The roll is seeded by the conversation's id, the resident and the temptation, so it's
  the same every time it comes up in that conversation.
- **The direction.** On a lie roll, B5's reply prompt has it after the background ("You are short
  of money this week. If it comes up, say you're doing fine.") for the rest of the conversation,
  and a scene's direction has it in the third person. Without a roll nothing is added. The lies
  stay within *Rough edges*' bounds: about the resident, what they did and what they'll do. Each
  direction ends "Use that cover story and nothing else: no days, times, places or other people."
- **For B3.** `engine.lies(conversation_id)` hands over, once, the lies a conversation set up: who
  was to lie to whom, about what, and whether the listener's own flags already hold the truth (who
  lent them money, knows the secret or holds the grudge). Nobody is set up to hide being short or a
  debt in a scene set up for them to borrow or pay back.

## Telling

What residents know of S12's incident ([`simile.story`](../story/README.md)) comes up only with the
player, and only as their trust allows (`telling.py`). `engine.incident`, which the lifespan points
at the saved investigation, is the incident.

- **Asked.** Once the player's lines since the resident last spoke mention Aris or the attack (Aris,
  the mechanic, her workshop or steel hand, what happened to her or at the workshop, who smashed up
  the workshop, the break-in, the attack, ...: `CUES[Kind.FACT]`; "a heart attack", everyday
  talk of the maker space, "that night" or "where were you" alone don't count), the resident is set
  up, for the rest of the conversation, for each fact they know
  (`engine.tellings(npc, PLAYER_ID)`), by R1's trust in the player then:
  - from the knower's `tells_from`, they **tell** it: "You remember this, and trust Visitor enough to
    tell them if they ask:" and their first memory of it, so a lie they told since never takes its
    place;
  - below it, with a `cover`, they **lie**: it's one of the lies above, of kind `fact`, with no
    roll, since trust has already decided it. Its direction ties the cover to the one question it
    answers, without the truth: 'You won't say where you'd been the night Aris was attacked. Only
    if asked that, say exactly: "I was at home all night."' After the lies, once, they're told never
    to volunteer a cover story or add a denial of their own;
  - below it, without a cover, they **keep it back**: one paragraph, however many facts, says they'd
    rather not talk about it, without denying that they know something.

  Their memory of a fact they lie about or keep back isn't in the prompt, so it can't slip out.
- **Elsewhere.** The incident's memories are out of R2's `recall`, so they're not on anyone's mind
  in a scene, a reply or a work until the player asks. After that, B3 remembers the conversation
  like any other: a resident who told the player something remembers telling it, which `recall`
  returns. A lie's direction holds no truth, and both the liar's memory of lying and their summary
  of that conversation carry the fact's id (`Lie.fact_id`), so `recall` leaves them out. Residents
  don't tell each other what they know.
- **For other modules.** `PlayerTalk.tellings` has what the resident was set up to say about each
  fact, by its id, with the `Stance` (`tell`, `lie` or `keep`). Each lie is also in `talk.lies`, with
  `Temptation.fact_id`, and in `engine.lies` for B3.

## The player's bionics

S11 ([`simile.social`](../social/README.md#bionics)) decides how residents take to the player's
bionics. The lifespan points `engine.looks` at its sightings.

- **What they see.** The first paragraph of each reply's background ends with what the resident
  can see of the player: each bionic fitted, which are new to them, and how they feel about
  bionics ("Visitor has an infrared eye that glows faintly red in place of one of their own. The
  infrared eye is new since you last saw them. Bionics make you uneasy."). A whole player gets
  nothing, and the prompt is as it was. Scenes between residents have no player to see: word of a
  sighting reaches them through the memory it leaves, on the sighter's mind like any other.
- **Keeping their distance.** B1's `unease` comes off the accept score for the player,
  `accept_unease` (2) times it, so an uneasy resident doesn't greet them. One the player talks to
  turns them down when that score declines, as it would an NPC's request: their one reply is cued
  "You'd rather not talk to Visitor. Turn them down in a few words, and leave it there.", and the
  conversation ends as after a goodbye. Only someone uneasy turns the player down, never at work,
  and someone talking with another resident doesn't break off to do it: the player gets no answer.
  A lower trust from a sighting also makes them tell less of the incident (*Telling* above).

## Only promising what's possible

B3 turns what a resident says they'll do into an intention that B1 acts on (see *Intentions* in
both READMEs), so the prompts say what they can do. Each side of a scene, and the background of
each reply to the player, has what they could plan to do in the village, from B1's
`options(npc)`: go home or to the village's places by name, read the news at a terminal, look
someone up, and where they'd make something now ("write at home, The Daily Grind or Spark Maker
Space", "paint a mural on the banyan row wall", or for a muralist with no wall, a canvas at home
for the gallery or nothing). They only promise what's on the list, and nothing further off than
tomorrow. Then what they've already said they'd do, each with whom they told and when ("now",
"today 15:00"), to keep to.

Someone who has said they'll go and do something now says where they're off to as they leave: the
script's rules say so, and so do B5's goodbye and farewell cues, so the player can follow them.

## Loans

E6: a resident who's short of money asks a friend to tide them over, and pays it back once they
can. `loans.py` decides at the start of each scene, from what each side holds (B1's `money` hook,
which E3 plugs in) and their savings target (`behaviour.savings`), and the direction says what
happens. Without the economy nobody asks.

- **Paying back.** Someone who owes the other a loan (R1's `owed`) pays it back once that leaves
  their finances below `borrow_from` (0.6): "Ana has the money now, and pays back the 100 Ben lent
  them."
- **Asking.** Otherwise someone whose finances are at least `borrow_from` asks the other if they
  like them at least `ask_like` (0.6), don't owe them already, and weren't turned down by them in
  the last `ask_again` (24 sim hours). They ask for what takes them back to their savings target,
  in tens, at most `max_loan` (100).
- **Trust decides.** The lender lends if they trust the borrower at least `lend_trust` (0.6), as
  much as they have above their own savings target, in tens: "Ben trusts Ana and lends it", "Ben
  can only spare 40, and lends that", "Ben can't spare it, and says no", or "Ben doesn't trust Ana
  enough to lend money, and says no".

- **One at a time.** Until B3 has reflected on a scene set up for a loan, the loan is pending: no
  other scene between the two settles anything, and the borrower of a pending ask asks nobody
  else. So two scenes in quick succession never lend twice.

`engine.settle(conversation_id)` hands B3 the loan a live or recently finished scene was set up to
settle, once, which ends it pending. B3 moves the money: see its README. Nothing changes for the
player, who has no money.

## Events

| Event | When |
|---|---|
| `ConversationStarted(conversation)` | It starts, with no lines. |
| `Facing(entity, toward, direction)` | Each participant turns to the other, `direction` being `down`, `left`, `right` or `up`. On a side-view map it's `left` or `right`, or `down`, towards the camera, for someone straight above or below. |
| `LineDrafted(line)` | A line is written, before its turn. Its `timestamp` is when it'll be spoken. |
| `LineSpoken(line)` | At `line.timestamp`, with the same line. F3 sends it to clients as `line`. |
| `ConversationEnded(conversation)` | It ends, with every line and `ended` set. |

`ConversationStarted` and `ConversationEnded` carry copies; lines are never changed after they're
published.

## For other modules

- **Transcripts (B3).** Subscribe to `ConversationEnded`. Its lines are the ones spoken: the rest
  of a script cut short never happened. `engine.conversation(id)` returns a live or recently
  finished conversation, and `engine.finished` keeps the last `keep_finished` (50).
- **Player conversations (B5).** Conversations with the player have `player` as a participant
  and publish the same events, with the player's lines included.
- **Voicing (I1).** `LineDrafted` gives each NPC line's text one line ahead of `LineSpoken`. In a
  conversation with the player, each line is a sentence and `LineDrafted` comes as soon as it has
  streamed, so voicing can start on the first sentence. A sentence dropped because the player talked
  over the NPC or left, or a scripted line drafted before an interruption, gets a `LineDrafted` but
  no `LineSpoken`.
- **Debug overlay (I2).** `engine.state(npc)` has their conversation, who they're talking to,
  engagement, facing and whether they're saying goodbye.
- **Ending one now (I3).** `engine.end(conversation_id)` ends a live conversation at its last
  spoken line, dropping any line still being written or waiting, and returns it with `ended` set,
  or None if it isn't live. `ConversationEnded` follows as usual, so B3 reflects on it.
- **Pulling someone away.** `engine.cut(npc, why)` pulls a resident out of a conversation with
  another, as in *Interruptions*, for `why`: `PLAYER` or a `Need`. It returns when they've finished
  their goodbye, or None if they weren't in one.
- **The ambient director.** `engine.accept_score(a, b)` says how keen `b` would be if `a` walked up
  now, so [`simile.ambient`](../ambient/README.md) only nudges pairs who would accept each other,
  and nobody with an urgent need.
- **Writing an NPC's replies to the player.** `app.state.players` is the server's
  `PlayerConversations`. `players.writers[npc]` is an async function of the cue and the lines so
  far that returns the NPC's reply, which is paced and voiced like any other, or None for B5's own.
  `players.interject(npc, text)` has the NPC say `text` to the player now, in their conversation or
  opening one, and is False if either is talking to someone else. The café
  ([`simile.cafe`](../cafe/README.md)) takes orders this way.

## Without Claude

`SIMILE_LLM=fake` makes L1 answer every call with a few stock lines, so a run never reaches Claude.
The test suite sets it for every test.

```bash
cd server && SIMILE_LLM=fake SIMILE_DB=:memory: uv run simile headless --speed 20 --duration 1
```
