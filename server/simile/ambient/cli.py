from typing import Annotated

import typer

QUIET_ENV = ("SIMILE_VOICE", "SIMILE_RECORD", "SIMILE_FRESH", "SIMILE_DEMO")


def register(app: typer.Typer) -> None:
    ambient = typer.Typer(no_args_is_help=True, help="The ambient director.")

    @ambient.command()
    def playthrough(
        runs: Annotated[int, typer.Option(min=1, help="Runs, each with its own seed.")] = 10,
        minutes: Annotated[float, typer.Option(min=1, help="Sim minutes the player plays.")] = 30,
        warmup: Annotated[
            float, typer.Option(min=0, help="Sim minutes the village runs before they join.")
        ] = 60,
        seed: Annotated[int, typer.Option(help="The first run's seed.")] = 0,
    ) -> None:
        """Play a scripted player through the village on a fake LLM, and report how often they
        overhear the residents talking.

        The player walks a route at 1x, chatting now and then. The fake LLM's lines are as long
        as Claude's and take as long to write, so nothing calls Claude.
        """
        import asyncio
        import os

        os.environ.update(SIMILE_LLM="fake", SIMILE_NEWS="0")
        for name in QUIET_ENV:
            os.environ.pop(name, None)
        from simile.ambient.playthrough import playthrough as play
        from simile.ambient.playthrough import report

        results = [
            asyncio.run(play(minutes=minutes, warmup=warmup, seed=seed + run))
            for run in range(runs)
        ]
        typer.echo(
            f"{runs} runs of {minutes:g} sim minutes after {warmup:g} minutes' warm-up.\n\n"
            + report(results),
            nl=False,
        )

    app.add_typer(ambient, name="ambient")
