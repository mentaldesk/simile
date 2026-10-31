from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    story = typer.Typer(help="Aris and her disappearance.", no_args_is_help=True)

    @story.command()
    def disappearance(
        seed: Annotated[int | None, typer.Option(help="Seed for who saw what.")] = None,
        facts: Annotated[bool, typer.Option(help="List the facts and who knows them.")] = False,
    ) -> None:
        """Make and print a disappearance as a new world would, saving nothing."""
        import random
        from datetime import UTC, datetime

        from simile.npc import load_npcs
        from simile.story.disappearance import make_disappearance

        made = make_disappearance(load_npcs(), datetime.now(UTC), rng=random.Random(seed))
        found = made.disappearance
        typer.echo(f"Distrusted by: {', '.join(found.distrusted_by)}")
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
