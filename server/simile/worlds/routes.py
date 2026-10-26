import functools
import os
from collections.abc import Awaitable, Callable

from pydantic import ValidationError
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute, Route

from simile.casting import CastError, CastRefused
from simile.guard import JSON, accepts
from simile.schema import Model
from simile.worlds import supervisor
from simile.worlds.store import (
    Name,
    NewWorld,
    NotFound,
    Refused,
    current,
    houses,
    running,
    worlds_of,
)

MAX_BODY = 16 * 1024

type Endpoint = Callable[[Request], Awaitable[Response]]


class TooLarge(Exception):
    pass


class Renamed(Model):
    name: Name


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
        except NotFound as error:
            return problem(404, str(error))
        except Refused as error:
            return problem(409, str(error))

    return respond


async def body[M: Model](request: Request, model: type[M]) -> M:
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > MAX_BODY:
            raise TooLarge(f"The request can be at most {MAX_BODY // 1024} KB")
    return model.model_validate_json(bytes(data))


async def asked(request: Request) -> NewWorld:
    return await body(request, NewWorld)


@guarded
async def listing(request: Request) -> Response:
    worlds = worlds_of(request.app)
    now = await run_in_threadpool(current, worlds.root)
    count = await run_in_threadpool(houses)
    listed = await run_in_threadpool(worlds.worlds)
    return JSONResponse(
        {
            "current": now.model_dump(mode="json"),
            "houses": count,
            "worlds": [world.model_dump(mode="json") for world in listed],
            "supervised": supervised(),
        }
    )


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
    opening = new.open and supervised()
    if opening:
        await run_in_threadpool(worlds.index.ask, made.id)
    made = made.model_copy(update={"opening": opening})
    return JSONResponse(
        made.model_dump(mode="json"),
        status_code=201,
        background=BackgroundTask(supervisor.switch) if opening else None,
    )


@guarded
async def world(request: Request) -> Response:
    found = await run_in_threadpool(worlds_of(request.app).world, request.path_params["id"])
    return JSONResponse(found.model_dump(mode="json"))


@guarded
async def rename(request: Request) -> Response:
    renamed = await body(request, Renamed)
    worlds = worlds_of(request.app)
    found = await run_in_threadpool(worlds.rename, request.path_params["id"], renamed.name)
    return JSONResponse(found.model_dump(mode="json"))


@guarded
@accepts(None, JSON)
async def delete(request: Request) -> Response:
    await run_in_threadpool(worlds_of(request.app).delete, request.path_params["id"])
    return Response(status_code=204)


@guarded
@accepts(None, JSON)
async def open_world(request: Request) -> Response:
    id, worlds = request.path_params["id"], worlds_of(request.app)
    await run_in_threadpool(worlds.check, id)
    if running(worlds.root) == id:
        return JSONResponse({"id": id, "opening": False})
    if not supervised():
        return problem(409, UNSUPERVISED)
    await run_in_threadpool(worlds.index.ask, id)
    return JSONResponse(
        {"id": id, "opening": True}, status_code=202, background=BackgroundTask(supervisor.switch)
    )


UNSUPERVISED = (
    "This server can't switch worlds because `simile worlds serve` (`make dev`) didn't start it. "
    "Start it that way, or with $SIMILE_DB set to the world's save"
)


def supervised() -> bool:
    return bool(os.environ.get(supervisor.SUPERVISOR_ENV))


def _reasons(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(map(str, e['loc']))}: {e['msg']}" if e["loc"] else e["msg"]
        for e in error.errors(include_url=False)
    )


routes: list[BaseRoute] = [
    Route("/api/worlds", listing, methods=["GET"]),
    Route("/api/worlds", create, methods=["POST"]),
    Route("/api/worlds/draw", draw, methods=["POST"]),
    Route("/api/worlds/{id}", world, methods=["GET"]),
    Route("/api/worlds/{id}", rename, methods=["PATCH"]),
    Route("/api/worlds/{id}", delete, methods=["DELETE"]),
    Route("/api/worlds/{id}/open", open_world, methods=["POST"]),
]
