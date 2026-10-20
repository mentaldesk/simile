from typing import Any

from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Route

from simile.schema import Appearance, Id, Model

MAX_BODY = 4 * 1024


class Flat(Model):
    character: Id | None = None
    appearance: Appearance


def problem(status: int, error: str) -> JSONResponse:
    return JSONResponse({"error": error}, status_code=status)


def reasons(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(map(str, e['loc']))}: {e['msg']}" if e["loc"] else e["msg"]
        for e in error.errors(include_url=False)
    )


def draw(asked: Flat) -> dict[str, Any]:
    from simile.dolls.doll import flat_manifest
    from simile.dolls.look import Look

    return flat_manifest(Look.of(asked.appearance, asked.character))


async def flat(request: Request) -> JSONResponse:
    """A flat doll for any `Appearance`, its atlas inline, drawn at once without the painter."""
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BODY:
            return problem(413, f"A doll request can be at most {MAX_BODY // 1024} KB")
    try:
        asked = Flat.model_validate_json(bytes(body))
    except ValidationError as error:
        return problem(422, reasons(error))
    doll = await run_in_threadpool(draw, asked)
    return JSONResponse(doll, headers={"Cache-Control": "no-store"})


routes: list[BaseRoute] = [Route("/api/dolls/flat", flat, methods=["POST"])]
