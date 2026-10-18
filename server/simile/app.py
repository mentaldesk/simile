from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

from simile import submodules
from simile.guard import Guard


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def create_app(package: str = "simile") -> Starlette:
    routes: list[BaseRoute] = [Route("/api/health", health)]
    for module in submodules("routes", package):
        routes.extend(module.routes)
    modules = list(submodules("lifespan", package))
    hooks = [
        getattr(module, hook)
        for hook in ("lifespan", "running")
        for module in modules
        if hasattr(module, hook)
    ]

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            for hook in hooks:
                await stack.enter_async_context(hook(app))
            yield

    return Starlette(routes=routes, lifespan=lifespan, middleware=[Middleware(Guard)])
