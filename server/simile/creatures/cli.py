from pathlib import Path
from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    creatures = typer.Typer(help="The tunnels' creatures' painted figures.", no_args_is_help=True)

    @creatures.command("paint")
    def paint(
        which: Annotated[
            list[str] | None, typer.Argument(help="Creatures to paint; all if none.")
        ] = None,
        force: Annotated[bool, typer.Option(help="Repaint even if nothing changed.")] = False,
        paintings: Annotated[
            Path | None, typer.Option(help="Also save each painting, guide and cut-out here.")
        ] = None,
    ) -> None:
        """Paint the creatures in content/creatures/ whose catalogue entry changed, with FLUX on
        Apple Silicon (`uv sync --extra images`), waiting while another image model runs, then
        draw the preview sheet again."""
        from functools import partial

        from simile.creatures.build import build
        from simile.creatures.preview import write_preview
        from simile.dolls.flux import Flux, wait_for_gpu
        from simile.dolls.paint import NoPainter

        try:
            done = build(partial(Flux, wait_for_gpu), only=which or (), force=force, log=typer.echo)
        except (KeyError, NoPainter) as error:
            typer.echo(error.args[0], err=True)
            raise typer.Exit(1) from None
        for painted in done:
            if paintings is not None:
                paintings.mkdir(parents=True, exist_ok=True)
                name = painted.creature.id
                for frame, image in painted.paintings.items():
                    image.save(paintings / f"{name}-{frame}.png")
                    painted.figures[frame].save(paintings / f"{name}-{frame}-cut.png")
                for frame, image in painted.guides.items():
                    image.save(paintings / f"{name}-{frame}-guide.png")
        if done:
            typer.echo(f"wrote {write_preview()}")

    @creatures.command("preview")
    def preview() -> None:
        """Draw content/creatures/preview.png again from the committed figures."""
        from simile.creatures.preview import write_preview

        typer.echo(f"wrote {write_preview()}")

    app.add_typer(creatures, name="creatures")
