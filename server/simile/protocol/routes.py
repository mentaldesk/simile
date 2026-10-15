from starlette.routing import BaseRoute, WebSocketRoute
from starlette.websockets import WebSocket

from simile.protocol.hub import hub_of


async def connect(websocket: WebSocket) -> None:
    await hub_of(websocket.app).serve(websocket)


routes: list[BaseRoute] = [WebSocketRoute("/ws", connect)]
