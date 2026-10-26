from pathlib import Path
from typing import Annotated

import typer

OTHERS = "simile (creatures|icons)"
"""Painting runs `dolls.flux.busy` doesn't look for."""


def busy() -> list[str]:
    """Other image models on this Mac, painting creatures or icons too."""
    import subprocess

    from simile.dolls.flux import SHELLS, busy, ours

    mine = ours()
    run = subprocess.run(["pgrep", "-fl", OTHERS], capture_output=True, text=True)
    found = [
        line
        for line in run.stdout.splitlines()
        if line.partition(" ")[0] not in mine
        and Path(line.partition(" ")[2].split(" ", 1)[0]).name not in SHELLS
    ]
    return busy() + found


def wait_for_gpu(log=typer.echo) -> None:
    import time

    from simile.dolls.flux import WAIT_S

    while others := busy():
        log(f"Waiting for {others}")
        time.sleep(WAIT_S)


def register(app: typer.Typer) -> None:
    icons = typer.Typer(help="Pictures of things on their own.", no_args_is_help=True)

    @icons.command("paint")
    def paint(
        which: Annotated[
            list[str] | None, typer.Argument(help="Icons to paint; all if none.")
        ] = None,
        force: Annotated[bool, typer.Option(help="Repaint even if nothing changed.")] = False,
        paintings: Annotated[
            Path | None, typer.Option(help="Also save each painting and cut-out here.")
        ] = None,
    ) -> None:
        """Paint the icons in content/icons/ whose catalogue entry changed, with FLUX on Apple
        Silicon (`uv sync --extra images`), waiting while another image model runs."""
        from functools import partial

        from simile.dolls.flux import Flux
        from simile.dolls.paint import NoPainter
        from simile.icons.build import build

        try:
            done = build(partial(Flux, wait_for_gpu), only=which or (), force=force, log=typer.echo)
        except (KeyError, NoPainter) as error:
            typer.echo(error.args[0], err=True)
            raise typer.Exit(1) from None
        if paintings is not None:
            paintings.mkdir(parents=True, exist_ok=True)
            for painted in done:
                painted.painting.save(paintings / f"{painted.icon.id}.png")
                painted.figure.save(paintings / f"{painted.icon.id}-cut.png")

    app.add_typer(icons, name="icons")
