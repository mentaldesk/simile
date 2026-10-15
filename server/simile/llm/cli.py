from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    @app.command("llm-smoke")
    def llm_smoke(
        prompt: str = "A stranger walks into your coffee shop. Greet them in one sentence.",
        model: str = "haiku",
        runs: Annotated[int, typer.Option(help="Calls to make, one after another.")] = 1,
        session: Annotated[
            bool, typer.Option(help="Send every run to one long-lived Claude Code session.")
        ] = False,
        cli_path: Annotated[
            str | None, typer.Option(help="Claude Code CLI to run. Default: the SDK's bundled one.")
        ] = None,
    ) -> None:
        """Stream a reply through local Claude Code and print latency and time to first token."""
        import asyncio

        from simile.llm.smoke import smoke

        asyncio.run(smoke(prompt, model=model, runs=runs, session=session, cli_path=cli_path))
