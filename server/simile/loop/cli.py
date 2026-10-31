from pathlib import Path
from typing import Annotated

import typer

QUIET_ENV = ("SIMILE_VOICE", "SIMILE_RECORD", "SIMILE_FRESH")


def fake_llm() -> None:
    import os

    os.environ.update(SIMILE_LLM="fake", SIMILE_NEWS="0")
    for name in QUIET_ENV:
        os.environ.pop(name, None)


def register(app: typer.Typer) -> None:
    loop = typer.Typer(no_args_is_help=True, help="S15: the loop, played end to end.")

    @loop.command()
    def play(
        seed: Annotated[int, typer.Option(help="Seeds the residents and the disappearance.")] = 0,
        saves: Annotated[
            Path | None,
            typer.Option(help="Writes the world here before each of the browser's beats."),
        ] = None,
    ) -> None:
        """Play the loop in the sim, on the fake LLM, and say how it went and how long it took."""
        import asyncio
        import os

        fake_llm()
        os.environ["SIMILE_DB"] = ":memory:"
        from simile.loop.playthrough import play as run
        from simile.loop.playthrough import report

        typer.echo(report(asyncio.run(run(seed=seed, saves=saves))), nl=False)

    @loop.command()
    def serve(
        save: Annotated[Path, typer.Argument(help="A world `play --saves` wrote.", exists=True)],
        at: Annotated[str, typer.Option(help="Where the player starts, like metro:87:15.")],
        port: int = 8000,
        origin: Annotated[
            list[str] | None, typer.Option(help="Another origin the client may be served from.")
        ] = None,
    ) -> None:
        """Serve a copy of a saved world on the fake LLM, with the player at `at`."""
        import os
        import shutil
        import tempfile

        import uvicorn

        fake_llm()
        scratch = Path(tempfile.mkdtemp(prefix="simile-loop-"))
        os.environ["SIMILE_DB"] = str(shutil.copyfile(save, scratch / save.name))
        if origin:
            os.environ["SIMILE_ORIGINS"] = ",".join(origin)
        from simile.loop.serve import create_loop_app
        from simile.world.paths import Spot

        map, x, y = at.split(":")
        app = create_loop_app(Spot(map, int(x), int(y)), scratch)
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")

    app.add_typer(loop, name="loop")
