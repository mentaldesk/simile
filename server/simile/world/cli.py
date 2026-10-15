from pathlib import Path
from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    @app.command(name="map")
    def build_map(
        content: Annotated[
            Path | None, typer.Option(help="Content directory. Defaults to the repo's content/.")
        ] = None,
    ) -> None:
        """Regenerate the village map and its previews in content/map/ from content/art/."""
        from simile.world.build_map import generate
        from simile.world.map import CONTENT_DIR

        root = content or CONTENT_DIR
        written = generate(root / "art", root / "map")
        typer.echo(f"Wrote {len(written)} files to {root / 'map'}")
