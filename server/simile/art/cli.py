from pathlib import Path
from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    @app.command()
    def art(
        npcs: Annotated[
            bool, typer.Option("--npcs", help="Only render the NPC sprites from content/npcs/.")
        ] = False,
        content: Annotated[
            Path | None, typer.Option(help="Content directory. Defaults to the repo's content/.")
        ] = None,
    ) -> None:
        """Regenerate the tileset, character sprites and previews in content/art/."""
        from simile.art.build import CONTENT_DIR, generate

        root = content or CONTENT_DIR
        written = generate(root, npcs_only=npcs)
        typer.echo(f"Wrote {len(written)} files to {root / 'art'}")
