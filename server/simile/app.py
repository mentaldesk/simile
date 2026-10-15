from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

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
    module_lifespans = [module.lifespan for module in submodules("lifespan", package)]

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            for module_lifespan in module_lifespans:
                await stack.enter_async_context(module_lifespan(app))
            yield

    return Starlette(routes=routes, lifespan=lifespan)
