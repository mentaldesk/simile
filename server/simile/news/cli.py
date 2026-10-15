from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    @app.command()
    def news(
        refresh: Annotated[bool, typer.Option(help="Fetch the live feed first.")] = False,
        count: Annotated[
            int, typer.Option("--count", "-n", min=1, help="How many items to list.")
        ] = 10,
    ) -> None:
        """List the latest stored news, newest first.

        `simile serve` and `simile headless` keep it fresh only with SIMILE_NEWS=1.

        SIMILE_NEWS_FEED overrides the feed's URL.
        """
        import asyncio

        from simile.memory import default_path
        from simile.news.feed import feed_url
        from simile.news.refresh import refresh as fetch_news
        from simile.news.store import NewsStore

        with NewsStore(default_path()) as store:
            if refresh:
                url = feed_url()
                try:
                    added = asyncio.run(fetch_news(store, url))
                except (OSError, ValueError) as error:
                    typer.echo(f"Couldn't fetch {url}: {error}", err=True)
                    raise typer.Exit(1) from None
                typer.echo(f"{len(added)} new items from {url}\n")
            items = store.latest(count)
        if not items:
            typer.echo("No news stored yet. Fetch it with `simile news --refresh`.")
        for item in items:
            typer.echo(f"{item.published:%Y-%m-%d %H:%M}  {item.title}\n{'':18}{item.url}")
