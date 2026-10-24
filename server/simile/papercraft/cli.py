from pathlib import Path
from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    @app.command()
    def papercraft(
        only: Annotated[
            list[str] | None,
            typer.Option(help="Only pieces whose key matches this glob, e.g. 'fronts/*'."),
        ] = None,
        dry_run: Annotated[
            bool, typer.Option(help="List what's stale and what needs painting, and stop.")
        ] = False,
        maps: Annotated[
            Path | None,
            typer.Option(help="Side-view maps to fit, if not content/street/."),
        ] = None,
    ) -> None:
        """Paint the village's papercraft scenery into content/papercraft/, with FLUX.2 Klein in
        edit mode, once the GPU is free. Needs Apple Silicon and the `images` extra. Repaints only
        what changed.

        First copies the maps' layout into content/papercraft/layout.json, if the maps are there
        and it changed."""
        from fnmatch import fnmatch

        from simile.dolls.flux import wait_for_gpu
        from simile.papercraft.build import Build
        from simile.papercraft.layout import STREET_DIR, refresh
        from simile.papercraft.painter import EditPainter

        def waiting() -> EditPainter:
            wait_for_gpu(typer.echo)
            return EditPainter()

        if refresh(maps or STREET_DIR):
            typer.echo("Updated layout.json from the maps")

        def chosen(key: str) -> bool:
            return not only or any(fnmatch(key, pattern) for pattern in only)

        build = Build(painter=waiting)
        if dry_run:
            stale = build.stale(build.read_manifest(), [k for k in build.pieces if chosen(k)])
            for piece in stale:
                cached = "to paint" if build.unpainted([piece]) else "cached"
                typer.echo(f"{piece.key} ({cached})")
            typer.echo(f"{len(stale)} stale")
            return
        report = build.run(chosen, log=typer.echo)
        seconds = sum(report.painted.values())
        typer.echo(
            f"Painted {len(report.painted)} in {seconds:.0f}s, wrote {len(report.written)}, "
            f"removed {len(report.removed)}"
        )

    @app.command("papercraft-preview")
    def papercraft_preview(
        out: Annotated[Path, typer.Argument(help="Where to write the pictures.")],
        maps: Annotated[
            Path | None, typer.Option(help="Side-view maps to compose, if not content/street/.")
        ] = None,
    ) -> None:
        """Contact sheets of every papercraft piece, and streets and dollhouses composed from
        them on the side-view maps at each time of day, for looking at."""
        from simile.papercraft.layout import STREET_DIR
        from simile.papercraft.preview import preview

        for path in preview(out, maps or STREET_DIR):
            typer.echo(path)
