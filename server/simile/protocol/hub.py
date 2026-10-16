import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from pydantic import BaseModel, ValidationError
from starlette.applications import Starlette
from starlette.websockets import WebSocket

from simile.protocol.audio import AudioChunk
from simile.protocol.fixtures import fixture_snapshot
from simile.protocol.messages import (
    ClockMessage,
    ServerMessage,
    SnapshotMessage,
    client_messages,
)
from simile.sim import world_of

logger = logging.getLogger(__name__)

type Outgoing = ServerMessage | AudioChunk
type Frame = str | bytes


def encode(message: Outgoing) -> Frame:
    return message.encode() if isinstance(message, AudioChunk) else message.model_dump_json()


class Connection:
    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self._frames: asyncio.Queue[Frame] = asyncio.Queue()

    def send(self, message: Outgoing) -> None:
        self.put(encode(message))

    def put(self, frame: Frame) -> None:
        self._frames.put_nowait(frame)

    async def write(self) -> None:
        while True:
            frame = await self._frames.get()
            if isinstance(frame, bytes):
                await self.websocket.send_bytes(frame)
            else:
                await self.websocket.send_text(frame)


class Hub:
    """Every connected client. Call it from the event loop."""

    def __init__(self, snapshot: Callable[[], SnapshotMessage]) -> None:
        self.snapshot = snapshot
        self.clock: Callable[[], ClockMessage] | None = None
        self.connections: set[Connection] = set()
        self._subscribers: list[tuple[type[BaseModel], Callable[[Any], None]]] = []

    def broadcast(self, message: Outgoing) -> None:
        if not self.connections:
            return
        frame = encode(message)
        for connection in self.connections:
            connection.put(frame)

    def subscribe[M: BaseModel](
        self, message_type: type[M], handler: Callable[[M], None]
    ) -> Callable[[], None]:
        subscriber = (message_type, handler)
        self._subscribers.append(subscriber)

        def unsubscribe() -> None:
            with suppress(ValueError):
                self._subscribers.remove(subscriber)

        return unsubscribe

    async def serve(self, websocket: WebSocket) -> None:
        await websocket.accept()
        connection = Connection(websocket)
        connection.send(self.snapshot())
        if self.clock:
            connection.send(self.clock())
        self.connections.add(connection)
        writer = asyncio.create_task(connection.write())
        try:
            while (received := await websocket.receive())["type"] != "websocket.disconnect":
                if (text := received.get("text")) is not None:
                    self.receive(text)
                else:
                    logger.warning("Ignoring a binary frame from a client")
        finally:
            self.connections.discard(connection)
            writer.cancel()
            await asyncio.gather(writer, return_exceptions=True)

    def receive(self, text: str) -> None:
        try:
            message = client_messages.validate_json(text)
        except ValidationError as error:
            logger.warning("Ignoring an invalid client message: %s", error)
            return
        for message_type, handler in tuple(self._subscribers):
            if isinstance(message, message_type):
                try:
                    handler(message)
                except Exception:
                    logger.exception("%r failed to handle %r", handler, message)


def hub_of(app: Starlette) -> Hub:
    if not hasattr(app.state, "hub"):
        app.state.hub = Hub(lambda: fixture_snapshot(world_of(app).clock.now))
    return app.state.hub
