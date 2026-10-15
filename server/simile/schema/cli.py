from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    @app.command()
    def schema(
        check: Annotated[
            bool, typer.Option(help="Fail if the exported files are out of date; write nothing.")
        ] = False,
    ) -> None:
        """Export JSON Schema for the domain models to server/simile/schema/json/."""
        from simile.schema.export import JSON_DIR, outdated, write

        if not check:
            write()
            return
        if names := outdated():
            typer.echo(
                f"Out of date in {JSON_DIR}: {', '.join(names)}. Run `uv run simile schema`."
            )
            raise typer.Exit(1)
