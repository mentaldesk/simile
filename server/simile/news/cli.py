from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    @app.command()
    def news(
        refresh: Annotated[bool, typer.Option(help="Fetch the live feeds first.")] = False,
        count: Annotated[
            int, typer.Option("--count", "-n", min=1, help="How many items to list.")
        ] = 10,
    ) -> None:
        """List the latest stored news, newest first.

        `simile serve` and `simile headless` keep it fresh only with SIMILE_NEWS=1.

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
                        typer.echo(f"{len(result)} new items from {label}")
                typer.echo()
            items = store.latest(count)
        if not items:
            typer.echo("No news stored yet. Fetch it with `simile news --refresh`.")
        for item in items:
            source = f" ({item.source})" if item.source else ""
            typer.echo(f"{item.published:%Y-%m-%d %H:%M}  {item.title}{source}\n{'':18}{item.url}")
        if failed:
            raise typer.Exit(1)
