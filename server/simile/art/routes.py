import io

from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute, Route

from simile.schema import Appearance, Id, Model

MAX_BODY = 4 * 1024


class Preview(Model):
    character: Id | None = None
    appearance: Appearance


def problem(status: int, error: str) -> JSONResponse:
    return JSONResponse({"error": error}, status_code=status)


def reasons(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(map(str, e['loc']))}: {e['msg']}" if e["loc"] else e["msg"]
        for e in error.errors(include_url=False)
    )


def draw(asked: Preview) -> bytes:
    from simile.art.characters import THREE_QUARTER, sprite_sheet

    sheet = sprite_sheet(asked.appearance, asked.character, THREE_QUARTER)
    png = io.BytesIO()
    sheet.to_image().save(png, "PNG")
    return png.getvalue()


async def preview(request: Request) -> Response:
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BODY:
            return problem(413, f"A preview request can be at most {MAX_BODY // 1024} KB")
    try:
        asked = Preview.model_validate_json(bytes(body))
    except ValidationError as error:
        return problem(422, reasons(error))
    png = await run_in_threadpool(draw, asked)
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})


routes: list[BaseRoute] = [Route("/api/art/preview", preview, methods=["POST"])]
