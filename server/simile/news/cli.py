from collections import Counter
from typing import TYPE_CHECKING, Annotated

import typer

if TYPE_CHECKING:
    from simile.llm import LLMClient
    from simile.news.analysis import Summaries
    from simile.news.store import NewsStore
    from simile.schema import NewsItem


def register(app: typer.Typer) -> None:
    @app.command()
    def news(
        refresh: Annotated[bool, typer.Option(help="Fetch the live feeds first.")] = False,
        analyse: Annotated[
            bool,
            typer.Option(help="Analyse the newest articles that aren't yet, with Claude."),
        ] = False,
        summarise: Annotated[
            int,
            typer.Option(
                min=0,
                metavar="N",
                help="Write long summaries, with Claude, for those of the N newest articles "
                "without one, reading each one's page once.",
            ),
        ] = 0,
        count: Annotated[
            int, typer.Option("--count", "-n", min=1, help="How many items to list.")
        ] = 10,
    ) -> None:
        """List the latest stored news, newest first.

        `simile serve` and `simile headless` keep it fresh and analyse new articles as they come,
        unless SIMILE_NEWS=0.

        It reads the feeds switched on in the title menu's News feeds, saved in
        server/data/feeds.json (or $SIMILE_FEEDS_FILE). SIMILE_NEWS_FEED overrides them with a
        comma-separated list of URLs.
        """
        import asyncio

        from simile.memory import default_path
        from simile.news.feed_list import feeds
        from simile.news.refresh import refresh_all
        from simile.news.store import NewsStore

        failed = False
        with NewsStore(default_path()) as store:
            if refresh:
                chosen = feeds()
                results = asyncio.run(refresh_all(store, chosen))
                for feed, result in zip(chosen, results, strict=True):
                    label = f"{feed.name} ({feed.url})" if feed.name else feed.url
                    if isinstance(result, BaseException):
                        typer.echo(f"Couldn't fetch {label}: {result}", err=True)
                        failed = True
                    else:
                        typer.echo(
                            f"{len(result.added)} new items from {label}, "
                            f"{len(result.skipped)} skipped as too short to react to"
                        )
                typer.echo()
            if analyse:
                waiting, analysed = asyncio.run(analyse_waiting(store))
                summarised = sum(bool(item.long_summary) for item in analysed)
                typer.echo(
                    f"Analysed {len(analysed)} of {waiting} articles waiting, "
                    f"{summarised} with a long summary.\n"
                )
                failed = failed or len(analysed) < waiting
            if summarise:
                summaries = asyncio.run(summarise_newest(store, summarise))
                typer.echo(f"Long summaries written: {len(summaries.written)}.")
                for item, reason in summaries.kept:
                    typer.echo(f"Kept the feed's summary of {item.title!r}: {reason}")
                if summaries.error:
                    typer.echo(f"Stopped, as a call failed: {summaries.error}", err=True)
                    failed = True
                typer.echo()
            items = store.latest(count)
            reasons = {item.id: store.why_no_text(item.id) for item in items}
        if not items:
            typer.echo("No news stored yet. Fetch it with `simile news --refresh`.")
        for item in items:
            source = f" ({item.source})" if item.source else ""
            typer.echo(f"{item.published:%Y-%m-%d %H:%M}  {item.title}{source}\n{'':18}{item.url}")
            if item.analysed:
                typer.echo(f"{'':18}{describe(item)}")
                typer.echo(f"{'':18}{summary_of(item, reasons[item.id])}")
        if any(item.analysed for item in items):
            typer.echo(f"\n{tally(items)}")
        if failed:
            raise typer.Exit(1)


def client() -> "LLMClient":
    import os

    from simile.llm import LLMClient
    from simile.llm.lifespan import FAKE_ENV, CannedProvider

    return LLMClient(CannedProvider() if os.environ.get(FAKE_ENV) == "fake" else None)


async def analyse_waiting(store: "NewsStore") -> tuple[int, list["NewsItem"]]:
    from simile.news import article
    from simile.news.analysis import NewsAnalyser
    from simile.news.config import DEFAULT_CONFIG

    llm = client()
    try:
        waiting = len(store.unanalysed(DEFAULT_CONFIG.candidates, llm.provider.name))
        analyser = NewsAnalyser(store, lambda: llm, page=article.page)
        return waiting, await analyser.analyse_pending()
    finally:
        await llm.aclose()


async def summarise_newest(store: "NewsStore", n: int) -> "Summaries":
    from simile.news import article
    from simile.news.analysis import summarise

    llm = client()
    try:
        return await summarise(store, llm, n, page=article.page)
    finally:
        await llm.aclose()


def describe(item: "NewsItem") -> str:
    top = sorted(item.values.items(), key=lambda pair: pair[1], reverse=True)[:3]
    values = ", ".join(f"{value.value} {score:.1f}" for value, score in top)
    return f"{values}; tone {item.sentiment or 0:+.1f}; {', '.join(item.tags)}"


def summary_of(item: "NewsItem", reason: str | None) -> str:
    if item.long_summary:
        return f"Long summary, {len(item.long_summary.split())} words"
    return f"Feed's summary only. {reason}" if reason else "Feed's summary only"


def tally(items: list["NewsItem"]) -> str:
    analysed = Counter(item.source or "?" for item in items if item.analysed)
    summarised = Counter(item.source or "?" for item in items if item.long_summary)
    counts = ", ".join(f"{source} {summarised[source]} of {n}" for source, n in analysed.items())
    return f"Long summaries of the analysed articles listed: {counts}"
