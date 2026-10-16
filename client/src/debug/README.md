# Debug overlay

A view into an NPC's head, for tuning the simulation. Press <kbd>`</kbd> (the key left of 1) to open
it, then click an NPC: a panel on the right shows their goal and needs, top values, last decision,
relationships, the memories they'd recall now and their current conversation, updated twice a
second by the server (`server/simile/debug/`). A yellow box marks who you're watching. Click
another NPC to switch, and <kbd>`</kbd> again to close it.

- The toggle listens for key-downs, which the chat box stops while the player types.
- It sends `watch_npc` with the NPC while open and `null` when closed, and again after every
  `snapshot`, so a reconnected or restarted server picks the watch back up.
- Clicks hit-test with `npcAt` from [`world/hit.ts`](../world/hit.ts), as the dialogue UI's do.
  While the overlay is open it claims clicks, so they don't also choose who to talk to.
- The panel is HTML (`panel.ts`), escaped by the `html` template in `html.ts`, since memories and
  lines are LLM text.
