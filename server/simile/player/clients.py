import asyncio


class InGame:
    """The clients in the game: those that have sent a player position since connecting."""

    def __init__(self) -> None:
        self._clients: set[asyncio.Task[object]] = set()

    def moved(self, message: object) -> None:
        # The hub hands each client's messages to subscribers on that client's own task.
        if (client := asyncio.current_task()) is not None:
            self._clients.add(client)

    def __bool__(self) -> bool:
        self._clients = {client for client in self._clients if not client.done()}
        return bool(self._clients)
