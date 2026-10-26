from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    worlds = typer.Typer(no_args_is_help=True, help="The worlds the server can run.")

    @worlds.command()
    def serve(
        host: str = "127.0.0.1",
        port: int = 8000,
        reload: Annotated[bool, typer.Option(help="Restart when the code changes.")] = False,
    ) -> None:
        """Run the sim server on the last world played, and on another when the menu opens it."""
        import logging

        from simile.worlds.store import Worlds, default_root
        from simile.worlds.supervisor import Supervisor, server_command

        logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(message)s")
        supervisor = Supervisor(server_command(host, port, reload), Worlds(default_root()))
        raise typer.Exit(supervisor.run())

    app.add_typer(worlds, name="worlds")
