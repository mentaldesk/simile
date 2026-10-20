from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    @app.command()
    def reset(
        yes: Annotated[bool, typer.Option("--yes", "-y", help="Don't ask first.")] = False,
    ) -> None:
        """Forget the saved village, so the next run starts afresh from content/. Keeps the
        news."""
        from simile.memory import MemoryStore, default_path
        from simile.persistence.store import WorldStore

        path = default_path()
        if not path.exists():
            typer.echo(f"Nothing saved in {path}")
            return
        if not yes:
            typer.confirm(f"Forget the village saved in {path}?", abort=True)
        with MemoryStore(path) as memory, WorldStore(memory) as store:
            store.clear()
        typer.echo(f"Forgot the village saved in {path}")

    @app.command(name="old-cells")
    def old_cells() -> None:
        """Rewrite the table that moves positions saved on today's maps in content/map/ to the
        side-view maps in content/street/."""
        from simile.persistence.old_cells import TABLE, build, write
        from simile.world.map import ISO_DIR, STREET_DIR, load_maps

        rows = build(load_maps(ISO_DIR), load_maps(STREET_DIR))
        write(rows)
        typer.echo(f"Wrote {len(rows)} runs of cells to {TABLE}")
