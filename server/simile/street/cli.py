from pathlib import Path
from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    @app.command(name="street")
    def build_street(
        out: Annotated[
            Path | None,
            typer.Option(help="Where to write. Defaults to the repo's content/street/."),
        ] = None,
    ) -> None:
        """Regenerate the side-view village's street and floor maps in content/street/."""
        from simile.street.generate import generate
        from simile.world.map import STREET_DIR

        folder = out or STREET_DIR
        written = generate(folder)
        typer.echo(f"Wrote {len(written)} files to {folder}")
