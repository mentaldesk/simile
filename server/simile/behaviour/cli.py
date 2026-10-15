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
    ) -> None:
        """Fast-forward the village's NPCs and summarise where they spent their time.

        Runs movement and behaviour as fast as the CPU allows. Conversations and news stay
        stubbed, so nothing calls Claude.
        """
        import asyncio
        from datetime import UTC, datetime, timedelta

        from simile.behaviour.simulate import report, simulate

        begin = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=start)
        observer, seconds = asyncio.run(simulate(hours, start=begin, seed=seed))
        typer.echo(report(observer, hours, begin, seed, seconds), nl=False)

    app.add_typer(behaviour, name="behaviour")
