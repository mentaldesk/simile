# simile.reflection

What a finished conversation meant to each NPC in it. The lifespan subscribes a `Reflector` to
`ConversationEnded` and keeps it on `app.state.reflection`.

## A reflection

- **When.** The bus handler only starts an asyncio task, so the tick never waits. Conversations
  with no lines, or with no NPC in them, are skipped. Tasks still running at shutdown are
  cancelled and their conversations are lost; to process one at shutdown, await
  `reflector.reflect(llm, conversation)` directly.
- **The call.** One L1 `structured()` call per conversation, with Haiku 5.5, `purpose="reflection"`
  and priority -1, so it queues behind dialogue. The prompt has each NPC's persona, strongest and
  weakest values, interests, how they felt about the others going in (R1's `as_of`, or `meet` for
  strangers), the open flags between them as refs (`F1`, `F2`, ...), and the transcript.
- **The reply.** An `Extraction` with a `Reflection` per NPC: a first-person summary with valence
  and salience, topics, and `events` (what the others did to them, with the aspects it moves,
  valence and magnitude). Then, for the conversation as a whole, `flags_opened` (see *Flags*
  below) and `flags_resolved` (by ref). People can be named by id, transcript name or full name;
  anything naming someone outside the conversation is dropped.
- **Applying it.** After the reply, each NPC's relationships are read again from R2 (another
  reflection may have changed them meanwhile) and decayed with `as_of` to when the conversation
  ended. Each NPC's first `events` valid events then go through `apply_events`, one call per
  person they're about. If those events add up to more than `max_magnitude` (1), they're scaled
  down to it, so a conversation moves a pair at most as far as one full-strength event however
  many events the model lists. R1 adds them up per aspect and moves each score once, so R1's
  curve holds per conversation, not per event, and familiarity grows once per conversation,
  events or not. Then flags, settled before any open: the refs in `flags_resolved` close those
  flags with `resolve_flag`, whoever owns them, but not ones resolved meanwhile. After that, new
  flags go on their owner's relationship with `open_flag`, at most `flags` per owner. Each
  summary becomes a `conversation` memory about the others. Everything is stored with one R2
  `add`.
- **Broken promises.** The prompt asks for a broken promise to be resolved by its ref and opened
  again as a `broken_promise`, and Haiku does both. If a reply only opens the `broken_promise`,
  and its owner holds just one open `promise` about whoever broke it, that promise is closed
  too. With more than one, B3 can't tell which was broken and leaves them open. A broken promise
  always costs trust: if the owner's own events about whoever broke it don't already lower
  trust, B3 adds one that does (`broken_promise_valence` and `broken_promise_magnitude`) to
  those events before `apply_events`, so it counts towards `max_magnitude` like the rest.
- **Failures.** A reply that doesn't match the schema after L1's retry (always, under
  `SIMILE_LLM=fake`) logs one warning and changes nothing. So does an `LLMError`.

Every relationship change is logged at INFO, e.g.
`henrietta about kofi: like 0.28->0.00, ..., +promise (painting over the squid by Saturday)`.

## Flags: who did what to whom

F2's flag kinds read from the owner's side, which is easy to get backwards: a `promise` flag
that tobias holds about lachlan means lachlan promised tobias something. So the reply never names
an owner. Each new flag says who did what to whom, and `owner_and_about` works out who holds it:

| Kind | The reply says | Owner | About |
|---|---|---|---|
| `debt` | `who` owes `whom` | `whom` | `who` |
| `grudge` | `who` holds a grudge against `whom` | `who` | `whom` |
| `promise` | `who` promised `whom` | `whom` | `who` |
| `broken_promise` | `who` broke a promise to `whom` | `whom` | `who` |
| `saved_life` | `who` saved the life of `whom` | `whom` | `who` |
| `secret` | `who` told `whom` a secret | `whom` | `who` |

The owner is whoever is owed, promised, let down, saved or told, or whoever holds the grudge. The
prompt lists open flags the same way, e.g. `F1 (promise): lachlan promised tobias: reporting back
on Saturday's match`.

## The player

The player (`player`) has no `Npc`, so they never reflect: no memories, relationships or flags
are owned by the player. NPCs remember the player and form relationships about them like anyone
else, and what the player does counts as events. In the prompt the player is called
`player_name` ("Visitor").

A flag the player would own is dropped. So when an NPC promises the player something, owes them,
breaks a promise to them, saves their life or tells them a secret, no flag is kept, only the NPC's
memory of the conversation. When the player does any of those to an NPC, or an NPC holds a grudge
against the player, the flag goes on the NPC's relationship about the player.

Every constant is in `ReflectionConfig`.
