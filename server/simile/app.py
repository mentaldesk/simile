from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

from simile import submodules


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def create_app(package: str = "simile") -> Starlette:
    routes: list[BaseRoute] = [Route("/api/health", health)]
    for module in submodules("routes", package):
        routes.extend(module.routes)
    return Starlette(routes=routes)
