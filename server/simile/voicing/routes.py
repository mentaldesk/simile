import re

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import BaseRoute, Route

from simile.library import library_of
from simile.voicing.greetings import found

ID = re.compile(r"[a-z][a-z0-9_]{0,63}")


async def listing(request: Request) -> Response:
    id = request.path_params["id"]
    if not ID.fullmatch(id):
        return JSONResponse({"greetings": []})
    paths = await run_in_threadpool(found, id, library_of(request.app))
    return JSONResponse({"greetings": [f"/api/greetings/{id}/{path.name}" for path in paths]})


async def greeting(request: Request) -> Response:
    id, name = request.path_params["id"], request.path_params["name"]
    paths = await run_in_threadpool(found, id, library_of(request.app)) if ID.fullmatch(id) else []
    path = next((path for path in paths if path.name == name), None)
    if path is None:
        return JSONResponse({"error": "No such greeting"}, status_code=404)
    return FileResponse(path, media_type="audio/mp4")


routes: list[BaseRoute] = [
    Route("/api/greetings/{id}", listing, methods=["GET"]),
    Route("/api/greetings/{id}/{name}", greeting, methods=["GET"]),
]
