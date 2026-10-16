from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    @app.command()
    def reset(
        yes: Annotated[bool, typer.Option("--yes", "-y", help="Don't ask first.")] = False,
    ) -> None:
        """Forget the saved village, so the next run starts afresh from content/. Keeps the
        news."""
        from simile.memory import default_path
        from simile.persistence.store import WorldStore

        path = default_path()
        if not path.exists():
            typer.echo(f"Nothing saved in {path}")
            return
        if not yes:
            typer.confirm(f"Forget the village saved in {path}?", abort=True)
        with WorldStore(path) as store:
            store.clear()
        typer.echo(f"Forgot the village saved in {path}")
