from pathlib import Path
from typing import Annotated

import typer


def register(art: typer.Typer) -> None:
    iso = typer.Typer(no_args_is_help=True, help="Pre-rendered isometric art, made in Blender.")
    art.add_typer(iso, name="iso")

    @iso.command()
    def scenery(
        light: Annotated[
            list[str] | None,
            typer.Option("--set", help="Only this lighting set; repeat for more. Default: all."),
        ] = None,
        content: Annotated[
            Path | None, typer.Option(help="Content directory. Defaults to the repo's content/.")
        ] = None,
        work: Annotated[
            Path | None, typer.Option(help="Keep Blender's raw renders here. Default: a temp dir.")
        ] = None,
        force: Annotated[bool, typer.Option(help="Render everything, changed or not.")] = False,
    ) -> None:
        """Render the ground, object sprites and light map of each lighting set that changed."""
        from simile.art.iso.lighting import SETS
        from simile.art.iso.scenery import CONTENT_DIR, build

        unknown = [name for name in light or [] if name not in SETS]
        if unknown:
            raise typer.BadParameter(f"unknown set {unknown}; choose from {list(SETS)}")
        for report in build(content or CONTENT_DIR, light, work, force):
            if not report.rendered:
                summary = "up to date"
            else:
                wall = report.seconds.get("wall", 0)
                summary = f"rendered {len(report.rendered)} in {wall:.0f} s"
            typer.echo(
                f"{report.name}: {summary}, wrote {len(report.written)}, "
                f"removed {len(report.removed)}, {report.bytes / 1e6:.2f} MB"
            )
