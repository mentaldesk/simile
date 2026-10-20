from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

if TYPE_CHECKING:
    from simile.llm.client import CallRecord
    from simile.llm.provider import Request
    from simile.schema import Memory, Npc, Work
    from simile.works.starters import Starter


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
        from simile.world.map import load_maps, with_every_location

        residents = {resident.id: resident for resident in load_npcs()}
        if npc not in residents:
            raise typer.BadParameter(f"no such resident: {npc}", param_hint="NPC")
        resident = residents[npc]
        if resident.craft is None:
            typer.echo(f"{resident.name} doesn't make anything.", err=True)
            raise typer.Exit(1)
        walls = with_every_location(load_maps()).murals
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

    @works.command()
    def starter(
        out: Annotated[
            Path | None, typer.Option(help="Where to put them. By default, content/works/.")
        ] = None,
    ) -> None:
        """Make the works today's village starts with, with Claude: about 15 Sonnet calls.

        Makes those OUT doesn't have yet, one at a time, saving each as it's made, and stops at
        the first that fails, so running it again carries on. With SIMILE_LLM=fake, stand-ins.
        """
        import asyncio
        from collections import Counter

        from simile.works.starters import Stopped

        calls: list[CallRecord] = []
        failed = None
        try:
            made = asyncio.run(starters(out, calls))
        except Stopped as stopped:
            made, failed = stopped.made, stopped
        for each in made:
            typer.echo(f"{each.work.id}  {each.work.medium.value:8}  {each.work.title}")
        purposes = Counter(call.purpose for call in calls)
        errors = sum(call.error is not None for call in calls)
        typer.echo(
            f"{len(made)} starter works. {len(calls)} LLM calls this run "
            f"({', '.join(f'{n} {purpose}' for purpose, n in purposes.items()) or 'none'}), "
            f"{errors} failed."
        )
        if failed is not None:
            typer.echo(f"Stopped: {failed}.", err=True)
            raise typer.Exit(1)

    @works.command()
    def download() -> None:
        """Download the image model that paints murals and paintings with SIMILE_IMAGES=1.

        FLUX.2 [klein] 4B, about 16 GB, from its Hugging Face repo into the local cache. Needs
        Apple Silicon and the images extra: uv sync --extra images.
        """
        from simile.works.config import DEFAULT_CONFIG

        try:
            from simile.works import flux
        except ImportError:
            typer.echo(
                "It needs Apple Silicon and the images extra: uv sync --extra images", err=True
            )
            raise typer.Exit(1) from None
        typer.echo(f"Downloaded to {flux.download(DEFAULT_CONFIG.image_model)}")

    app.add_typer(works, name="works")


async def starters(out: Path | None, calls: list["CallRecord"]) -> list["Starter"]:
    import os
    from datetime import UTC, datetime

    from simile.llm import FakeProvider, LLMClient
    from simile.llm.lifespan import FAKE_ENV
    from simile.npc import NPCS_DIR, load_npcs
    from simile.works.starters import STARTERS, make
    from simile.world.map import load_maps, with_every_location

    fake = os.environ.get(FAKE_ENV) == "fake"
    provider = FakeProvider([stand_in] * 64) if fake else None
    llm = LLMClient(provider, listeners=[calls.append])
    npcs = {npc.id: npc for npc in load_npcs(NPCS_DIR)}
    start = datetime(2026, 1, 1, 8, tzinfo=UTC)
    walls = with_every_location(load_maps()).murals
    try:
        return await make(llm, npcs, walls, out or STARTERS, start=start)
    finally:
        await llm.aclose()


def stand_in(request: "Request") -> str:
    """With `SIMILE_LLM=fake`, a plain piece, mural or painting, so the checks and the renderer
    run without Claude."""
    import re

    from simile.schema import CoreValue
    from simile.works.maker import MuralReply, Reply

    asked = request.messages[-1].content
    common = {
        "title": "Stand-in",
        "statement": "A stand-in, made without Claude.",
        "inspired_by": [],
        "tags": ["stand-in"],
        "sentiment": 5.0,
        **{value.value: 0.0 for value in CoreValue},
    }
    if not (size := re.search(r'viewBox="0 0 (\d+) (\d+)"', asked)):
        return Reply.model_validate({**common, "text": "A stand-in piece."}).model_dump_json()
    width, height = int(size[1]), int(size[2])
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">'
        f'<rect width="{width}" height="{height}" fill="#2a4d69"/>'
        f'<rect y="{height // 2}" width="{width}" height="{height - height // 2}" fill="#e8a33d"/>'
        "</svg>"
    )
    mural = {**common, "description": "Two bands of colour, blue over amber.", "svg": svg}
    return MuralReply.model_validate(mural).model_dump_json()


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
    from simile.works.painter import easel
    from simile.works.store import WorksStore
    from simile.works.walls import Walls
    from simile.world.map import load_maps, with_every_location

    walls = with_every_location(load_maps()).murals
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
        try:
            async with easel() as painter:
                maker = Maker(
                    works, memory, clock, lambda: llm, walls=walls, npcs=npcs, painter=painter
                )
                memories, _ = maker.on_mind(npc, clock.now)
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
