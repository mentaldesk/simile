from pathlib import Path
from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    @app.command("generate-npcs")
    def generate_npcs(
        count: Annotated[int, typer.Option(help="How many residents, one per home.")] = 10,
        seed: Annotated[int, typer.Option(help="Seeds the values, ages, genders and homes.")] = 0,
        out: Annotated[
            Path | None, typer.Option(help="Defaults to the repo's content/npcs/.")
        ] = None,
        model: Annotated[str, typer.Option(help="Claude model that writes the NPCs.")] = "sonnet",
    ) -> None:
        """Generate the village's residents with Claude and write them to content/npcs/."""
        import asyncio

        from simile.llm import CallRecord, LLMClient
        from simile.npc.content import NPCS_DIR, write_npcs
        from simile.npc.generate import HOMES, generate
        from simile.schema import Npc

        if not 1 <= count <= len(HOMES):
            raise typer.BadParameter(f"must be 1-{len(HOMES)}, one per home", param_hint="--count")

        calls: list[CallRecord] = []
        llm = LLMClient(listeners=[calls.append])

        async def run() -> list[Npc]:
            npcs = []
            async for npc in generate(llm, count, seed, model=model):
                typer.echo(f"{npc.home}: {npc.name} ({npc.id}), {npc.age}, {npc.occupation}")
                npcs.append(npc)
            return npcs

        npcs = asyncio.run(run())
        directory = out or NPCS_DIR
        write_npcs(npcs, directory, seed)
        typer.echo(f"Wrote {len(npcs)} NPCs to {directory} with {len(calls)} Claude calls")
