import asyncio
import io
import json
import zipfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient
from starlette.types import Message

from simile.characters.palette import PLAYER
from simile.library import Library
from simile.library.generation import MAX_GENERATING
from simile.library.routes import EventStream
from simile.llm import FakeProvider, LLMError, Request

from .conftest import LOOK, PREMADE, answer, archive, character, clip, requested

JSON = {"Content-Type": "application/json"}
ZIP = {"Content-Type": "application/zip"}
BIOGRAPHY = {"backstory", "persona", "speaking_style", "interests", "craft"}


def events(client: TestClient, path: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    with client.stream("POST", path, json=payload) as response:
        assert response.status_code == 200, response.read()
        assert response.headers["content-type"].startswith("application/x-ndjson")
        return [json.loads(line) for line in response.iter_lines() if line]


def texts(got: list[dict[str, Any]]) -> list[str]:
    calls: list[str] = []
    for event in got:
        if event["type"] == "call":
            calls.append("")
        elif event["type"] == "text":
            calls[-1] += event["text"]
    return calls


def files(directory: Path) -> list[str]:
    return sorted(str(p.relative_to(directory)) for p in directory.rglob("*") if p.is_file())


def test_lists_premade_then_player_characters(client: TestClient) -> None:
    client.post("/api/characters", json=character(id="zed_ames", name="Zed Ames"))
    client.post("/api/characters", json=character())

    listed = client.get("/api/characters").json()

    assert [(c["id"], c["source"]) for c in listed] == [
        ("tobiah_rennick", "premade"),
        ("wren_abernethy", "player"),
        ("zed_ames", "player"),
    ]
    assert client.get("/api/characters/tobiah_rennick").json() == PREMADE


@pytest.mark.parametrize("id", ["nobody", "Not-An-Id", "player"])
def test_an_unknown_character_is_not_found(client: TestClient, id: str) -> None:
    for method in ("GET", "PUT", "DELETE"):
        body = character() if method == "PUT" else None
        response = client.request(method, f"/api/characters/{id}", json=body)
        assert (response.status_code, response.json()) == (404, {"error": "No such character"})
    assert client.get(f"/api/characters/{id}/export").status_code == 404


def test_premade_characters_cant_be_changed(
    client: TestClient, premade_dir: Path, root: Path
) -> None:
    id = PREMADE["id"]
    before = (premade_dir / f"{id}.json").read_bytes()
    refused = {"error": "Premade characters are read-only"}

    edited = client.put(f"/api/characters/{id}", json=PREMADE | {"persona": "Grumpy."})
    deleted = client.delete(f"/api/characters/{id}")
    rerolled = client.post(
        "/api/characters/reroll", json={"character": PREMADE, "sections": ["voice"]}
    )
    disguised = client.post(
        "/api/characters/reroll",
        json={"character": PREMADE | {"source": "player"}, "sections": ["voice"]},
    )
    exported = client.get(f"/api/characters/{id}/export")
    copied = client.post("/api/characters", json=PREMADE)

    assert (edited.status_code, edited.json()) == (403, refused)
    assert (deleted.status_code, deleted.json()) == (403, refused)
    assert (rerolled.status_code, rerolled.json()) == (403, refused)
    assert (disguised.status_code, disguised.json()) == (403, refused)
    assert (exported.status_code, exported.json()) == (
        403,
        {"error": "Premade characters can't be exported"},
    )
    assert (copied.status_code, copied.json()) == (403, refused)
    assert (premade_dir / f"{id}.json").read_bytes() == before
    assert client.get(f"/api/characters/{id}").json() == PREMADE
    assert files(root) == []


def test_player_characters_live_in_the_library_directory(client: TestClient, root: Path) -> None:
    created = client.post("/api/characters", json=character(source="premade", version=9))

    saved = created.json()
    assert created.status_code == 201
    assert created.headers["location"] == "/api/characters/wren_abernethy"
    assert (saved["source"], saved["version"], saved["created"]) == ("player", 1, saved["updated"])
    assert json.loads((root / "characters" / "wren_abernethy.json").read_text()) == saved

    edited = client.put("/api/characters/wren_abernethy", json=saved | {"persona": "Softer now."})

    assert edited.status_code == 200
    assert edited.json()["persona"] == "Softer now."
    assert edited.json()["version"] == 2
    assert edited.json()["created"] == saved["created"]
    assert client.get("/api/characters/wren_abernethy").json() == edited.json()

    assert client.delete("/api/characters/wren_abernethy").status_code == 204
    assert client.get("/api/characters/wren_abernethy").status_code == 404
    assert files(root) == []


def test_an_edit_cant_change_the_id(client: TestClient) -> None:
    client.post("/api/characters", json=character())

    response = client.put("/api/characters/wren_abernethy", json=character(id="someone_else"))

    assert (response.status_code, response.json()) == (
        422,
        {"error": "A character's id can't change"},
    )


@pytest.mark.parametrize(
    ("body", "status", "error"),
    [
        (b"{", 422, "The request isn't JSON"),
        (b"[]", 422, "The request must be a JSON object"),
        (json.dumps(character(birth_year=1850)).encode(), 422, "born in 1850, they'd be"),
        (json.dumps(character(gender="robot")).encode(), 422, "gender: Input should be"),
        (b" " * (300 * 1024), 413, "The request can be at most 256 KB"),
    ],
)
def test_a_bad_character_is_refused(
    client: TestClient, root: Path, body: bytes, status: int, error: str
) -> None:
    response = client.post("/api/characters", content=body, headers=JSON)

    assert response.status_code == status
    assert error in response.json()["error"]
    assert files(root) == []


def test_generates_a_draft_and_streams_what_claude_writes(
    client: TestClient, fake: FakeProvider, replies: list[str], root: Path
) -> None:
    got = events(
        client, "/api/characters/generate", {"name": "Wren Abernethy", "occupation": "Glazier"}
    )

    assert [e["purpose"] for e in got if e["type"] == "call"] == [
        "character-biography",
        "character-critic",
    ]
    assert texts(got) == replies
    done = got[-1]
    draft = done["character"]
    assert done["type"] == "done"
    assert (draft["name"], draft["occupation"], draft["source"]) == (
        "Wren Abernethy",
        "Glazier",
        "player",
    )
    assert draft["backstory"] == "Written backstory."
    assert {
        "field": "backstory",
        "current": "Written backstory.",
        "suggested": "Revised backstory.",
    } in done["suggestions"]
    assert done["notes"] == ["Swapped a stock phrase for something specific."]
    assert done["warnings"] == []
    assert files(root) == []


def test_a_draft_never_takes_a_library_id(client: TestClient) -> None:
    client.post("/api/characters", json=character())

    got = events(client, "/api/characters/generate", {"name": "Wren Abernethy"})

    assert got[-1]["character"]["id"] == "wren_abernethy_2"


def test_a_reroll_keeps_locked_fields(client: TestClient, fake: FakeProvider) -> None:
    saved = client.post("/api/characters", json=character()).json()

    got = events(client, "/api/characters/reroll", {"character": saved, "sections": ["biography"]})

    rerolled = got[-1]["character"]
    kept = set(saved) - BIOGRAPHY - {"updated", "version"}
    assert {field: rerolled[field] for field in kept} == {field: saved[field] for field in kept}
    assert rerolled["version"] == saved["version"] + 1
    assert rerolled["backstory"] == "Written backstory."
    assert set(requested(fake.requests[0])["properties"]) == BIOGRAPHY


def test_a_reroll_names_known_sections(client: TestClient) -> None:
    for sections, error in [
        ([], "sections: List should have at least 1 item"),
        (["mood"], "no such section: mood"),
    ]:
        response = client.post(
            "/api/characters/reroll", json={"character": character(), "sections": sections}
        )
        assert response.status_code == 422
        assert error in response.json()["error"]


def test_a_near_copy_of_a_library_character_is_warned_about(client: TestClient) -> None:
    client.post(
        "/api/characters",
        json=character(backstory="Written backstory.", persona="Written persona."),
    )

    got = events(client, "/api/characters/generate", {"name": "Ada Lyle"})

    assert got[-1]["warnings"] == ["Close to Wren Abernethy in the library (1.00)."]


def test_a_failed_call_ends_the_stream_with_its_reason(
    client: TestClient, fake: FakeProvider
) -> None:
    fake.replies.append(LLMError("usage limit reached"))

    got = events(client, "/api/characters/generate", {})

    assert got == [
        {"type": "call", "purpose": "character-biography"},
        {"type": "error", "error": "usage limit reached"},
    ]


@pytest.mark.anyio
async def test_requests_together_get_only_two_slots(
    app: Starlette, fake: FakeProvider, library: Library
) -> None:
    hold, written = asyncio.Event(), asyncio.Event()
    statuses: list[int] = []

    async def slow(request: Request) -> str:
        await hold.wait()
        return answer(request)

    async def post() -> None:
        async def receive() -> Message:
            return {"type": "http.request", "body": b"{}", "more_body": False}

        async def send(message: Message) -> None:
            if message["type"] == "http.response.start":
                statuses.append(message["status"])
                await written.wait()

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/characters/generate",
            "raw_path": b"/api/characters/generate",
            "query_string": b"",
            "root_path": "",
            "headers": [(b"host", b"localhost"), (b"content-type", b"application/json")],
        }
        await app(scope, receive, send)

    fake.default = slow
    posts = [asyncio.create_task(post()) for _ in range(6)]
    for _ in range(500):
        if len(statuses) == len(posts):
            break
        await asyncio.sleep(0.01)
    held = library.generating
    hold.set()
    written.set()
    await asyncio.gather(*posts)

    assert sorted(statuses) == [200, 200, 429, 429, 429, 429]
    assert (held, library.generating) == (MAX_GENERATING, 0)


@pytest.mark.anyio
async def test_a_stream_that_never_starts_gives_its_slot_back(library: Library) -> None:
    async def lines() -> AsyncIterator[str]:
        yield "never sent\n"

    async def receive() -> Message:
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        await asyncio.sleep(10)

    response = EventStream(lines(), library)
    held = library.generating
    await response({"type": "http", "asgi": {"spec_version": "2.0"}}, receive, send)

    assert (held, library.generating) == (1, 0)


def test_export_then_import_round_trips(client: TestClient, library: Library, root: Path) -> None:
    client.post("/api/characters", json=character())
    voiced = library.save_clip("wren_abernethy", clip()).model_dump(mode="json")

    exported = client.get("/api/characters/wren_abernethy/export")
    imported = client.post("/api/characters/import", headers=ZIP, content=exported.content)

    assert exported.headers["content-type"] == "application/zip"
    assert exported.headers["content-disposition"] == 'attachment; filename="wren_abernethy.zip"'
    assert zipfile.ZipFile(io.BytesIO(exported.content)).namelist() == [
        "character.json",
        "voice.wav",
    ]
    copy = imported.json()
    assert imported.status_code == 201
    assert copy["id"] == "wren_abernethy_2"
    assert copy["voice"]["reference_clip"] == "clips/wren_abernethy_2.wav"
    assert copy | {"id": voiced["id"], "voice": voiced["voice"]} == voiced
    assert (root / "clips" / "wren_abernethy_2.wav").read_bytes() == clip()

    client.delete("/api/characters/wren_abernethy")
    again = client.post("/api/characters/import", headers=ZIP, content=exported.content).json()

    assert again | {"id": voiced["id"], "voice": voiced["voice"]} == voiced
    assert again["voice"]["reference_clip"] == "clips/wren_abernethy.wav"


def test_the_client_can_change_the_library_from_its_own_origin(client: TestClient) -> None:
    origin = {"Origin": "http://localhost:5173"}

    created = client.post("/api/characters", json=character(), headers=origin)
    edited = client.put("/api/characters/wren_abernethy", json=character(), headers=origin)
    exported = client.get("/api/characters/wren_abernethy/export", headers=origin)
    deleted = client.delete("/api/characters/wren_abernethy", headers=origin)
    imported = client.post("/api/characters/import", content=exported.content, headers=origin | ZIP)
    player = client.put("/api/player", json={"appearance": LOOK}, headers=origin)

    statuses = [r.status_code for r in (created, edited, exported, deleted, imported, player)]
    assert statuses == [201, 200, 200, 204, 201, 200]


def test_an_import_takes_nothing_but_the_character_and_its_clip(
    client: TestClient, root: Path
) -> None:
    hostile = character(
        id="tobiah_rennick",
        source="premade",
        voice=character()["voice"] | {"reference_clip": "../../../../etc/passwd"},
    )

    with_clip = client.post(
        "/api/characters/import",
        headers=ZIP,
        content=archive({"character.json": json.dumps(hostile), "voice.wav": clip()}),
    ).json()
    without = client.post(
        "/api/characters/import",
        headers=ZIP,
        content=archive({"character.json": json.dumps(hostile)}),
    ).json()

    assert (with_clip["id"], with_clip["source"]) == ("tobiah_rennick_2", "player")
    assert with_clip["voice"]["reference_clip"] == "clips/tobiah_rennick_2.wav"
    assert (without["id"], without["voice"]["reference_clip"]) == ("tobiah_rennick_3", None)
    assert files(root) == [
        "characters/tobiah_rennick_2.json",
        "characters/tobiah_rennick_3.json",
        "clips/tobiah_rennick_2.wav",
    ]


def encrypted() -> bytes:
    data = bytearray(archive({"character.json": json.dumps(character())}))
    for header, offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        data[data.index(header) + offset] |= 0x1
    return bytes(data)


def twice() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped, pytest.warns(UserWarning):
        zipped.writestr("character.json", json.dumps(character()))
        zipped.writestr("character.json", json.dumps(character()))
    return buffer.getvalue()


def patched(data: bytes, at: bytes, offset: int, value: bytes) -> bytes:
    start = data.index(at) + offset
    return data[:start] + value + data[start + len(value) :]


GOOD = json.dumps(character())
DAMAGED = "That isn't a character file, or it's damaged: "
UNDECODABLE = "The voice clip isn't a WAV file that decodes"
BAD_CHUNK = patched(clip(), b"fmt ", 4, b"\xff\xff\xff\x00")
BAD_FILES = {
    "not a zip": (b"just some text", f"{DAMAGED}File is not a zip file"),
    "a bad directory offset": (
        patched(archive({"character.json": GOOD}), b"PK\x05\x06", 16, b"\x00\x00\x10\x00"),
        f"{DAMAGED}negative seek value",
    ),
    "a name that isn't utf-8": (
        patched(
            patched(archive({"character.json": GOOD}), b"PK\x01\x02", 9, b"\x08"),
            b"PK\x01\x02",
            46,
            b"\xff",
        ),
        f"{DAMAGED}'utf-8' codec can't decode",
    ),
    "bzip2": (
        archive({"character.json": GOOD}, zipfile.ZIP_BZIP2),
        "character.json has to be stored or deflated, not compressed another way",
    ),
    "lzma": (
        archive({"character.json": GOOD, "voice.wav": clip()}, zipfile.ZIP_LZMA),
        "character.json has to be stored or deflated, not compressed another way",
    ),
    "a clip with a bad chunk size": (
        archive({"character.json": GOOD, "voice.wav": BAD_CHUNK}),
        UNDECODABLE,
    ),
    "no character": (archive({"voice.wav": clip()}), "The character file has no character.json"),
    "another file": (
        archive({"character.json": GOOD, "../../escape.json": "{}"}),
        "A character file holds only character.json and voice.wav, not '../../escape.json'",
    ),
    "a folder": (
        archive({"character.json": GOOD, "clips/": ""}),
        "A character file holds only character.json and voice.wav, not 'clips/'",
    ),
    "not a character": (
        archive({"character.json": json.dumps(character(name=""))}),
        "character.json isn't a valid character: name: String should have at least 1 character",
    ),
    "a path for an id": (
        archive({"character.json": json.dumps(character(id="../../escape"))}),
        "character.json isn't a valid character: id: String should match pattern",
    ),
    "not json": (
        archive({"character.json": "{"}),
        "character.json isn't a valid character: Invalid JSON",
    ),
    "a clip that won't decode": (
        archive({"character.json": GOOD, "voice.wav": b"RIFF....WAVEnope"}),
        UNDECODABLE,
    ),
    "a clip cut short": (
        archive({"character.json": GOOD, "voice.wav": clip()[:-1000]}),
        "The voice clip is cut short",
    ),
    "an empty clip": (
        archive({"character.json": GOOD, "voice.wav": clip(0)}),
        "The voice clip is empty",
    ),
    "a long clip": (
        archive({"character.json": GOOD, "voice.wav": clip(61, rate=8000)}),
        "The voice clip can be at most 60 seconds long",
    ),
    "a huge character": (
        archive({"character.json": json.dumps(character(backstory="x" * 300_000))}),
        "character.json can be at most 256 KB",
    ),
    "a zip bomb": (
        archive({"character.json": GOOD, "voice.wav": bytes(11 * 2**20)}),
        "voice.wav can be at most 10240 KB",
    ),
}


@pytest.mark.parametrize(("data", "error"), BAD_FILES.values(), ids=BAD_FILES.keys())
def test_a_bad_file_is_refused_with_a_clear_reason(
    client: TestClient, root: Path, data: bytes, error: str
) -> None:
    response = client.post("/api/characters/import", headers=ZIP, content=data)

    assert response.status_code == 422
    assert response.json()["error"].startswith(error)
    assert files(root) == []


@pytest.mark.parametrize(
    ("data", "error"),
    [
        (encrypted(), "character.json is encrypted"),
        (twice(), "The character file has the same name in it twice"),
    ],
    ids=["encrypted", "a name twice"],
)
def test_a_crafted_file_is_refused(client: TestClient, root: Path, data: bytes, error: str) -> None:
    response = client.post("/api/characters/import", headers=ZIP, content=data)

    assert (response.status_code, response.json()) == (422, {"error": error})
    assert files(root) == []


def test_an_oversized_file_is_refused_before_its_read(client: TestClient) -> None:
    response = client.post("/api/characters/import", headers=ZIP, content=bytes(13 * 2**20))

    assert (response.status_code, response.json()) == (
        413,
        {"error": "The request can be at most 12288 KB"},
    )


def test_saves_the_players_look(client: TestClient, root: Path) -> None:
    assert client.get("/api/player").json() == {"appearance": PLAYER.model_dump(mode="json")}

    look = LOOK | {"hair_style": "long"}
    saved = client.put("/api/player", json={"appearance": look})

    assert saved.json() == {"appearance": look}
    assert client.get("/api/player").json() == {"appearance": look}
    assert files(root) == ["player.json"]


def test_a_bad_look_is_refused(client: TestClient, root: Path) -> None:
    response = client.put("/api/player", json={"appearance": LOOK | {"skin": "pink"}})

    assert response.status_code == 422
    assert response.json()["error"].startswith("appearance.skin: String should match pattern")
    assert files(root) == []
