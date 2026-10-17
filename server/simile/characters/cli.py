from pathlib import Path
from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    characters = typer.Typer(no_args_is_help=True, help="The character library.")

    @characters.command()
    def generate(
        count: Annotated[int, typer.Option(help="How many characters the pool should have.")] = 20,
        seed: Annotated[int, typer.Option(help="Seeds everything sampled in code.")] = 0,
        out: Annotated[
            Path | None, typer.Option(help="Defaults to the repo's content/characters/pool/.")
        ] = None,
        model: Annotated[str, typer.Option(help="Claude model that writes them.")] = "haiku",
        max_calls: Annotated[
            int | None, typer.Option(help="Stop starting characters at this many Claude calls.")
        ] = None,
    ) -> None:
        """Generate premade characters, skipping any already written."""
        import asyncio
        from collections import Counter

        from simile.characters.novelty import LocalEmbedder
        from simile.characters.pool import POOL_DIR, generate_pool
        from simile.llm import CallRecord, LLMClient

        directory = out or POOL_DIR
        content = POOL_DIR.parents[1]
        resolved = directory.resolve()
        if resolved.is_relative_to(content) and not resolved.is_relative_to(POOL_DIR):
            raise typer.BadParameter("must be content/characters/pool/ or outside content/")
        if count < 1:
            raise typer.BadParameter("must be at least 1", param_hint="--count")

        calls: list[CallRecord] = []

        def called(record: CallRecord) -> None:
            calls.append(record)
            typer.echo(
                f"  Claude call {len(calls)}: {record.purpose}, {record.latency_ms / 1000:.0f}s"
            )

        llm = LLMClient(listeners=[called])
        run = asyncio.run(
            generate_pool(
                llm,
                count,
                seed,
                directory,
                embedder=LocalEmbedder(),
                calls=calls,
                max_calls=max_calls,
                model=model,
                echo=typer.echo,
            )
        )

        def tally(counts: Counter[str]) -> str:
            return ", ".join(f"{n} {name}" for name, n in counts.most_common()) or "none"

        models = Counter((c.usage.model if c.usage and c.usage.model else c.model) for c in calls)
        typer.echo(
            f"Wrote {len(run.written)} characters to {directory}, skipped {len(run.skipped)} "
            f"already there, {len(run.failed)} failed, {run.unstarted} not started. "
            f"Claude calls: {tally(models)} ({tally(Counter(c.purpose for c in calls))})."
        )

    app.add_typer(characters, name="characters")
