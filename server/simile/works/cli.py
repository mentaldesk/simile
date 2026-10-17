from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

if TYPE_CHECKING:
    from simile.schema import Memory, Npc, Work


class NoWall(Exception):
    """No wall is worth a muralist's painting over."""


def register(app: typer.Typer) -> None:
    works = typer.Typer(no_args_is_help=True, help="The residents' works.")

    @works.command()
    def make(
        npc: Annotated[str, typer.Argument(help="The resident's id, e.g. tobias.")],
        wall: Annotated[
            str | None,
            typer.Option(
                help="For a muralist, the wall to paint. By default, the one they'd pick."
            ),
        ] = None,
        png: Annotated[
            Path | None, typer.Option(help="For a muralist, where to save the mural's picture too.")
        ] = None,
    ) -> None:
        """Have a resident write a piece or paint a mural from what's on their mind, with Claude.

        Stores the work, and their memory of making it, in $SIMILE_DB.
        """
        import asyncio

        from simile.npc import load_npcs
        from simile.schema import Medium
        from simile.world.map import load_map

        residents = {resident.id: resident for resident in load_npcs()}
        if npc not in residents:
            raise typer.BadParameter(f"no such resident: {npc}", param_hint="NPC")
        resident = residents[npc]
        if resident.craft is None:
            typer.echo(f"{resident.name} doesn't make anything.", err=True)
            raise typer.Exit(1)
        walls = load_map().murals
        if wall is not None and wall not in {w.id for w in walls}:
            raise typer.BadParameter(f"no such wall: {wall}", param_hint="--wall")
        mural = resident.craft.medium is Medium.MURAL
        try:
            memories, work, picture = asyncio.run(create(resident, residents, wall))
        except NoWall:
            typer.echo(
                f"{resident.name} has no wall worth painting just now. Name one with --wall.",
                err=True,
            )
            raise typer.Exit(1) from None
        typer.echo(on_mind(memories, work))
        if work is None:
            made = "paint a mural" if mural else "write a piece"
            typer.echo(f"{resident.name} couldn't {made}.", err=True)
            raise typer.Exit(1)
        if png is not None and picture is not None:
            png.write_bytes(picture)
        typer.echo(describe(resident, work))

    app.add_typer(works, name="works")


async def create(
    npc: "Npc", npcs: dict[str, "Npc"], wall: str | None
) -> tuple[list["Memory"], "Work | None", bytes | None]:
    """What's on their mind, what they made, and a mural's picture."""
    import os
    from datetime import UTC, datetime

    from simile.llm import LLMClient
    from simile.llm.lifespan import FAKE_ENV, CannedProvider
    from simile.memory import MemoryStore, default_path
    from simile.persistence import WorldStore
    from simile.schema import Medium
    from simile.sim import Clock
    from simile.works.maker import Maker
    from simile.works.store import WorksStore
    from simile.works.walls import Walls
    from simile.world.map import load_map

    walls = load_map().murals
    with (
        MemoryStore(default_path()) as memory,
        WorksStore(memory.path) as works,
        WorldStore(memory) as world,
    ):
        saved = world.load()
        clock = Clock(saved.now if saved else datetime.now(UTC))
        if wall is None and npc.craft is not None and npc.craft.medium is Medium.MURAL:
            spot = Walls(walls, works, memory, clock, npcs).pick(npc)
            if spot is None:
                raise NoWall
            wall = spot.wall
        llm = LLMClient(CannedProvider() if os.environ.get(FAKE_ENV) == "fake" else None)
        maker = Maker(works, memory, clock, lambda: llm, walls=walls, npcs=npcs)
        memories, _ = maker.on_mind(npc, clock.now)
        try:
            task = maker.make(npc, wall)
            work = await task if task else None
            return memories, work, works.picture(work.id) if work else None
        finally:
            await llm.aclose()


def on_mind(memories: list["Memory"], work: "Work | None") -> str:
    from simile.works.maker import source

    inspired = set(work.inspired_by) if work else set()
    lines = [
        f"{'*' if source(m) in inspired else ' '} {m.valence:+.1f} {m.salience:.1f}  {m.content}"
        for m in memories
    ]
    return "\n".join(["On their mind (* inspired it; valence, salience):", *lines, ""])


def describe(npc: "Npc", work: "Work") -> str:
    from simile.works.walls import wall_name

    top = sorted(work.values.items(), key=lambda pair: pair[1], reverse=True)[:5]
    values = ", ".join(f"{value.value} {score:.1f}" for value, score in top)
    where = f" on {wall_name(work.wall)}" if work.wall else ""
    return (
        f'"{work.title}", {work.form}, by {npc.name}{where}\n\n{work.text}\n\n'
        f"Statement: {work.statement}\n"
        f"Values: {values}; tone {work.sentiment:+.1f}; {', '.join(work.tags)}\n"
        f"Stored as {work.id}."
    )
