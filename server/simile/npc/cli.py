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
        rich_brief: Annotated[
            bool,
            typer.Option(
                "--rich-brief",
                help="Also sample each resident's name, origin, occupation and life events in "
                "code. Needs an --out outside content/.",
            ),
        ] = False,
    ) -> None:
        """Generate the village's residents with Claude and write them to content/npcs/."""
        import asyncio

        from simile.llm import CallRecord, LLMClient
        from simile.npc.content import NPCS_DIR, write_npcs
        from simile.npc.generate import HOMES, generate, plan
        from simile.schema import Npc

        if not 1 <= count <= len(HOMES):
            raise typer.BadParameter(f"must be 1-{len(HOMES)}, one per home", param_hint="--count")
        if rich_brief and (out is None or out.resolve().is_relative_to(NPCS_DIR.parent)):
            raise typer.BadParameter("--rich-brief needs one outside content/", param_hint="--out")

        calls: list[CallRecord] = []
        llm = LLMClient(listeners=[calls.append])

        async def run() -> list[Npc]:
            npcs = []
            async for npc in generate(llm, count, seed, model=model, rich=rich_brief):
                typer.echo(f"{npc.home}: {npc.name} ({npc.id}), {npc.age}, {npc.occupation}")
                npcs.append(npc)
            return npcs

        npcs = asyncio.run(run())
        directory = out or NPCS_DIR
        write_npcs(npcs, directory, seed, briefs=plan(count, seed, rich=True) if rich_brief else ())
        typer.echo(f"Wrote {len(npcs)} NPCs to {directory} with {len(calls)} Claude calls")

    npc = typer.Typer(no_args_is_help=True, help="The village's residents.")

    @npc.command()
    def crafts(
        npcs: Annotated[
            list[str] | None, typer.Argument(help="Resident ids. Defaults to all of them.")
        ] = None,
        directory: Annotated[
            Path | None, typer.Option("--dir", help="Defaults to the repo's content/npcs/.")
        ] = None,
        model: Annotated[str, typer.Option(help="Claude model that chooses them.")] = "sonnet",
    ) -> None:
        """Choose each resident's craft with Claude, leaving everything else about them as it is."""
        import asyncio

        from simile.llm import CallRecord, LLMClient
        from simile.npc.content import NPCS_DIR, load_npcs, readme_seed, write_npcs
        from simile.npc.crafts import add_crafts
        from simile.npc.generate import craft_label
        from simile.schema import Npc

        directory = directory or NPCS_DIR
        seed = readme_seed(directory)
        cast = load_npcs(directory)
        chosen = set(npcs or (npc.id for npc in cast))
        if unknown := sorted(chosen - {npc.id for npc in cast}):
            raise typer.BadParameter(f"no such resident: {', '.join(unknown)}", param_hint="NPCS")
        todo = [npc for npc in cast if npc.id in chosen]
        others = [npc for npc in cast if npc.id not in chosen]
        calls: list[CallRecord] = []
        llm = LLMClient(listeners=[calls.append])

        async def run() -> list[Npc]:
            crafted = []
            async for npc, why in add_crafts(llm, todo, others=others, model=model):
                typer.echo(f"{npc.id}: {craft_label(npc.craft)}. {why}")
                crafted.append(npc)
            return crafted

        crafted = asyncio.run(run())
        write_npcs([*others, *crafted], directory, seed)
        count = sum(npc.craft is not None for npc in crafted)
        typer.echo(
            f"Gave {count} of {len(crafted)} NPCs a craft in {directory} "
            f"with {len(calls)} Claude calls"
        )

    app.add_typer(npc, name="npc")
