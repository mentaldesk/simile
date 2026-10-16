from pathlib import Path
from typing import Annotated

import typer

from simile.art.iso import cli as iso


def register(app: typer.Typer) -> None:
    art = typer.Typer(invoke_without_command=True)
    app.add_typer(art, name="art")
    iso.register(art)

    @art.callback()
    def regenerate(
        ctx: typer.Context,
        npcs: Annotated[
            bool, typer.Option("--npcs", help="Only render the NPC sprites from content/npcs/.")
        ] = False,
        content: Annotated[
            Path | None, typer.Option(help="Content directory. Defaults to the repo's content/.")
        ] = None,
    ) -> None:
        """Regenerate the tileset, character sprites and previews in content/art/."""
        if ctx.invoked_subcommand is not None:
            return
        from simile.art.build import CONTENT_DIR, generate

        root = content or CONTENT_DIR
        written = generate(root, npcs_only=npcs)
        typer.echo(f"Wrote {len(written)} files to {root / 'art'}")
