from typing import TYPE_CHECKING, Annotated

import typer

if TYPE_CHECKING:
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
        count: Annotated[
            int, typer.Option("--count", "-n", min=1, help="How many items to list.")
        ] = 10,
    ) -> None:
        """List the latest stored news, newest first.

        `simile serve` and `simile headless` keep it fresh and analyse new articles as they come,
        unless SIMILE_NEWS=0.

        SIMILE_NEWS_FEED overrides the feeds with a comma-separated list of URLs.
        """
        import asyncio

        from simile.memory import default_path
        from simile.news.feed import feeds
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
                typer.echo(f"Analysed {len(analysed)} of {waiting} articles waiting.\n")
                failed = failed or len(analysed) < waiting
            items = store.latest(count)
        if not items:
            typer.echo("No news stored yet. Fetch it with `simile news --refresh`.")
        for item in items:
            source = f" ({item.source})" if item.source else ""
            typer.echo(f"{item.published:%Y-%m-%d %H:%M}  {item.title}{source}\n{'':18}{item.url}")
            if item.analysed:
                typer.echo(f"{'':18}{describe(item)}")
        if failed:
            raise typer.Exit(1)


async def analyse_waiting(store: "NewsStore") -> tuple[int, list["NewsItem"]]:
    import os

    from simile.llm import LLMClient
    from simile.llm.lifespan import FAKE_ENV, CannedProvider
    from simile.news.analysis import NewsAnalyser
    from simile.news.config import DEFAULT_CONFIG

    llm = LLMClient(CannedProvider() if os.environ.get(FAKE_ENV) == "fake" else None)
    try:
        waiting = len(store.unanalysed(DEFAULT_CONFIG.candidates, llm.provider.name))
        return waiting, await NewsAnalyser(store, lambda: llm).analyse_pending()
    finally:
        await llm.aclose()


def describe(item: "NewsItem") -> str:
    top = sorted(item.values.items(), key=lambda pair: pair[1], reverse=True)[:3]
    values = ", ".join(f"{value.value} {score:.1f}" for value, score in top)
    return f"{values}; tone {item.sentiment or 0:+.1f}; {', '.join(item.tags)}"
