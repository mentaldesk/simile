from pathlib import Path
from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    cafe = typer.Typer(no_args_is_help=True, help="The Daily Grind.")

    @cafe.command()
    def barista(
        seed: Annotated[int, typer.Option(help="Seeds their values, age and gender.")] = 0,
        directory: Annotated[
            Path | None, typer.Option("--dir", help="Defaults to the repo's content/npcs/.")
        ] = None,
        model: Annotated[str, typer.Option(help="Claude model that writes them.")] = "sonnet",
    ) -> None:
        """Generate the café's barista with N1's prompt and add them to the residents."""
        import asyncio

        from simile.cafe.barista import HOME, generate_barista
        from simile.llm import CallRecord, LLMClient
        from simile.npc import NPCS_DIR, load_npcs

        directory = directory or NPCS_DIR
        others = load_npcs(directory)
        if taken := [npc.id for npc in others if npc.home == HOME]:
            raise typer.BadParameter(f"{taken[0]} already lives above the café", param_hint="--dir")
        calls: list[CallRecord] = []
        llm = LLMClient(listeners=[calls.append])
        npc = asyncio.run(generate_barista(llm, others, seed, model=model))
        path = directory / f"{npc.id}.json"
        path.write_text(npc.model_dump_json(indent=2) + "\n", encoding="utf-8")
        typer.echo(f"{npc.name} ({npc.id}), {npc.age}: {npc.persona}")
        typer.echo(f"Wrote {path} with {len(calls)} Claude calls")

    app.add_typer(cafe, name="cafe")
