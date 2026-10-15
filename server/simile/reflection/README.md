# simile.reflection

What a finished conversation meant to each NPC in it. The lifespan subscribes a `Reflector` to
`ConversationEnded` and keeps it on `app.state.reflection`.

## A reflection

- **When.** The bus handler only starts an asyncio task, so the tick never waits. Conversations
  with no lines, or with no NPC in them, are skipped. Tasks still running at shutdown are
  cancelled and their conversations are lost; to process one at shutdown, await
  `reflector.reflect(llm, conversation)` directly.
- **The call.** One L1 `structured()` call per conversation, with Haiku, `purpose="reflection"`
  and priority -1, so it queues behind dialogue. The prompt has each NPC's persona, strongest and
  weakest values, interests, how they felt about the others going in (R1's `as_of`, or `meet` for
  strangers), their open flags about them as refs (`F1`, `F2`, ...), and the transcript.
- **The reply.** An `Extraction` with a `Reflection` per NPC: a first-person summary with valence
  and salience, topics, `events` (what the others did to them, with the aspects it moves, valence
  and magnitude), `flags_opened` and `flags_resolved` (by ref). People can be named by id,
  transcript name or full name; anything naming someone outside the conversation is dropped.
- **Applying it.** After the reply, each NPC's relationships are read again from R2 (another
  reflection may have changed them meanwhile) and decayed with `as_of` to when the conversation
  ended. Each NPC's first `events` valid events then go through `apply_event`. If their events
  about one person add up to more than `max_magnitude` (1), they're scaled down to it, so a
  conversation moves a pair at most as far as one full-strength event however many events the
  model lists. The events apply at the familiarity the pair had going in, and familiarity grows
  once per conversation, events or not. New flags go on their owner's relationship with
  `open_flag`, at most `flags` per NPC. An NPC resolves only their own flags, with
  `resolve_flag`, and not ones resolved meanwhile. Each summary becomes a `conversation` memory
  about the others. Everything is stored with one R2 `add`.
- **Failures.** A reply that doesn't match the schema after L1's retry (always, under
  `SIMILE_LLM=fake`) logs one warning and changes nothing. So does an `LLMError`.

Every relationship change is logged at INFO, e.g.
`henrietta about kofi: like 0.28->0.00, ..., +promise (painting over the squid by Saturday)`.

## The player

The player (`player`) has no `Npc`, so they never reflect: no memories, relationships or flags
are owned by the player. NPCs remember the player and form relationships about them like anyone
else, and what the player does counts as events. In the prompt the player is called
`player_name` ("Visitor").

Every constant is in `ReflectionConfig`.
