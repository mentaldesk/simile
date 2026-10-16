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
  `a` speaks first.
- **Lines.** Each line is one L1 `stream()` call with Haiku 5.5 and `purpose="conversation"`. The
  system prompt is the speaker's persona, backstory, speaking style, values and interests. The
  prompt is R1's `describe()` of how they feel about the other, R2's `shared_history` (events, and
  the other's open flags about them), R2's `recall` (memories of the other, then recent or salient
  ones), B4's `topics_to_raise`, where and when they are, the latest lines, how the speaker's last
  few lines began (so they begin this one another way rather than with the same pet word) and a
  cue: open, reply (keep it going, no goodbyes yet), goodbye or answer a goodbye. The system prompt
  asks for pet words and phrases now and then, not in every line. The model ends each line with
  `[values: ...]`, the core values the conversation touches. `parse_reply` takes it off, even cut
  short, along with any name label, quotes, `*stage directions*` and anything the model wrote for
  the other speaker. It also cuts a line at the first sentence boundary past `max_words` (40), so
  no sentence starts after the 40th word.
- **Engagement.** Each participant starts from `start_engagement`, more if they like the other or
  value Connection. After every line, both lose `fatigue` and gain `topic_weight` times how much
  the values it brings up for the first time in the conversation matter to them (from -1 to 1)
  plus `like_weight` times how much they like the other. A conversation that keeps circling the
  same values runs out of steam; one that moves on to things they care about keeps going. From
  `min_lines` on, whoever's turn it is says goodbye when theirs is below `leave_below`, and the
  other answers. Pairs who dislike each other start lower and drop faster, so their conversations
  are short; strangers usually part within 5 to 20 lines and friends on good form can go on for 30
  or more. `max_lines` (60) is only a backstop.
- **Goodbyes.** From `min_lines` on, a reply whose last sentence says goodbye anyway ("I'll leave
  you to it", "see you at the riverside", "catch you later") counts as one: the other answers it
  and the conversation ends. A goodbye mentioned in passing, or asked as a question ("Will I see you
  at the quiz?"), doesn't count.
- **Pacing.** A line takes `words / 200 wpm` sim seconds (at least `min_line_seconds`), about as
  long as V1 takes to say it, then `turn_gap` before the next, whether or not anyone is listening. The next line is written while
  the current one plays, so lines follow each other without gaps unless the LLM is slower than the
  line. `Line.timestamp` is when it starts.
- **Ending.** After the last line plays, the conversation ends. So does one whose next line fails
  or takes longer than `line_timeout` real seconds (30) to write, once the current line has
  played. Both NPCs resume deciding, and neither seeks the other for `cooldown` minutes.

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
  they're talking to another NPC or asleep. From then on, the player's lines reach the NPC for as
  long as the conversation lasts. Saying something to a different NPC who is free ends the one going
  on: the old partner says a short canned goodbye, and the new resident's first line waits until it
  ends. Saying it to one who isn't free changes nothing. An NPC who walks up to the player (B1's
  seek) says hello. So does a free NPC within `near` (3 tiles) whose acceptance score beats
  `greet_bar` (0.5): every `look_every` (5 s), each nearby NPC is considered once per
  `greet_cooldown` (10 min), so high Connection NPCs greet strangers and those who dislike the
  player don't. Nobody greets a player who's already talking or not connected, and nobody in B1's
  `leave_player_alone` greets them.
- **Replies.** Each player line is answered straight away, with no line ahead: one L1 `stream()`
  with `priority=1` and `purpose="player-reply"`. Each sentence becomes its own `Line` as soon as it
  has streamed, with `LineDrafted` at once and `LineSpoken` when the previous sentence has been
  said. The player's lines are spoken when they arrive and have no `LineDrafted`. If the player
  says something while the NPC is still writing or speaking, the NPC stops: the rest of that reply
  is dropped and they answer the new line.
- **News the player mentions.** B4's `mentioned` matches the player's lines since the NPC last
  spoke against each article the NPC read: its title, tags and summary from the news store (looked
  up through `news_of` when needed, or just the title quoted in the memory if it's gone) and the
  topics the NPC took from it. An article counts if they share `NewsConfig.mention_words` (2)
  words, where a word matches its other forms ("colonise", "Colonising"), or if the player names
  the news ("news", "article", "piece", "story", "headline", "read", "paper") and one word is in its
  title, tags or topics exactly, give or take a plural ("Did you see the Mars piece?"). The NPC's
  memory of each article that counts, with their take, follows the transcript in that reply's
  prompt, for at most `mentions` (2) articles, most shared words first. An NPC who didn't read it
  gets nothing and answers from their values.
- **Latency.** Replies use `PlayerConfig.model`, Haiku 4.5, because Haiku 5.5 can't turn thinking
  off (see [`llm/README.md`](../llm/README.md)). The nearest free NPC within `near` gets a warm
  Claude Code process for their reply (`llm.warm`), and so does the NPC after each reply.
- **Ending.** Engagement works as in B2, with each player line and each reply counting as a line,
  and each player line touching the values the NPC's last reply did. When the NPC's engagement is
  low, they answer with a goodbye; a player line within `farewell_wait` (8 s) of that goodbye joins
  the conversation and ends it. If the player says goodbye ("bye", "see you", "gotta go", ...), the
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

- **Transcripts (B3).** Subscribe to `ConversationEnded`. `engine.conversation(id)` returns a live
  or recently finished conversation, and `engine.finished` keeps the last `keep_finished` (50).
- **Player conversations (B5).** Conversations with the player have `player` as a participant
  and publish the same events, with the player's lines included.
- **Voicing (I1).** `LineDrafted` gives each NPC line's text one line ahead of `LineSpoken`. In a
  conversation with the player, each line is a sentence and `LineDrafted` comes as soon as it has
  streamed, so voicing can start on the first sentence. A sentence dropped because the player talked
  over the NPC or left gets a `LineDrafted` but no `LineSpoken`.
- **Debug overlay (I2).** `engine.state(npc)` has their conversation, who they're talking to,
  engagement, facing and whether they're about to leave.
- **Ending one now (I3).** `engine.end(conversation_id)` ends a live conversation as if it had run
  its course, dropping any line still being written, and returns it with `ended` set, or None if
  it isn't live. `ConversationEnded` follows as usual, so B3 reflects on it.
- **The ambient director.** `engine.accept_score(a, b)` says how keen `b` would be if `a` walked up
  now, so [`simile.ambient`](../ambient/README.md) only nudges pairs who would accept each other.

## Without Claude

`SIMILE_LLM=fake` makes L1 answer every call with a few stock lines, so a run never reaches Claude.
The test suite sets it for every test.

```bash
cd server && SIMILE_LLM=fake SIMILE_DB=:memory: uv run simile headless --speed 20 --duration 1
```
