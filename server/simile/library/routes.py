import functools
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import aclosing
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError
from pydantic_core import from_json
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import BaseRoute, Route
from starlette.types import Receive, Scope, Send

from simile.guard import accepts
from simile.library.archive import MAX_FILE, Refused, reasons
from simile.library.store import Library, NotFound, PlayerLook, ReadOnly, library_of
from simile.schema import Character, CharacterSource

if TYPE_CHECKING:
    from simile.library.generation import Work

MAX_JSON = 256 * 1024

type Endpoint = Callable[[Request], Awaitable[Response]]


class TooLarge(Exception):
    pass


class EventStream(StreamingResponse):
    """Generation events, holding one of the library's slots until the response ends."""

    media_type = "application/x-ndjson"

    def __init__(self, events: AsyncIterator[str], library: Library) -> None:
        super().__init__(events)
        library.generating += 1
        self.library = library

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.library.generating -= 1

    async def stream_response(self, send: Send) -> None:
        async with aclosing(self.body_iterator):
            await super().stream_response(send)


def problem(status: int, error: str) -> JSONResponse:
    return JSONResponse({"error": error}, status_code=status)


def guarded(endpoint: Endpoint) -> Endpoint:
    @functools.wraps(endpoint)
    async def respond(request: Request) -> Response:
        try:
            return await endpoint(request)
        except NotFound:
            return problem(404, "No such character")
        except ReadOnly as error:
            return problem(403, str(error))
        except TooLarge as error:
            return problem(413, str(error))
        except Refused as error:
            return problem(422, str(error))
        except ValidationError as error:
            return problem(422, reasons(error))

    return respond


async def body(request: Request, limit: int = MAX_JSON) -> bytes:
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > limit:
            raise TooLarge(f"The request can be at most {limit // 1024} KB")
    return bytes(data)


async def json_object(request: Request) -> dict[str, Any]:
    try:
        data = from_json(await body(request))
    except ValueError as error:
        raise Refused(f"The request isn't JSON: {error}") from None
    if not isinstance(data, dict):
        raise Refused("The request must be a JSON object")
    return data


def character_json(character: Character, status: int = 200) -> JSONResponse:
    headers = {"Location": f"/api/characters/{character.id}"} if status == 201 else None
    return JSONResponse(character.model_dump(mode="json"), status_code=status, headers=headers)


@guarded
async def listing(request: Request) -> Response:
    characters = await run_in_threadpool(library_of(request.app).characters)
    return JSONResponse([character.model_dump(mode="json") for character in characters])


@guarded
async def create(request: Request) -> Response:
    data = await json_object(request)
    return character_json(await run_in_threadpool(library_of(request.app).create, data), 201)


@guarded
async def one(request: Request) -> Response:
    id = request.path_params["id"]
    return character_json(await run_in_threadpool(library_of(request.app).get, id))


@guarded
async def update(request: Request) -> Response:
    id, data = request.path_params["id"], await json_object(request)
    return character_json(await run_in_threadpool(library_of(request.app).update, id, data))


@accepts(None)
@guarded
async def delete(request: Request) -> Response:
    await run_in_threadpool(library_of(request.app).delete, request.path_params["id"])
    return Response(status_code=204)


@guarded
async def export(request: Request) -> Response:
    id = request.path_params["id"]
    data = await run_in_threadpool(library_of(request.app).export, id)
    headers = {"Content-Disposition": f'attachment; filename="{id}.zip"'}
    return Response(data, media_type="application/zip", headers=headers)


@accepts("application/zip")
@guarded
async def import_file(request: Request) -> Response:
    data = await body(request, MAX_FILE)
    return character_json(await run_in_threadpool(library_of(request.app).import_file, data), 201)


@guarded
async def generate(request: Request) -> Response:
    from simile.characters import generate as engine
    from simile.characters.brief import Brief

    brief = Brief.model_validate_json(await body(request))
    brief = brief.model_copy(update={"source": CharacterSource.PLAYER})
    library = library_of(request.app)
    taken = await run_in_threadpool(library.ids)
    return stream(request, lambda llm: engine.generate(llm, brief, taken=taken))


@guarded
async def reroll(request: Request) -> Response:
    from simile.characters import generate as engine
    from simile.library.generation import Reroll

    asked = Reroll.model_validate_json(await body(request))
    character = asked.character
    premade = await run_in_threadpool(library_of(request.app).is_premade, character.id)
    if premade or character.source is CharacterSource.PREMADE:
        raise ReadOnly("Premade characters are read-only")
    return stream(request, lambda llm: engine.reroll(llm, character, *asked.sections))


def stream(request: Request, work: "Work") -> Response:
    from simile.library.generation import MAX_GENERATING, events

    library = library_of(request.app)
    if library.generating >= MAX_GENERATING:
        return problem(429, f"{library.generating} characters are already being written")
    return EventStream(events(library, request.app.state.llm, work), library)


@guarded
async def player(request: Request) -> Response:
    appearance = await run_in_threadpool(library_of(request.app).player)
    return JSONResponse(PlayerLook(appearance=appearance).model_dump(mode="json"))


@guarded
async def save_player(request: Request) -> Response:
    look = PlayerLook.model_validate_json(await body(request))
    await run_in_threadpool(library_of(request.app).save_player, look.appearance)
    return JSONResponse(look.model_dump(mode="json"))


routes: list[BaseRoute] = [
    Route("/api/characters", listing, methods=["GET"]),
    Route("/api/characters", create, methods=["POST"]),
    Route("/api/characters/generate", generate, methods=["POST"]),
    Route("/api/characters/reroll", reroll, methods=["POST"]),
    Route("/api/characters/import", import_file, methods=["POST"]),
    Route("/api/characters/{id}", one, methods=["GET"]),
    Route("/api/characters/{id}", update, methods=["PUT"]),
    Route("/api/characters/{id}", delete, methods=["DELETE"]),
    Route("/api/characters/{id}/export", export, methods=["GET"]),
    Route("/api/player", player, methods=["GET"]),
    Route("/api/player", save_player, methods=["PUT"]),
]
