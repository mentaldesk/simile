# simile.news

The village's news: articles from the feeds chosen in the title menu, stored in the `news` table of
the memory store's file and analysed once each for how closely they relate to every core value,
with tags, a tone and, from the article itself, a summary of three or four paragraphs. NPCs read
them at the terminals and bring them up later, and the player reads them there too.

## Live news, on by default

- **Fetching.** `simile serve` and `simile headless` fetch every feed when they start, then every
  sim hour, but no sooner than 30 real minutes after the feed was last checked, even by an earlier
  run. Each fetch stores the 10 newest items per feed that aren't stored yet. Each feed refreshes
  on its own, so a slow or failing one holds up no other.
- **Analysis.** Every sim minute, the articles among the 60 newest that aren't analysed yet get one
  Haiku call each through L1, below conversations' priority, which also writes the long summary.
  A first start analyses up to 10 items per feed, about 60 calls, and logs how many as it starts.
- **Turning it off.** `SIMILE_NEWS=0` leaves the news table alone: nothing is fetched, article
  pages included, and no bundled articles are added. Articles already stored but not analysed, say
  from `simile news --refresh`, are still analysed, and summarised only from text their feed
  carried. Every test runs this way, and so does `simile ambient playthrough`.

## Long summaries

The analysis call reads up to 4,000 words of the article and writes three or four short paragraphs
in its own words: what happened, who's involved and why it matters. The terminal shows them when
the player opens the article, and residents react to them.

- **The article's text** is the feed's own (`content:encoded`, or Atom's `content`) when it carries
  150 words or more. Otherwise the page is read once, through the same fetch as the feeds, so the
  limits below hold for it too, and trafilatura finds the article on it. A feed on the internet
  can't send it to a private address.
- **Never from the headline.** With fewer than 150 words (a teaser, a live blog's stub, a hard
  paywall's first paragraph), an error status, a refusal or a timeout, the article keeps its feed's
  summary. Why is kept in `news_no_text`, logged, and listed by `simile news`, and that page isn't
  read again.
- **Paid content isn't summarised.** A page whose structured data says it isn't free to read
  (`isAccessibleForFree: false`) keeps the feed's summary too, even when it serves the whole
  article, as Scientific American's do. Text a feed carries itself is the publisher's to share, so
  it's summarised.
- **Nothing is kept.** The page is dropped once its text is found, and the text, in `news_text`,
  once the summary is written or the article won't be analysed. Read text is kept until then so a
  failed call doesn't read the page again.
- **Residents** react to the long summary, and their memory of it keeps up to three points that
  stuck with them (`Memory.points`). A conversation's prompt gives one article's points at most:
  in a reply to the player, the article the player just mentioned or else the resident's first
  news topic, and in a scene, the first topic with points, the opener's before the other's.

## Choosing the feeds

The title menu's *News feeds* lists the feeds with a switch for each, adds one from a pasted URL,
removes one, and resets to the defaults. The list is saved once per install, not per world, in
`server/data/feeds.json` (`$SIMILE_FEEDS_FILE` moves it). Until it's changed, the six in `FEEDS`
are the defaults, and *Reset to defaults* deletes the file. `SIMILE_NEWS_FEED` overrides the list
for a run with a comma-separated list of URLs, and the menu says so.

- **Changes apply at the next refresh**, without a restart: the refresher asks the list every tick.
  A feed added or switched on is fetched at once, unless it was checked less than 30 minutes ago. A
  removed feed's stored articles stay, since residents remember what they read.
- **Usage.** Each feed that's on adds up to 10 Haiku calls when its new stories are analysed, so the
  list takes at most 12 (`NewsConfig.max_feeds`).
- **Routes.** `GET /api/news/feeds` lists them with when each was last checked. `POST` to
  `/api/news/feeds/check` fetches a URL once and answers with its title and latest headline, without
  adding it. `POST /api/news/feeds` fetches it again and adds it under its title. `/switch`
  (`{"url", "on"}`), `/remove` (`{"url"}`) and `/reset` (`{}`) change the list. Each answers with the
  list, or a status and an `error` in words for the player. They take only JSON, so another site's
  form can't post to them.

A pasted URL is untrusted, so every fetch, not only the first:

- goes over http or https only
- gives up 30 seconds after it starts, whatever it's waiting for: connecting, a redirect, the
  headers, chunked framing or the body. A timer shuts its sockets then. It also gives up after 10
  seconds of silence, and past 4 MB. The refresher and the routes stop waiting 5 seconds later
  still, should the thread be stuck resolving the host's name.
- follows at most 5 redirects, only over http(s), and never from the internet to a private
  address. A feed on your own network may redirect within it.
- refuses anything feedparser doesn't read as RSS or Atom, with the reason
- refuses a feed whose bytes declare an XML entity. That catches UTF-8 and other ASCII-compatible
  encodings, but not UTF-16 or UTF-32, where feedparser leaves entities unexpanded instead.

## Bundled articles

When fetching is on and no news is stored at all, the server first stores the 13 real articles in
[`content/news/articles.json`](../../../content/news/articles.json), analysed already, so the
terminals have something to list before the first fetch is in, and when the feeds can't be
reached. After that they're articles like any other: one a feed carries too isn't stored twice,
they're never analysed again, and newer live articles push them down the terminals' list.

## By hand

```bash
cd server
uv run simile news              # the latest stored, newest first
uv run simile news --refresh    # fetch the feeds first
uv run simile news --analyse    # analyse what's waiting, with Claude
uv run simile news --summarise 30   # long summaries for those of the 30 newest without one
```

`--summarise` reads each page once, as analysis does, and keeps how an article was analysed. The
listing says which articles have a long summary, or why not, and counts them by feed.

Every constant of reading and analysing is in `NewsConfig`.
