from pathlib import Path
from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    dolls = typer.Typer(help="The residents' paper dolls.", no_args_is_help=True)

    @dolls.command("paint")
    def paint(
        who: Annotated[
            list[str] | None, typer.Argument(help="Residents or player; all if none.")
        ] = None,
        force: Annotated[bool, typer.Option(help="Repaint even if nothing changed.")] = False,
        paintings: Annotated[
            Path | None, typer.Option(help="Also save each sheet and painting here, to look at.")
        ] = None,
    ) -> None:
        """Paint the dolls in content/dolls/ whose Appearance changed, with part 3's FLUX painter
        on Apple Silicon (`uv sync --extra images`)."""
        from simile.dolls.build import build
        from simile.dolls.paint import EditPainter

        for painted in build(EditPainter, only=who or (), force=force):
            if paintings is not None:
                paintings.mkdir(parents=True, exist_ok=True)
                for sheet, image in painted.paintings.items():
                    image.save(paintings / f"{painted.who}-{sheet}.png")
            moved = {k: round(v, 3) for k, v in painted.misplaced.items() if v > 0.02}
            added = {k: round(v, 3) for k, v in painted.patches.items() if v > 0.05}
            if moved:
                typer.echo(f"{painted.who}: pieces the painter moved or dropped: {moved}")
            if added:
                typer.echo(f"{painted.who}: pieces the painter added to: {added}")

    app.add_typer(dolls, name="dolls")
