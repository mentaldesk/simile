from typing import TYPE_CHECKING, Annotated

import typer

if TYPE_CHECKING:
    from simile.schema import Memory, Npc, Work


def register(app: typer.Typer) -> None:
    works = typer.Typer(no_args_is_help=True, help="The residents' works.")

    @works.command()
    def make(npc: Annotated[str, typer.Argument(help="The resident's id, e.g. tobias.")]) -> None:
        """Have a resident write a piece from what's on their mind, with Claude.

        Stores the work, and their memory of making it, in $SIMILE_DB.
        """
        import asyncio

        from simile.npc import load_npcs
        from simile.schema import Medium

        residents = {resident.id: resident for resident in load_npcs()}
        if npc not in residents:
            raise typer.BadParameter(f"no such resident: {npc}", param_hint="NPC")
        resident = residents[npc]
        if resident.craft is None or resident.craft.medium is not Medium.WRITING:
            typer.echo(f"{resident.name} doesn't write.", err=True)
            raise typer.Exit(1)
        memories, work = asyncio.run(write(resident))
        typer.echo(on_mind(memories, work))
        if work is None:
            typer.echo(f"{resident.name} couldn't write a piece.", err=True)
            raise typer.Exit(1)
        typer.echo(describe(resident, work))

    app.add_typer(works, name="works")


async def write(npc: "Npc") -> tuple[list["Memory"], "Work | None"]:
    import os
    from datetime import UTC, datetime

    from simile.llm import LLMClient
    from simile.llm.lifespan import FAKE_ENV, CannedProvider
    from simile.memory import MemoryStore, default_path
    from simile.persistence import WorldStore
    from simile.sim import Clock
    from simile.works.maker import Maker
    from simile.works.store import WorksStore

    llm = LLMClient(CannedProvider() if os.environ.get(FAKE_ENV) == "fake" else None)
    with (
        MemoryStore(default_path()) as memory,
        WorksStore(memory.path) as works,
        WorldStore(memory) as world,
    ):
        saved = world.load()
        clock = Clock(saved.now if saved else datetime.now(UTC))
        maker = Maker(works, memory, clock, lambda: llm)
        memories, _ = maker.on_mind(npc, clock.now)
        try:
            task = maker.make(npc)
            return memories, await task if task else None
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
    top = sorted(work.values.items(), key=lambda pair: pair[1], reverse=True)[:5]
    values = ", ".join(f"{value.value} {score:.1f}" for value, score in top)
    return (
        f'"{work.title}", {work.form}, by {npc.name}\n\n{work.text}\n\n'
        f"Statement: {work.statement}\n"
        f"Values: {values}; tone {work.sentiment:+.1f}; {', '.join(work.tags)}\n"
        f"Stored as {work.id}."
    )
