from pathlib import Path
from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    dolls = typer.Typer(help="The residents' painted figures.", no_args_is_help=True)

    @dolls.command("paint")
    def paint(
        who: Annotated[
            list[str] | None, typer.Argument(help="Residents or player; all if none.")
        ] = None,
        force: Annotated[bool, typer.Option(help="Repaint even if nothing changed.")] = False,
        paintings: Annotated[
            Path | None, typer.Option(help="Also save each painting and cut-out here.")
        ] = None,
    ) -> None:
        """Paint the figures in content/dolls/ whose Appearance changed, with FLUX on Apple
        Silicon (`uv sync --extra images`), waiting while another image model runs."""
        from functools import partial

        from simile.dolls.build import build
        from simile.dolls.flux import Flux, wait_for_gpu
        from simile.dolls.measure import CLOSE
        from simile.dolls.paint import NoPainter

        try:
            done = build(partial(Flux, wait_for_gpu), only=who or (), force=force)
        except (KeyError, NoPainter) as error:
            typer.echo(error.args[0], err=True)
            raise typer.Exit(1) from None
        for painted in done:
            if paintings is not None:
                paintings.mkdir(parents=True, exist_ok=True)
                for frame, image in painted.paintings.items():
                    image.save(paintings / f"{painted.who}-{frame}.png")
                    painted.figures[frame].save(paintings / f"{painted.who}-{frame}-cut.png")
            for frame, tries in painted.tries.items():
                kept = tries[-1].matched
                off = {k: s.delta_e for k, s in kept.items() if s.delta_e > CLOSE}
                if off:
                    typer.echo(f"{painted.who} {frame}: still off by {off}")

    @dolls.command("seats")
    def seats() -> None:
        """Measure each figure's seat in content/dolls/ again from its atlas, without painting."""
        from simile.dolls.build import reseat

        for path in reseat():
            typer.echo(f"wrote {path.name}")

    app.add_typer(dolls, name="dolls")
