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
  who was looking for `a` is very keen. `accept_score(a, b)` is that score. Anyone already talking
  is declined, and so is anything beyond `max_conversations` (2) conversations between NPCs. The
  player's doesn't count: I1's `max_voiced` already caps how many are voiced. Requests involving
  the player go to `engine.player_request` (see below).
- **Starting.** Both are paused with B1, which stops their walks, and each turns to face the other.
  `a` opens. On the next tick the engine asks for the script.
- **The plan.** What would have decided engagement turn by turn plans the scene instead. Each side
  gets a keenness from 0 to 1: `initial_engagement` (how much they like the other, and Connection),
  plus `keen_social` times their social need above or below 0.5, `keen_topics` times their topic
  interest, `keen_goal` times what they were doing's `accept_goals` score (`seeking_them` if they
  were looking for the other), less `keen_pressing` times their most pressing need (rest, curiosity
  or news) over `pressing`. Topic interest is how much the values of what both sides are likely to
  bring up matter to them, from -1 to 1: B4's articles behind their news topics, weighted by how
  much each relates to each value, or for someone with no news, their own top three values. Someone
  at `leave_below` or less wants to wrap up after `min_lines`, someone at 1 after `long_talk` (30),
  in a straight line between. Whoever wants to leave first does (the one approached, on a tie), and
  the scene runs that many lines plus the goodbye and its answer. The direction says each side's
  keenness in words ("keen to talk", "happy to chat", "lukewarm", "would rather not talk"), what
  draws them in (came looking for them, could do with company) and what holds them back (was off
  to read the news, has had plenty of company, tired): the reasons that agree with their keenness
  in brackets, the others after "though". Then who'll want to leave after about how many lines,
  and the length.
- **The script.** One L1 `stream()` call with Haiku 4.5 and `purpose="conversation"` writes the
  whole scene. Haiku 5.5 thinks before it writes and can't be told not to: on the same scenes it
  sometimes took over 20 s to its first line, where Haiku 4.5 took 2 to 7 s. The system prompt, the same for every scene, asks for it like a scene in a novel:
  each character knows only their own notes, what's between them and what's been said; they know
  what someone with their life and job would know, and otherwise ask, admit they don't know or give
  their own angle; it's a chat between neighbours, not a consultation; a topic the other doesn't
  take up is let go and nobody goes back over a point; pet words now and then. The prompt has, for
  each side, their persona, backstory, speaking style, values and interests, R1's `describe()` of
  how they feel about the other told in the third person, and, each marked as only theirs, any
  grudge they hold against the other, R2's `recall` (memories of the other, then recent or salient
  ones) and the secrets others told them (open `secret` flags about anyone else), and B4's
  `topics_to_raise`. Then what's between them, which both know: R2's `shared_history` events and
  their open debts, promises, broken promises and saved lives, and a secret told between them,
  marked as known only to the two. Then where and when they are, and the direction. Each line is
  the speaker's first name, a colon, the line and its `[values: ...]` tag.
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
  them, or when their rest, curiosity or news rises past `urgent_need` (0.95) during it. The line
  being said finishes, then they say a short goodbye (`GOODBYES`), unless they've just said one; if
  the other has, a "Bye" back. Nothing after that is said, and the rest of the script never happened.
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
might bring up is their own (B4's `topics_to_raise`), as with a resident. Nothing the player has read
reaches an NPC's prompt. B1 counts a talk with the player as `player_relief` (half) of one with a
resident towards their social need.

- **Starting.** `player_say` to an NPC within `say_range` (4 tiles) starts a conversation, unless
  they're asleep. One talking to another resident is pulled out of it (see *Interruptions*) and
  answers once that conversation has ended and their goodbye's audio has played. From then on, the player's lines reach the NPC for as long as the
  conversation lasts. Saying something to a different NPC who is awake ends the one going on: the
  old partner says a short canned goodbye, and the new resident's first line waits until it ends.
  Saying it to one who's asleep changes nothing. An NPC who walks up to the player (B1's seek) says
  hello. So does a free NPC within `near` (3 tiles) whose acceptance score beats `greet_bar` (0.5):
  every `look_every` (5 s), each nearby NPC is considered once per `greet_cooldown` (10 min), so
  high Connection NPCs greet strangers and those who dislike the player don't. Nobody greets a
  player who's already talking or not connected, and nobody in B1's `leave_player_alone` greets
  them.
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
- **Latency.** Replies use `PlayerConfig.model`, Haiku 4.5, because Haiku 5.5 can't turn thinking
  off (see [`llm/README.md`](../llm/README.md)). The nearest free NPC within `near` gets a warm
  Claude Code process for their reply (`llm.warm`), and so does the NPC after each reply.
- **What they know.** The resident's system prompt adds that they know what someone with their life
  and job would know, and otherwise ask, admit they don't know or give their own angle rather than
  expert advice; that it's a chat between neighbours, not a consultation; and that when the player
  changes the subject they go with it, or say once that they'd rather not and let it go.
- **Engagement.** The NPC starts from `start_engagement`, more if they like the player or value
  Connection. After every line they lose `fatigue` and gain `topic_weight` times how much the values
  it brings up for the first time in the conversation matter to them (from -1 to 1) plus
  `like_weight` times how much they like the player. Each player line and each reply counts as a
  line, and each player line touches the values the NPC's last reply did.
- **Ending.** From `min_lines` on, an NPC whose engagement is below `leave_below` answers with a
  goodbye. A player line within `farewell_wait` (8 s) of that goodbye joins the conversation and
  ends it. If the player says goodbye ("bye", "see you", "gotta go", ...), the
  NPC says goodbye back and it ends. It ends at once if the player walks beyond `leave_range` (6
  tiles) or disconnects. After `silence` (60 s) without a word from the player, the NPC says
  goodbye, or just leaves if the player never answered their hello. A reply that fails or says
  nothing ends it too. Cooldowns are as in B2.

Every constant is in `PlayerConfig`.

## Events

| Event | When |
|---|---|
| `ConversationStarted(conversation)` | It starts, with no lines. |
| `Facing(entity, toward, direction)` | Each participant turns to the other, `direction` being `down`, `left`, `right` or `up`. |
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
  now, so [`simile.ambient`](../ambient/README.md) only nudges pairs who would accept each other.

## Without Claude

`SIMILE_LLM=fake` makes L1 answer every call with a few stock lines, so a run never reaches Claude.
The test suite sets it for every test.

```bash
cd server && SIMILE_LLM=fake SIMILE_DB=:memory: uv run simile headless --speed 20 --duration 1
```
