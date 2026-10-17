# simile.works

What the residents make from what's on their mind: for now, writing in their `craft`. Works are
stored in the `works` table of the memory store's file, and go up on the news terminals for the
residents and the player to read.

## Making a work

`Maker.make(npc)` starts a resident writing and returns at once, so a tick can call it. The task it
returns stores the `Work`, gives the artist a `work` memory of making it (with `work_id`), and
returns the work, or None if the call failed. It does nothing for residents without a writing
craft, or with a piece already under way. `simile serve` and `simile headless` keep one on
`app.state.maker`, and B1's `create` hook calls it when a writer finishes a stay making something.

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

## Reading at the terminals

The lifespan wraps B1's `news_interest` and `read_news` hooks around the news's (`news` starts
first), so a terminal offers the best unread article or piece of writing:

- **Interest.** A piece's interest is the news's for an article (`news/interest.py`: how it bears
  on the reader's values, their interests and its tone), plus `artist_weight` (0.5) times B1's
  affinity for the artist from R1. A friend's piece pulls harder than a stranger's, and a rival's
  less. Pieces below 0.5 aren't read. `news_interest` is the better of the best article and the
  best piece, up to 1.
- **Reading.** At a terminal, a resident reads the unread piece that interests them most if no
  article interests them more, and then the news's pick as well, so a piece never costs them an
  article. One Haiku call through L1, below conversations' priority, asks how it lands, with their
  values, the piece, the artist's statement and how they feel about the artist. The reply becomes a
  `work` memory with `work_id`, `about` the artist and the piece's first 3 tags as topics. Nobody
  reads their own work, or a piece twice.

## The player

`list_works` and `read_work` are answered with `works`: the 20 newest pieces of writing, with the
artist's name and whether the player has read each. Reading one stores the player's own `work`
memory, once, with no LLM call. As with the news, residents never see it.

Every constant is in `WorksConfig`.

## By hand

```bash
cd server
uv run simile works make tobias   # what's on his mind, then the piece, stored in $SIMILE_DB
```
