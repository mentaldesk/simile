# simile.works

What the residents make from what's on their mind, in their `craft`: writing, which goes up on the
news terminals, murals, painted on M7's walls, and paintings for the gallery. Works are stored in the
`works` table of the memory store's file, and a mural's picture beside it in `murals`.

## Making a work

`Maker.make(npc, wall=None, intention=None)` starts a resident writing, painting a mural on `wall`, or painting for
the gallery, and returns at once, so a tick can call it. The task it returns stores the `Work`, gives the artist a `work`
memory of making it (with `work_id`), and returns the work, or None if it failed. It does nothing
for residents without a craft, muralists without a known wall, or anyone with a work already under
way. `simile serve` and `simile headless` keep one on `app.state.maker`, and B1's `create` hook
calls it when a resident finishes a stay making something.

One Sonnet call through L1, below conversations' priority, makes the work and analyses it. The
prompt has:

- their 8 strongest memories by salience × recency (news, conversations, others' works), with how
  each made them feel, but not their memories of making their own works;
- their values, persona, backstory, interests, way of talking and craft;
- the titles and statements of their last 3 works, so they don't repeat themselves.

It asks for a work in their voice that says something in line with their values, taking a side
where they care strongly.

B1's `create` hook hands over the intention a stay kept, if it kept one (see *Intentions* in B1's
README), and `make(npc, wall, intention)` leads the prompt with its idea: "You told Visitor you'd
make this, and you're making it now: a mural of an ocean of coffee with cups half-sunk in it". It
asks them to make that idea, in their own way, drawing on what's on their mind, and the
conversation it came from is the first of the work's `inspired_by`. The reply has the title, the work and its statement, which of the
memories it came from (stored as `inspired_by`: their news, conversation or work ids), and its tags,
tone and relatedness to every core value, scored as for news.

## Murals

- **Choosing a wall.** B1's `mural_wall` hook is `Walls.pick`. A wall they've said they'll paint
  (an open `create` intention naming it, see B1's README) comes first, while it's blank or ready
  enough as below, so they go where they told the player. Then a blank wall, the nearest
  of them to a muralist on the village, or the first for one indoors. Otherwise each painted wall
  gets a readiness to paint over it: its age up to `mural_age` (2 days), plus `own_mural` (0.3) for
  the painter's own, or for someone else's their boldness above 0.5 (the mean of 1 - Tradition, 1 -
  Obedience and Freedom) minus half their B1 affinity for the artist. The readiest wall at or above
  0.5 is picked, and None while there's none. A painter less bold than 0.75 never paints over a
  friend's (affinity 0.4 or more), and nobody picks a wall someone else is off to paint.
- **Painting.** The prompt also has the wall's size and what's on it now, and asks for an SVG with
  the wall's `viewBox`, beside a plain description of what it shows (the work's `text`).
- **Checking the SVG** (`svg.checked`). It must be under 60,000 characters and 2,000 elements,
  roughly the wall's shape, and only shapes, text, gradients, patterns, masks and filters: no
  scripts, images, foreign objects, event handlers, CSS escapes, or references to anything outside
  it. So that resvg can't be kept busy or overflow its stack, elements may nest 32 deep, there may
  be 200 `<use>`s, none reaching another, and references to references may go 4 deep; ids must be
  unique, and `numOctaves` and morphology radii are capped. A bad one is asked for again once, with
  the reason, and then given up quietly.
- **Drawing it** (`render.draw`). resvg draws it in a child process, at the wall's size in the iso
  scenery (96 px per tile, at the same scale up the wall), onto lightly weathered plaster. A child
  that crashes, panics or takes more than `render_timeout` (5 s) is killed, and its SVG counts as
  bad. Anything else that goes wrong while making a work is logged, and nothing is made.
- **Replacing.** The new mural covers the old one, which stays in the store with its picture, and
  `covered(id)` says what each mural covered. The artist remembers painting it, and over whose.
- **Telling the client.** Each new client gets `murals`, with every wall, painted or not, and
  everyone gets it again when one is painted. `GET /api/works/<id>.png` serves a mural's picture,
  and 404s for anything else.
- **Being seen.** A resident who comes within 3 tiles in front of a mural they haven't seen, on the
  village rather than inside a building, says how it lands in one Haiku call, as at the terminals.
  The memory is about the artist, with `work_id`. If the call fails, they try again on their first
  look after `look_again` (a sim hour). An artist who finds their mural painted over is told so in
  the same call, and remembers it with a salience of at least 0.7. The player remembers seeing it,
  with no call.

## Paintings

A painter, or a muralist given anything but a wall, paints a canvas for the gallery, once the
gallery has given the maker its `hang` (`gallery/README.md`). Without one, nobody does.

- **Painting.** The prompt asks for something new in their craft, or for a muralist in its spirit
  on canvas, as an SVG at the frame's opening: 1.34 × 0.84 m (`PAINTING_M`, from the iso frames),
  960 × 602 px. It's checked as a mural's is, asked for once more if it won't do, and drawn in the
  same child process under the same limits, onto a primed canvas with no weathering.
- **Hanging.** The `Work` (`medium` painting, the artist's `form`, no `wall`) is stored, `hang` gets
  it with its SVG and PNG, and the artist remembers painting it for the gallery.

## Starter works

So that the village never starts bare, works are there from the first frame. Its `running` hook
does this once per save, and never into an in-memory store:

- **Today's village** ships with 15 works in `content/works/`: a mural on four of the five walls
  (Kofi's on the tower and the corner shop, Ingrid's on the garden flats, Odalys's on the Daily
  Grind), a piece from each of the six writers for the terminals, and five paintings for the
  gallery (Priya's and Tobias's, two each, and a canvas of Ingrid's). `works.json` has the `Work`s,
  oldest first, beside each mural's and painting's SVG and PNG. A save with no works that has never
  had them gets them all, as if made before it starts, the newest `starters_newest` (3 sim hours)
  earlier and the rest with their spacing before it. The murals go on their walls, the paintings
  hang in the gallery's first frames, and each artist remembers making theirs. The `seeded` table
  records that it's been done, so it's never done twice, even once the starters are painted over.
- **A new world** (a cast in the data directory, `worlds/README.md`) makes its own in the
  background instead, once its save first runs: up to `starters` (8) of its residents with a
  craft, the most creative first, start one work each through the usual `Maker`, muralists on the
  walls in turn and then for the gallery. Each appears when it's finished, as any other does.

The starters were made once by a command, with the usual Maker prompts, in the order of `PLAN` in
`starters.py`, so an artist's second work sees their first. Their residents had nothing on their
mind yet, so they come from their values, persona and craft:

```bash
cd server
uv run simile works starter   # about 15 Sonnet calls, into content/works/
```

It makes only the works `content/works/` doesn't have yet, saving each as it's made, and stops at the
first that fails, so running it again carries on. `--out` puts them elsewhere, and with
`SIMILE_LLM=fake` it makes stand-ins through the same checks and renderer.

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
uv run simile works make kofi --png kofi.png   # a mural on the wall he'd pick, if any
uv run simile works make kofi --wall tower     # or on the one named
```
