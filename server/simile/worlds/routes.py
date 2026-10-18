import functools
from collections.abc import Awaitable, Callable

from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute, Route

from simile.casting import CastError, CastRefused
from simile.worlds.store import NewWorld, current, houses, worlds_of

MAX_BODY = 16 * 1024

type Endpoint = Callable[[Request], Awaitable[Response]]


class TooLarge(Exception):
    pass


def problem(status: int, error: str) -> JSONResponse:
    return JSONResponse({"error": error}, status_code=status)


def guarded(endpoint: Endpoint) -> Endpoint:
    @functools.wraps(endpoint)
    async def respond(request: Request) -> Response:
        try:
            return await endpoint(request)
        except TooLarge as error:
            return problem(413, str(error))
        except ValidationError as error:
            return problem(422, _reasons(error))
        except CastRefused as error:
            return problem(409, str(error))
        except CastError as error:
            return problem(422, str(error))

    return respond


async def asked(request: Request) -> NewWorld:
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > MAX_BODY:
            raise TooLarge(f"The request can be at most {MAX_BODY // 1024} KB")
    return NewWorld.model_validate_json(bytes(data))


@guarded
async def listing(request: Request) -> Response:
    running = await run_in_threadpool(current)
    count = await run_in_threadpool(houses)
    return JSONResponse({"current": running.model_dump(mode="json"), "houses": count})


@guarded
async def draw(request: Request) -> Response:
    from simile.library import library_of

    new = await asked(request)
    worlds, library = worlds_of(request.app), library_of(request.app)
    return JSONResponse({"residents": await run_in_threadpool(worlds.draw, new, library)})


@guarded
async def create(request: Request) -> Response:
    from simile.library import library_of

    new = await asked(request)
    worlds, library = worlds_of(request.app), library_of(request.app)
    made = await run_in_threadpool(worlds.create, new, library)
    return JSONResponse(made.model_dump(mode="json"), status_code=201)


def _reasons(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(map(str, e['loc']))}: {e['msg']}" if e["loc"] else e["msg"]
        for e in error.errors(include_url=False)
    )


routes: list[BaseRoute] = [
    Route("/api/worlds", listing, methods=["GET"]),
    Route("/api/worlds", create, methods=["POST"]),
    Route("/api/worlds/draw", draw, methods=["POST"]),
]
