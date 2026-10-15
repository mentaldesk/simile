from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    @app.command()
    def headless(
        speed: Annotated[float, typer.Option(help="Sim seconds per real second.")] = 1.0,
        duration: Annotated[
            float | None,
            typer.Option(
                min=0,
                help="Sim hours to run for. Runs until Ctrl-C if omitted.",
                show_default=False,
            ),
        ] = None,
    ) -> None:
        """Run the village without a client and log its events."""
        import asyncio
        import logging
        from datetime import timedelta

        from simile.sim.clock import Clock
        from simile.sim.headless import run_headless
        from simile.sim.world import World

        if speed <= 0:
            raise typer.BadParameter("must be more than 0", param_hint="'--speed'")
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        world = World(Clock(speed=speed))
        try:
            asyncio.run(
                run_headless(world, None if duration is None else timedelta(hours=duration))
            )
        except KeyboardInterrupt:
            raise typer.Exit(130) from None
