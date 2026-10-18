import functools
from collections.abc import Awaitable, Callable
from typing import Self

from pydantic import Field, TypeAdapter, ValidationError, model_validator
from pydantic_core import PydanticCustomError
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import BaseRoute, Route

from simile.guard import accepts
from simile.jobs import Busy, Jobs, jobs_of
from simile.library import Library, NotFound, ReadOnly, Refused, library_of
from simile.library.archive import reasons
from simile.schema import Character, Id, Model
from simile.voice.service import voice_of
from simile.voicelib import kinds, uploads, voices
from simile.voicelib.speech import speaker_of

MAX_JSON = 4 * 1024
TRANSCRIPT = TypeAdapter(kinds.Line)
UNVOICED = (
    "Try it needs the voice model, so start the server with SIMILE_VOICE=1 on a Mac with Apple "
    "Silicon (see server/simile/voice/README.md)"
)

type Endpoint = Callable[[Request], Awaitable[Response]]


class TooLarge(Exception):
    pass


class Pick(Model):
    design: str | None = Field(default=None, pattern=f"^{kinds.JOB}$")
    candidate: int | None = Field(default=None, ge=1, le=kinds.MAX_CANDIDATES)
    recording: str | None = Field(default=None, pattern=f"^{kinds.JOB}$")
    library: Id | None = None

    @model_validator(mode="after")
    def _one_voice(self) -> Self:
        if sum(way is not None for way in (self.design, self.recording, self.library)) != 1:
            raise PydanticCustomError("pick", "Pick one of design, recording or library")
        if (self.design is None) != (self.candidate is None):
            raise PydanticCustomError(
                "pick", "Only a designed voice has a candidate, and it needs one"
            )
        return self


class Line(Model):
    line: kinds.Spoken = Field(max_length=300)


def problem(status: int, error: str) -> JSONResponse:
    return JSONResponse({"error": error}, status_code=status)


def guarded(endpoint: Endpoint) -> Endpoint:
    @functools.wraps(endpoint)
    async def respond(request: Request) -> Response:
        try:
            return await endpoint(request)
        except NotFound:
            return problem(404, "No such character")
        except (kinds.Missing, voices.UnknownVoice) as error:
            return problem(404, str(error))
        except ReadOnly as error:
            return problem(403, str(error))
        except TooLarge as error:
            return problem(413, str(error))
        except uploads.Unsupported as error:
            return problem(415, str(error))
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
            raise TooLarge(f"That can be at most {limit // 1024} KB")
    return bytes(data)


def own(library: Library, id: str) -> Character:
    character = library.get(id)
    if library.is_premade(id):
        raise ReadOnly("Premade characters are read-only")
    return character


def chosen(jobs: Jobs, choice: Pick) -> tuple[bytes, str]:
    """The clip that was picked, and what it says."""
    if choice.library is not None:
        return voices.clip_path(choice.library).read_bytes(), voices.transcript(choice.library)
    if choice.recording is not None:
        return kinds.recorded(jobs, choice.recording)
    assert choice.design is not None and choice.candidate is not None
    return kinds.designed(jobs, choice.design, choice.candidate)


def set_voice(library: Library, id: str, clip: bytes, line: str) -> Character:
    """Gives the character `clip` as its reference clip, with `line`, what it says."""
    character = library.save_clip(id, clip)
    if character.voice.reference_line == line:
        return character
    data = character.model_dump(mode="json")
    data["voice"]["reference_line"] = line
    return library.update(id, data)


@guarded
async def listing(request: Request) -> Response:
    found = await run_in_threadpool(voices.voices)
    return JSONResponse([voice.model_dump(mode="json") for voice in found])


@guarded
async def library_clip(request: Request) -> Response:
    path = await run_in_threadpool(voices.clip_path, request.path_params["id"])
    return FileResponse(path, media_type="audio/wav")


@accepts("audio/wav", "audio/mpeg", "audio/mp4")
@guarded
async def record(request: Request) -> Response:
    library, jobs = library_of(request.app), jobs_of(request.app)
    character = await run_in_threadpool(own, library, request.path_params["id"])
    kind = jobs.capabilities()["kinds"].get(kinds.CHECK)
    if kind is None or not kind["available"]:
        return problem(503, kind["reason"] if kind else "This server can't check recordings")
    said = request.query_params.get("transcript", character.voice.reference_line)
    line = TRANSCRIPT.validate_python(said)
    data = await body(request, uploads.MAX_UPLOAD)
    found = await run_in_threadpool(uploads.check, data)
    path = await run_in_threadpool(uploads.store, kinds.uploads_dir(jobs.root), data, found)
    params = {"upload": path.name, "reference_line": line}
    try:
        job = jobs.submit(kinds.CHECK, params)
    except Busy as error:
        path.unlink(missing_ok=True)
        return problem(429, str(error))
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    uploads.waiting_of(request.app).add(jobs, job.id, path)
    return JSONResponse(job.model_dump(mode="json"), status_code=202)


@guarded
async def pick(request: Request) -> Response:
    library, jobs = library_of(request.app), jobs_of(request.app)
    id = request.path_params["id"]
    choice = Pick.model_validate_json(await body(request))
    await run_in_threadpool(own, library, id)
    clip, line = await run_in_threadpool(chosen, jobs, choice)
    character = await run_in_threadpool(set_voice, library, id, clip, line)
    return JSONResponse(character.model_dump(mode="json"))


@guarded
async def try_it(request: Request) -> Response:
    voice = voice_of(request.app)
    if voice is None:
        return problem(503, UNVOICED)
    asked = Line.model_validate_json(await body(request))
    library = library_of(request.app)
    character = await run_in_threadpool(library.get, request.path_params["id"])
    clip = library.clip(character)
    if clip is None or not clip.is_file():
        return problem(409, f"{character.name} has no voice yet")
    audio = await speaker_of(request.app).say(voice, character, clip, asked.line)
    return Response(audio, media_type="audio/wav")


routes: list[BaseRoute] = [
    Route("/api/voices", listing, methods=["GET"]),
    Route("/api/voices/{id}/clip", library_clip, methods=["GET"]),
    Route("/api/characters/{id}/voice/recording", record, methods=["POST"]),
    Route("/api/characters/{id}/voice/pick", pick, methods=["POST"]),
    Route("/api/characters/{id}/voice/try", try_it, methods=["POST"]),
]
