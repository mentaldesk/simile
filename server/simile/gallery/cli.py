from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

if TYPE_CHECKING:
    from simile.gallery.store import FrameKey
    from simile.schema import Memory, Npc, Work


def register(app: typer.Typer) -> None:
    gallery = typer.Typer(no_args_is_help=True, help="The gallery's paintings.")

    @gallery.command()
    def paint(
        npc: Annotated[str, typer.Argument(help="A painter's or muralist's id, e.g. kofi.")],
        png: Annotated[Path | None, typer.Option(help="Where to save the picture too.")] = None,
    ) -> None:
        """Have a resident paint a canvas for the gallery from what's on their mind, with Claude.

        Stores the work, their memory of making it and the picture in $SIMILE_DB, and hangs it.
        """
        import asyncio

        from simile.npc import load_npcs
        from simile.schema import Medium
        from simile.works.cli import describe, on_mind

        residents = {resident.id: resident for resident in load_npcs()}
        if npc not in residents:
            raise typer.BadParameter(f"no such resident: {npc}", param_hint="NPC")
        resident = residents[npc]
        if resident.craft is None or resident.craft.medium is Medium.WRITING:
            typer.echo(f"{resident.name} doesn't paint.", err=True)
            raise typer.Exit(1)
        memories, work, frame, picture = asyncio.run(create(resident, residents))
        typer.echo(on_mind(memories, work))
        if work is None or frame is None:
            typer.echo(f"{resident.name} couldn't paint anything.", err=True)
            raise typer.Exit(1)
        if png is not None and picture is not None:
            png.write_bytes(picture)
        typer.echo(describe(resident, work))
        typer.echo(f"Hung in {frame[1]} on {frame[0]}.")

    app.add_typer(gallery, name="gallery")


async def create(
    npc: "Npc", npcs: dict[str, "Npc"]
) -> tuple[list["Memory"], "Work | None", "FrameKey | None", bytes | None]:
    """What's on their mind, what they painted, where it hangs, and its picture."""
    import os
    from datetime import UTC, datetime

    from simile.gallery.gallery import Gallery, frames_of
    from simile.gallery.store import GalleryStore
    from simile.llm import LLMClient
    from simile.llm.lifespan import FAKE_ENV, CannedProvider
    from simile.memory import MemoryStore, default_path
    from simile.persistence import WorldStore
    from simile.sim import Clock
    from simile.works.maker import Maker
    from simile.works.store import WorksStore
    from simile.world.map import load_maps

    with (
        MemoryStore(default_path()) as memory,
        WorksStore(memory.path) as works,
        GalleryStore(memory.path) as store,
        WorldStore(memory) as world,
    ):
        saved = world.load()
        clock = Clock(saved.now if saved else datetime.now(UTC))
        gallery = Gallery(frames_of(load_maps()), store, works, clock, npcs)
        hung: list[FrameKey] = []
        llm = LLMClient(CannedProvider() if os.environ.get(FAKE_ENV) == "fake" else None)

        def hang(work: "Work", svg: str, png: bytes) -> None:
            hung.append(gallery.hang(work, svg, png))

        maker = Maker(works, memory, clock, lambda: llm, npcs=npcs, hang=hang)
        memories, _ = maker.on_mind(npc, clock.now)
        try:
            task = maker.make(npc)
            work = await task if task else None
            picture = store.picture(work.id) if work else None
            return memories, work, hung[0] if hung else None, picture
        finally:
            await llm.aclose()
