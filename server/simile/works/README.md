# simile.works

What the residents make from what's on their mind: for now, writing in their `craft`. Works are
stored in the `works` table of the memory store's file.

## Making a work

`Maker.make(npc)` starts a resident writing and returns at once, so a tick can call it. The task it
returns stores the `Work`, gives the artist a `work` memory of making it (with `work_id`), and
returns the work, or None if the call failed. It does nothing for residents without a writing
craft, or with a piece already under way. `simile serve` and `simile headless` keep one on
`app.state.maker`; nothing calls it yet.

One Sonnet call through L1, below conversations' priority, writes the piece and analyses it. The
prompt has:

- their 8 strongest memories by salience × recency (news, conversations, others' works), with how
  each made them feel, but not their memories of making their own works;
- their values, persona, backstory, interests, way of talking and craft;
- the titles and statements of their last 3 works, so they don't repeat themselves.

It asks for a short piece in their voice that says something in line with their values, taking a
side where they care strongly. The reply has the title, text and statement, which of the memories
it came from (stored as `inspired_by`: their news, conversation or work ids), and its tags, tone and
relatedness to every core value, scored as for news.

Every constant is in `WorksConfig`.

## By hand

```bash
cd server
uv run simile works make tobias   # what's on his mind, then the piece, stored in $SIMILE_DB
```
