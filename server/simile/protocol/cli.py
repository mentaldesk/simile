import typer


def register(app: typer.Typer) -> None:
    @app.command()
    def protocol() -> None:
        """Export JSON Schema for the client-server messages, for client/src/net/protocol.ts."""
        from simile.protocol.export import write

        write()
