from typing import Annotated

import typer

from simile import submodules


def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: Annotated[bool, typer.Option(help="Restart when the code changes.")] = False,
) -> None:
    """Run the sim server."""
    import uvicorn

    uvicorn.run("simile.app:create_app", factory=True, host=host, port=port, reload=reload)


def about() -> None:
    """Simile: a village of LLM-driven NPCs."""


def create_cli(package: str = "simile") -> typer.Typer:
    cli = typer.Typer(no_args_is_help=True)
    cli.callback()(about)
    cli.command()(serve)
    for module in submodules("cli", package):
        module.register(cli)
    return cli


def main() -> None:
    create_cli()()
