from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    story = typer.Typer(help="Aris and the incident.", no_args_is_help=True)

    @story.command()
    def incident(
        seed: Annotated[int | None, typer.Option(help="Seed for who attacks and who saw.")] = None,
        facts: Annotated[bool, typer.Option(help="List the facts and who knows them.")] = False,
    ) -> None:
        """Make and print an incident as a new world would, with one Sonnet call, saving nothing."""
        import asyncio
        import logging
        import os
        import random
        from datetime import UTC, datetime

        from simile.llm import LLMClient
        from simile.llm.lifespan import FAKE_ENV, CannedProvider
        from simile.npc import load_npcs
        from simile.story.incident import make_incident

        logging.basicConfig(level=logging.INFO, format="%(message)s")
        llm = LLMClient(CannedProvider() if os.environ.get(FAKE_ENV) == "fake" else None)
        now = datetime.now(UTC)
        made = asyncio.run(make_incident(load_npcs(), now, llm, rng=random.Random(seed)))
        found = made.incident
        typer.echo(f"Attackers: {', '.join(found.attackers)}")
        typer.echo(f"Motive{'' if made.written else ' (from templates)'}: {found.motive}")
        if facts:
            for fact in found.facts:
                knowers = ", ".join(
                    f"{k.id} ({k.how}, tells from {k.tells_from}, cover {k.cover!r})"
                    for k in fact.known_by
                )
                typer.echo(f"\n{fact.id}: {fact.what}\n  known by: {knowers or 'nobody'}")
                for lead in fact.leads:
                    typer.echo(f"  -> {lead.fact_id}: {lead.text}")

    app.add_typer(story, name="story")
