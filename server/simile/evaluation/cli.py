from pathlib import Path
from typing import Annotated

import typer

LOCAL = "ollama:gemma4:26b"


def register(app: typer.Typer) -> None:
    evaluate = typer.Typer(no_args_is_help=True, help="Measure how characters behave.")

    @evaluate.command()
    def characters(
        sample: Annotated[
            int, typer.Option(help="How many characters to draw from the pool.")
        ] = 10,
        seed: Annotated[int, typer.Option(help="Seeds the draw.")] = 0,
        pick: Annotated[
            str | None, typer.Option(help="Character ids to use instead, comma-separated.")
        ] = None,
        pool: Annotated[
            Path | None, typer.Option(help="Defaults to the repo's content/characters/pool/.")
        ] = None,
        out: Annotated[
            Path | None,
            typer.Option(
                help="A folder outside content/ for report.md and replies.json. A rerun reuses "
                "the replies there. Without it the report goes to stdout."
            ),
        ] = None,
        claude: Annotated[
            bool,
            typer.Option(
                help="Call Claude through L1. Without it, stock replies stand in and nothing "
                "is called."
            ),
        ] = False,
        model: Annotated[
            str | None,
            typer.Option(
                help="Model for the replies, e.g. ollama:gemma4:26b for a local one. Defaults "
                "to B5's."
            ),
        ] = None,
        judge: Annotated[
            str, typer.Option(help="Model that labels the stances, in one call.")
        ] = "claude-haiku-5-5",
        max_calls: Annotated[
            int | None,
            typer.Option(
                help="Most reply calls to start. Defaults to one per character and scenario."
            ),
        ] = None,
        scenarios: Annotated[
            str | None,
            typer.Option(
                help="Scenario ids to play, comma-separated, 'tempting' for those with "
                "something to lie about, or 'pushback' for those where the player pushes. "
                "Defaults to all."
            ),
        ] = None,
        lies: Annotated[
            bool,
            typer.Option(help="Roll for lies. Without it, nobody is directed to lie."),
        ] = True,
        humour: Annotated[
            bool,
            typer.Option(
                help="Give the prompts each character's humour. A character without one is "
                "given one as casting would, seeded by --seed, which the report shows either way."
            ),
        ] = True,
        reuse: Annotated[
            Path | None,
            typer.Option(
                help="Another run's folder whose replies to the same prompts are reused, "
                "without counting its calls."
            ),
        ] = None,
    ) -> None:
        """Play fixed scenarios for a sample of characters and report how differently they
        reply."""
        import asyncio
        import os

        from simile.casting.humour import humoured
        from simile.characters.novelty import LocalEmbedder
        from simile.characters.pool import POOL_DIR, load_pool
        from simile.conversation.config import ConversationConfig
        from simile.conversation.player import PlayerConfig
        from simile.evaluation.fake import STOCK, Stock
        from simile.evaluation.report import Run
        from simile.evaluation.run import MAX_WITH_CLAUDE, Refused, choose, evaluate, played
        from simile.llm import CallRecord, FakeProvider, LLMClient
        from simile.llm.lifespan import FAKE_ENV

        directory = pool or POOL_DIR
        picks = [id.strip() for id in pick.split(",") if id.strip()] if pick else []
        try:
            chosen = humoured(choose(load_pool(directory), sample, seed, picks), seed)
            playing = played(scenarios)
        except Refused as e:
            raise typer.BadParameter(str(e)) from e
        fake = os.environ.get(FAKE_ENV) == "fake"
        calling = claude and not fake
        if calling and len(chosen) > MAX_WITH_CLAUDE:
            raise typer.BadParameter(
                f"at most {MAX_WITH_CLAUDE} characters with --claude, not {len(chosen)}"
            )
        if claude and fake:
            typer.echo(f"{FAKE_ENV}=fake, so stock replies stand in for Claude.", err=True)
        model = (model or PlayerConfig().model) if calling else STOCK
        judge = judge if calling else STOCK
        limit = len(chosen) * len(playing) if max_calls is None else max_calls
        config = ConversationConfig() if lies else ConversationConfig(lie_most=0)

        def called(record: CallRecord) -> None:
            if calling:
                typer.echo(
                    f"  {record.provider} call: {record.purpose}, {record.latency_ms / 1000:.1f}s"
                    + (f", {record.error}" if record.error else ""),
                    err=True,
                )

        llm = LLMClient(None if calling else FakeProvider(default=Stock()), listeners=[called])
        drawn = ", ".join(picks) if picks else f"{len(chosen)} drawn with seed {seed}"

        def run(calls: int) -> Run:
            return Run(pool=shown(directory), sample=drawn, model=model, judge=judge, calls=calls)

        try:
            result = asyncio.run(
                evaluate(
                    llm,
                    chosen,
                    LocalEmbedder(),
                    model=model,
                    judge=judge,
                    run=run,
                    out=out,
                    max_calls=limit,
                    scenarios=playing,
                    reuse=reuse,
                    config=config,
                    humour=humour,
                )
            )
        except Refused as e:
            raise typer.BadParameter(str(e), param_hint="--out") from e
        if result.report is None:
            typer.echo(
                f"{result.missing} replies missing, so no report. Rerun with the same --out to "
                "finish.",
                err=True,
            )
            raise typer.Exit(1)
        if out is None:
            typer.echo(result.report)
        else:
            typer.echo(f"Wrote {out / 'report.md'}", err=True)
        if calling:
            typer.echo(f"Claude calls: {result.calls}", err=True)

    @evaluate.command()
    def suspects(
        seeds: Annotated[
            str | None,
            typer.Option(
                help="Seeds of S12's incidents, comma-separated. Defaults to four whose liars "
                "give every kind of cover."
            ),
        ] = None,
        models: Annotated[
            str | None,
            typer.Option(help=f"Models to compare, comma-separated. Defaults to B5's and {LOCAL}."),
        ] = None,
        claude: Annotated[
            bool,
            typer.Option(
                help="Call the models and Claude's judge through L1. Without it, stock replies "
                "stand in and nothing is called."
            ),
        ] = False,
        judge: Annotated[
            str, typer.Option(help="Model that labels the replies and scores their character.")
        ] = "claude-haiku-5-5",
        write: Annotated[
            bool,
            typer.Option(
                help="Have Sonnet write each incident's covers, one call a seed, as for a new "
                "world. Without it they're the content's templates."
            ),
        ] = False,
        out: Annotated[
            Path | None,
            typer.Option(
                help="A folder outside content/ for report.md, replies.json and backstories.json. "
                "A rerun reuses what's there. Without it the report goes to stdout."
            ),
        ] = None,
        max_calls: Annotated[
            int | None, typer.Option(help="Most reply calls to start, for every model together.")
        ] = None,
    ) -> None:
        """Compare how models voice the incident's liars."""
        import asyncio
        import os

        from simile.conversation.player import PlayerConfig
        from simile.conversation.prompt import first_name
        from simile.evaluation.fake import STOCK, Stock
        from simile.evaluation.run import Refused
        from simile.evaluation.suspects import SEEDS
        from simile.evaluation.suspects_report import report
        from simile.evaluation.suspects_run import REPORT, compare
        from simile.llm import FakeProvider, LLMClient
        from simile.llm.lifespan import FAKE_ENV
        from simile.npc import load_npcs
        from simile.npc.content import NPCS_DIR

        try:
            drawn = [int(seed) for seed in seeds.split(",") if seed.strip()] if seeds else SEEDS
        except ValueError as e:
            raise typer.BadParameter(f"not a list of seeds: {seeds}", param_hint="--seeds") from e
        named = [m.strip() for m in (models or "").split(",") if m.strip()]
        named = named or [PlayerConfig().model, LOCAL]
        fake = os.environ.get(FAKE_ENV) == "fake"
        calling = claude and not fake
        if claude and fake:
            typer.echo(f"{FAKE_ENV}=fake, so stock replies stand in for Claude.", err=True)
        if not calling:
            named, judge = [f"{STOCK}/{model}" for model in named], STOCK
        llm = LLMClient(None if calling else FakeProvider(default=Stock()))
        npcs = load_npcs(NPCS_DIR)
        try:
            result = asyncio.run(
                compare(
                    llm,
                    npcs,
                    models=named,
                    judge=judge,
                    seeds=drawn,
                    out=out,
                    write=write,
                    max_calls=max_calls,
                )
            )
        except Refused as e:
            raise typer.BadParameter(str(e), param_hint="--out") from e
        if result.missing:
            typer.echo(
                f"{result.missing} replies missing, so no report. Rerun with the same --out to "
                "finish.",
                err=True,
            )
            raise typer.Exit(1)
        residents = [first_name(npc) for npc in npcs]
        text = report(result, named, judge, residents, stock=not calling)
        if out is None:
            typer.echo(text)
        else:
            (out / REPORT).write_text(text, encoding="utf-8")
            typer.echo(f"Wrote {out / REPORT}", err=True)
        if calling:
            typer.echo(f"Claude calls: {result.calls}", err=True)

    app.add_typer(evaluate, name="evaluate")


def shown(path: Path) -> str:
    """`path` from the repo's root when it's inside it."""
    root = Path(__file__).resolve().parents[3]
    resolved = path.resolve()
    return str(resolved.relative_to(root)) if resolved.is_relative_to(root) else str(path)
