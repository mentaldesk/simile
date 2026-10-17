from typing import Any

import anyio
from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import BaseRoute, Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from simile.jobs.runner import Busy, Finished, Job, UnknownKind, jobs_of
from simile.schema import Model

MAX_BODY = 64 * 1024


class Submission(Model):
    kind: str
    params: dict[str, Any] = {}


def problem(status: int, error: str) -> JSONResponse:
    return JSONResponse({"error": error}, status_code=status)


def invalid(error: ValidationError) -> JSONResponse:
    reasons = (
        f"{'.'.join(map(str, e['loc']))}: {e['msg']}" if e["loc"] else e["msg"]
        for e in error.errors(include_url=False)
    )
    return problem(422, "; ".join(reasons))


def job_json(job: Job, status: int = 200) -> JSONResponse:
    return JSONResponse(job.model_dump(mode="json"), status_code=status)


def capabilities(request: Request) -> JSONResponse:
    return JSONResponse(jobs_of(request.app).capabilities())


def listing(request: Request) -> JSONResponse:
    return JSONResponse([job.model_dump(mode="json") for job in jobs_of(request.app).list()])


async def submit(request: Request) -> JSONResponse:
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BODY:
            return problem(413, f"A job request can be at most {MAX_BODY // 1024} KB")
    try:
        submission = Submission.model_validate_json(body)
        job = jobs_of(request.app).submit(submission.kind, submission.params)
    except ValidationError as error:
        return invalid(error)
    except UnknownKind as error:
        return problem(422, str(error))
    except Busy as error:
        return problem(429, str(error))
    return job_json(job, 202)


def status(request: Request) -> JSONResponse:
    job = jobs_of(request.app).get(request.path_params["job_id"])
    return problem(404, "No such job") if job is None else job_json(job)


async def cancel(request: Request) -> JSONResponse:
    try:
        return job_json(await jobs_of(request.app).cancel(request.path_params["job_id"]))
    except KeyError:
        return problem(404, "No such job")
    except Finished as error:
        return problem(409, str(error))


def published(request: Request) -> Response:
    path = jobs_of(request.app).file(request.path_params["kind"], request.path_params["name"])
    if path is None:
        return Response(status_code=404)
    return FileResponse(path, headers={"Cache-Control": "no-cache"})


async def watch(websocket: WebSocket) -> None:
    """Sends the job as JSON now and after each change, then closes once it has finished.
    Closing early leaves the job running."""
    jobs, job_id = jobs_of(websocket.app), websocket.path_params["job_id"]
    await websocket.accept()
    if jobs.get(job_id) is None:
        await websocket.close(code=4404, reason="No such job")
        return
    async with anyio.create_task_group() as group:

        async def send() -> None:
            try:
                async for job in jobs.watch(job_id):
                    await websocket.send_json(job.model_dump(mode="json"))
                await websocket.close()
            except WebSocketDisconnect:
                pass
            group.cancel_scope.cancel()

        group.start_soon(send)
        while (await websocket.receive())["type"] != "websocket.disconnect":
            pass
        group.cancel_scope.cancel()


routes: list[BaseRoute] = [
    Route("/api/jobs/capabilities", capabilities),
    Route("/api/jobs", listing, methods=["GET"]),
    Route("/api/jobs", submit, methods=["POST"]),
    Route("/api/jobs/files/{kind}/{name}", published),
    Route("/api/jobs/{job_id}", status),
    Route("/api/jobs/{job_id}/cancel", cancel, methods=["POST"]),
    WebSocketRoute("/ws/jobs/{job_id}", watch),
]
