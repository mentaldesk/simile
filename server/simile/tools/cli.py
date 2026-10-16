from pathlib import Path
from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    @app.command()
    def report(
        db: Annotated[
            Path | None,
            typer.Option(
                help="The database. Defaults to $SIMILE_DB, or server/data/simile.db.",
                show_default=False,
            ),
        ] = None,
        run: Annotated[
            int | None,
            typer.Option(help="Which recorded run. Defaults to the latest.", show_default=False),
        ] = None,
    ) -> None:
        """Summarise a run recorded with SIMILE_RECORD=1, as Markdown."""
        from simile.memory import default_path
        from simile.tools.report import NoRun, load_run
        from simile.tools.report import report as summarise

        path = db or default_path()
        if not path.is_file():
            typer.echo(f"No database at {path}", err=True)
            raise typer.Exit(1)
        try:
            recorded = load_run(path, run)
        except NoRun as e:
            typer.echo(str(e), err=True)
            raise typer.Exit(1) from None
        typer.echo(summarise(recorded), nl=False)
