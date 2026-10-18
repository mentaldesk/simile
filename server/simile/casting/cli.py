from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

if TYPE_CHECKING:
    from simile.casting import Pin


def register(app: typer.Typer) -> None:
    @app.command("cast")
    def cast_command(
        count: Annotated[
            int | None,
            typer.Option("--random", help="How many residents, drawn from the library at random."),
        ] = None,
        pick: Annotated[
            str | None, typer.Option(help="Character ids to cast as given, comma-separated.")
        ] = None,
        pin: Annotated[
            list[str] | None,
            typer.Option(help="A bond to bind, as actor:kind:target. Repeatable."),
        ] = None,
        seed: Annotated[int | None, typer.Option(help="Defaults to a random one.")] = None,
        data: Annotated[
            Path | None,
            typer.Option(
                help="The new world's data directory. Defaults to the folder of $SIMILE_DB."
            ),
        ] = None,
        pool: Annotated[
            Path | None, typer.Option(help="Defaults to the repo's content/characters/pool/.")
        ] = None,
        game_date: Annotated[
            str | None,
            typer.Option(
                "--date", help="The day the village starts, YYYY-MM-DD. Defaults to today."
            ),
        ] = None,
    ) -> None:
        """Make a new world's residents from the character library, in a data directory of its
        own. Today's village and content/ are never touched."""
        import random

        from simile.casting import (
            CastError,
            CastRefused,
            bind,
            cast,
            check_writable,
            data_directory,
            write_cast,
        )
        from simile.characters.pool import POOL_DIR, load_pool
        from simile.memory import default_path

        if count is None and not pick and not pin:
            raise typer.BadParameter("pass --random N, --pick a,b,c or both")
        folder = data or data_directory()
        if folder is None:
            raise typer.BadParameter("pass the new world's data directory", param_hint="--data")
        folder = folder.resolve()
        try:
            check_writable(folder)
        except CastRefused as e:
            raise typer.BadParameter(str(e), param_hint="--data") from e
        picks = [id.strip() for id in (pick or "").split(",") if id.strip()]
        pins = [_pin(text) for text in pin or []]
        seed = random.SystemRandom().randrange(2**31) if seed is None else seed
        try:
            start = date.fromisoformat(game_date) if game_date else None
        except ValueError as e:
            raise typer.BadParameter(str(e), param_hint="--date") from e
        try:
            chosen = cast(load_pool(pool or POOL_DIR), count, picks, pins, seed)
            made = bind(chosen, pins, seed, start)
        except CastError as e:
            raise typer.BadParameter(str(e)) from e
        written = write_cast(made, folder)

        typer.echo(f"Cast {len(made.residents)} residents into {written} (seed {seed}):")
        for resident in made.residents:
            c = resident.character
            typer.echo(f"  {resident.home:9} {c.name}, {made.age(c)}, {c.occupation} ({c.id})")
        if made.bonds:
            typer.echo("Bonds:")
            for bond in made.bonds:
                link = "and" if bond.kind.mutual else "->"
                pinned = ", pinned" if bond.pinned else ""
                typer.echo(f"  {bond.actor} {link} {bond.target}: {bond.kind}{pinned}")
        if unvoiced := made.unvoiced():
            typer.echo(
                f"No voice clip yet for {len(unvoiced)} of them, so their lines are text only: "
                + ", ".join(c.id for c in unvoiced)
            )
        db = folder / "simile.db" if data else default_path().resolve()
        typer.echo(f"Run it with:\n  SIMILE_DB={db} uv run simile headless --speed 10")


def _pin(text: str) -> "Pin":
    from simile.casting import Pin

    parts = text.split(":")
    if len(parts) != 3:
        raise typer.BadParameter(f"{text!r} isn't actor:kind:target", param_hint="--pin")
    actor, kind, target = parts
    try:
        return Pin.model_validate({"kind": kind, "actor": actor, "target": target})
    except ValueError as e:
        raise typer.BadParameter(f"{text!r}: {e}", param_hint="--pin") from e
