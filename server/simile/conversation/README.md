# simile.conversation

NPCs talking to each other in real time. `conversations_of(app)` returns the server's
`ConversationEngine`, created on first use. Its lifespan plugs `request` and `live` into B1's
hooks and ticks the engine on the sim loop.

## A conversation

- **Asking.** B1 calls `request(a, b)` when `a` walks up to `b`. `b` accepts if `acceptance()`
  is positive (at `accept_temperature` 0; otherwise with chance `logistic(score / temperature)`).
  It adds up how `b` feels about `a` (R1's like, trust, respect and familiarity, read from R2 with
  `as_of`, or `meet` for strangers), `b`'s values (Connection, Compassion and Open Mindedness for,
  Independence and Peace of Mind against), their social need and what they're busy with: someone
  at a terminal or the maker space, or looking for someone else, is less keen, and someone who was
  looking for `a` is very keen. The player, anyone already talking and anything beyond
  `max_conversations` (2) are declined.
- **Starting.** Both are paused with B1, which stops their walks, and each turns to face the other.
  `a` speaks first.
- **Lines.** Each line is one L1 `stream()` call with Haiku and `purpose="conversation"`. The
  system prompt is the speaker's persona, backstory, speaking style, values and interests. The
  prompt is R1's `describe()` of how they feel about the other, R2's `shared_history` (events, and
  the other's open flags about them), R2's `recall` (memories of the other, then recent or salient
  ones), B4's `topics_to_raise` if `simile.news.reactions` exists, where and when they are, the
  latest lines and a cue: open, reply, goodbye or answer a goodbye. The model ends each line with
  `[values: ...]`, the core values the conversation touches. `parse_reply` takes it off, with any
  name label, quotes or `*stage directions*`.
- **Engagement.** Each participant starts from `start_engagement`, more if they like the other or
  value Connection. After every line, both lose `fatigue` and gain `topic_weight` times how much
  the line's values matter to them (from -1 to 1) plus `like_weight` times how much they like the
  other. From `min_lines` on, whoever's turn it is says goodbye when theirs is below
  `leave_below`, and the other answers. Pairs who dislike each other start lower and drop faster,
  so their conversations are short. Nobody talks past `max_lines`.
- **Pacing.** A line takes `words / 150 wpm` sim seconds (at least `min_line_seconds`), then
  `turn_gap` before the next, whether or not anyone is listening. The next line is written while
  the current one plays, so lines follow each other without gaps unless the LLM is slower than the
  line. `Line.timestamp` is when it starts.
- **Ending.** After the last line plays, or a line fails to come back, the conversation ends. Both
  NPCs resume deciding, and neither seeks the other for `cooldown` minutes.

Every constant is in `ConversationConfig`.

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
- **Player conversations (B5).** `system_prompt`, `background`, `turn_prompt`, `parse_reply`,
  `engage`, `leaving` and `duration` work for any speaker. Take line ids from `line_ids(app)`, so
  they're unique across the world.
- **Voicing (I1).** `LineDrafted` gives each NPC line's text one line ahead of `LineSpoken`.
- **Debug overlay (I2).** `engine.state(npc)` has their conversation, who they're talking to,
  engagement, facing and whether they're about to leave.

## Without Claude

`SIMILE_LLM=fake` makes L1 answer every call with a few stock lines, so a run never reaches Claude.
The test suite sets it for every test.

```bash
cd server && SIMILE_LLM=fake SIMILE_DB=:memory: uv run simile headless --speed 20 --duration 1
```
