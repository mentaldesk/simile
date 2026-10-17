# simile.news

The village's news: articles from the feeds in `FEEDS`, stored in the `news` table of the memory
store's file and analysed once each for how closely they relate to every core value, with tags and
a tone. NPCs read them at the terminals and bring them up later, and the player reads them there
too.

## Live news, on by default

- **Fetching.** `simile serve` and `simile headless` fetch every feed when they start, then every
  sim hour, but no sooner than 30 real minutes after the feed was last checked, even by an earlier
  run. Each fetch stores the 10 newest items per feed that aren't stored yet.
  `SIMILE_NEWS_FEED` swaps the feeds for a comma-separated list of URLs.
- **Analysis.** Every sim minute, the articles among the 60 newest that aren't analysed yet get one
  Haiku call each through L1, below conversations' priority. A first start analyses up to 10 items
  per feed, about 60 calls, and logs how many as it starts.
- **Turning it off.** `SIMILE_NEWS=0` leaves the news table alone: nothing is fetched, and no
  bundled articles are added. Articles already stored but not analysed, say from
  `simile news --refresh`, are still analysed. Every test runs this way, and so do `demo/run.sh`,
  `demo/check.py` and `simile ambient playthrough`.

## Bundled articles

When fetching is on and no news is stored at all, the server first stores the 13 real articles in
[`content/news/articles.json`](../../../content/news/articles.json), analysed already, so the
terminals have something to list before the first fetch is in, and when the feeds can't be
reached. After that they're articles like any other: one a feed carries too isn't stored twice,
they're never analysed again, and newer live articles push them down the terminals' list. The
demo starts from the same file.

## By hand

```bash
cd server
uv run simile news              # the latest stored, newest first
uv run simile news --refresh    # fetch the feeds first
uv run simile news --analyse    # analyse what's waiting, with Claude
```

Every constant of reading and analysing is in `NewsConfig`.
