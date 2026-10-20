from pathlib import Path
from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    behaviour = typer.Typer(no_args_is_help=True, help="NPC behaviour.")

    @behaviour.command()
    def simulate(
        hours: Annotated[float, typer.Option(min=0, help="Sim hours to run for.")] = 24.0,
        start: Annotated[
            float, typer.Option(min=0, max=24, help="Sim hour of day to start at.")
        ] = 8.0,
        seed: Annotated[int, typer.Option(help="Seed for the NPCs' choices.")] = 0,
        talk: Annotated[
            float | None,
            typer.Option(
                min=0,
                help="Accept every request to talk and end each conversation after this many sim "
                "minutes. Without it, every request is declined.",
            ),
        ] = None,
        intentions: Annotated[
            float | None,
            typer.Option(
                min=0.1,
                help="Every this many sim hours, each resident awake says they'll do something at "
                "random, now or later, and the summary adds how many they kept.",
            ),
        ] = None,
        maps: Annotated[
            Path | None,
            typer.Option(
                exists=True,
                file_okay=False,
                help="A folder of maps to run on, such as content/street. Defaults to the "
                "server's.",
            ),
        ] = None,
    ) -> None:
        """Fast-forward the village's NPCs and summarise where they spent their time.

        Runs movement and behaviour as fast as the CPU allows. Conversations and news stay
        stubbed, so nothing calls Claude.
        """
        import asyncio
        from datetime import UTC, datetime, timedelta

        from simile.behaviour.simulate import report, simulate

        begin = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=start)
        observer, seconds = asyncio.run(
            simulate(hours, start=begin, seed=seed, talk=talk, intentions=intentions, maps=maps)
        )
        typer.echo(report(observer, hours, begin, seed, seconds), nl=False)

    app.add_typer(behaviour, name="behaviour")
