import asyncio
import json
import os
import socket
from collections import deque
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from simile.llm import CallRecord, FakeProvider, LLMClient, LLMError, Message, Request, Usage
from simile.llm.ollama import HOST_ENV, OllamaProvider, base_url

pytestmark = pytest.mark.anyio

type Step = dict[str, Any] | str | asyncio.Event


class Mood(BaseModel):
    mood: str
    intensity: float


def said(text: str) -> dict[str, Any]:
    return {"model": "gemma4:26b", "message": {"role": "assistant", "content": text}, "done": False}


DONE = {
    "model": "gemma4:26b",
    "message": {"role": "assistant", "content": ""},
    "done": True,
    "done_reason": "stop",
    "total_duration": 1_250_000_000,
    "load_duration": 2_000_000,
    "prompt_eval_count": 1200,
    "prompt_eval_cached_count": 900,
    "prompt_eval_duration": 400_000_000,
    "eval_count": 9,
    "eval_duration": 300_000_000,
}


@dataclass
class Reply:
    steps: list[Step]
    status: int = 200
    finish: bool = True
    """Ends the chunked body properly. Without it, the server hangs up mid-reply."""


@dataclass
class FakeOllama:
    """A stand-in for Ollama's `/api/chat` that streams scripted NDJSON frames."""

    host: str = ""
    replies: deque[Reply] = field(default_factory=deque)
    requests: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)
    hung_up: asyncio.Event = field(default_factory=asyncio.Event)
    """Set when the client hangs up while the server holds a reply."""

    @property
    def bodies(self) -> list[dict[str, Any]]:
        return [body for _, _, body in self.requests]

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = (await reader.readuntil(b"\r\n\r\n")).decode().split("\r\n")
            method, path, _ = head[0].split(" ")
            headers = dict(line.lower().split(": ", 1) for line in head[1:] if line)
            body = await reader.readexactly(int(headers.get("content-length", 0)))
            self.requests.append((method, path, json.loads(body)))
            reply = self.replies.popleft()
            writer.write(
                f"HTTP/1.1 {reply.status} Fake\r\nContent-Type: application/x-ndjson\r\n"
                "Transfer-Encoding: chunked\r\nConnection: close\r\n\r\n".encode()
            )
            for step in reply.steps:
                if isinstance(step, asyncio.Event):
                    if await self.hold(step, reader):
                        return
                    continue
                line = (step if isinstance(step, str) else json.dumps(step)).encode() + b"\n"
                writer.write(f"{len(line):x}\r\n".encode() + line + b"\r\n")
                await writer.drain()
            if reply.finish:
                writer.write(b"0\r\n\r\n")
                await writer.drain()
                await reader.read()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    async def hold(self, resume: asyncio.Event, reader: asyncio.StreamReader) -> bool:
        """Wait for `resume`, or for the client to hang up, which returns True."""
        resumed = asyncio.ensure_future(resume.wait())
        eof = asyncio.ensure_future(reader.read())
        await asyncio.wait({resumed, eof}, return_when=asyncio.FIRST_COMPLETED)
        resumed.cancel()
        eof.cancel()
        if resume.is_set():
            return False
        self.hung_up.set()
        return True

    async def until_hung_up(self) -> None:
        await asyncio.wait_for(self.hung_up.wait(), timeout=2)


@pytest.fixture
async def ollama(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FakeOllama]:
    fake = FakeOllama()
    server = await asyncio.start_server(fake.handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    fake.host = f"127.0.0.1:{port}"
    monkeypatch.setenv(HOST_ENV, fake.host)
    async with server:
        yield fake


def request(*messages: Message, system: str = "You are Mara.") -> Request:
    return Request(messages or (Message("user", "Morning!"),), system, "ollama:gemma4:26b")


async def test_streams_the_reply_then_its_usage(ollama: FakeOllama) -> None:
    ollama.replies.append(Reply([said("Morning"), said(", love."), DONE]))

    chunks = [chunk async for chunk in OllamaProvider().stream(request())]

    assert chunks == [
        "Morning",
        ", love.",
        Usage(
            input_tokens=300,
            output_tokens=9,
            cache_read_tokens=900,
            model="ollama:gemma4:26b",
            api_ms=1250,
        ),
    ]


async def test_sends_the_system_prompt_and_turns_to_api_chat(ollama: FakeOllama) -> None:
    ollama.replies.append(Reply([said("Hi."), DONE]))
    turns = (Message("user", "Hi"), Message("assistant", "Hello!"), Message("user", "Coffee?"))

    [_ async for _ in OllamaProvider().stream(request(*turns))]

    method, path, body = ollama.requests[0]
    assert (method, path) == ("POST", "/api/chat")
    assert body == {
        "model": "gemma4:26b",
        "messages": [
            {"role": "system", "content": "You are Mara."},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "Coffee?"},
        ],
        "stream": True,
        "think": False,
    }


async def test_leaves_out_an_empty_system_prompt(ollama: FakeOllama) -> None:
    ollama.replies.append(Reply([said("Hi."), DONE]))

    [_ async for _ in OllamaProvider().stream(request(system=""))]

    assert [m["role"] for m in ollama.bodies[0]["messages"]] == ["user"]


async def test_the_client_sends_ollama_models_to_ollama(ollama: FakeOllama) -> None:
    ollama.replies.append(Reply([said("Morning"), said(", love."), DONE]))
    records: list[CallRecord] = []

    reply = await LLMClient(listeners=[records.append]).complete(
        "Morning!", model="ollama:gemma4:26b", purpose="player-reply"
    )

    assert reply == "Morning, love."
    [record] = records
    assert (record.provider, record.model, record.error) == ("ollama", "ollama:gemma4:26b", None)
    assert record.ttft_ms is not None
    assert record.usage is not None and record.usage.output_tokens == 9


async def test_a_given_provider_takes_ollama_models_too() -> None:
    fake = FakeProvider(["Hi."])

    await LLMClient(fake).complete("Hello", model="ollama:gemma4:26b")

    assert fake.requests[0].model == "ollama:gemma4:26b"


async def test_structured_passes_the_schema_as_the_format(ollama: FakeOllama) -> None:
    ollama.replies.append(Reply([said('{"mood": "glad", '), said('"intensity": 0.5}'), DONE]))

    mood = await LLMClient().structured("How is Mara?", Mood, model="ollama:gemma4:26b")

    assert mood == Mood(mood="glad", intensity=0.5)
    assert ollama.bodies[0]["format"] == Mood.model_json_schema()
    assert '"intensity"' in ollama.bodies[0]["messages"][0]["content"]


async def test_an_http_error_raises_its_message(ollama: FakeOllama) -> None:
    ollama.replies.append(Reply([{"error": "model 'nope' not found"}], status=404))

    with pytest.raises(LLMError, match="model 'nope' not found"):
        await LLMClient().complete("Hi", model="ollama:nope")


async def test_an_error_mid_stream_fails_the_call(ollama: FakeOllama) -> None:
    ollama.replies.append(Reply([said("Well, "), {"error": "out of memory"}]))
    chunks: list[str] = []

    with pytest.raises(LLMError, match="out of memory"):
        async for chunk in LLMClient().stream("Hi", model="ollama:gemma4:26b"):
            chunks.append(chunk)

    assert chunks == ["Well, "]


async def test_a_reply_cut_short_is_an_error(ollama: FakeOllama) -> None:
    ollama.replies.append(Reply([said("One, two"), {**DONE, "done_reason": "length"}]))

    with pytest.raises(LLMError, match="cut the reply short"):
        await LLMClient().complete("Count", model="ollama:gemma4:26b")


async def test_a_reply_that_stops_before_done_is_an_error(ollama: FakeOllama) -> None:
    ollama.replies.append(Reply([said("Well, ")]))

    with pytest.raises(LLMError, match="before it was done"):
        await LLMClient().complete("Hi", model="ollama:gemma4:26b")


async def test_hanging_up_mid_reply_is_an_error(ollama: FakeOllama) -> None:
    ollama.replies.append(Reply([said("Well, ")], finish=False))

    with pytest.raises(LLMError, match="Ollama: RemoteProtocolError"):
        await LLMClient().complete("Hi", model="ollama:gemma4:26b")


async def test_a_garbled_frame_is_an_error(ollama: FakeOllama) -> None:
    ollama.replies.append(Reply(["not json"]))

    with pytest.raises(LLMError, match="JSONDecodeError"):
        await LLMClient().complete("Hi", model="ollama:gemma4:26b")


async def test_no_server_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    with socket.socket() as unused:
        unused.bind(("127.0.0.1", 0))
        port = unused.getsockname()[1]
    monkeypatch.setenv(HOST_ENV, f"127.0.0.1:{port}")

    with pytest.raises(LLMError, match="Can't reach Ollama .* Is it running"):
        await LLMClient().complete("Hi", model="ollama:gemma4:26b")


async def test_leaving_a_stream_early_hangs_up_and_frees_its_slot(ollama: FakeOllama) -> None:
    ollama.replies.append(Reply([said("Well, "), asyncio.Event(), DONE]))
    ollama.replies.append(Reply([said("Hi."), DONE]))
    records: list[CallRecord] = []
    client = LLMClient(max_concurrency=1, listeners=[records.append])

    async with aclosing(client.stream("Hi", model="ollama:gemma4:26b")) as chunks:
        async for _ in chunks:
            break

    await ollama.until_hung_up()
    assert records[0].error == "cancelled"
    assert await asyncio.wait_for(client.complete("Hi", model="ollama:gemma4:26b"), 2) == "Hi."


async def test_cancelling_mid_stream_hangs_up(ollama: FakeOllama) -> None:
    ollama.replies.append(Reply([said("Well, "), asyncio.Event(), DONE]))
    started = asyncio.Event()

    async def listen() -> None:
        async for _ in LLMClient().stream("Hi", model="ollama:gemma4:26b"):
            started.set()

    task = asyncio.create_task(listen())
    await asyncio.wait_for(started.wait(), 2)
    task.cancel()

    await ollama.until_hung_up()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.parametrize(
    ("host", "url"),
    [
        ("127.0.0.1", "http://127.0.0.1:11434"),
        ("0.0.0.0:8080", "http://0.0.0.0:8080"),
        ("http://ollama.test:80/", "http://ollama.test:80"),
        ("https://ollama.test", "https://ollama.test"),
    ],
)
def test_reads_the_host_as_ollama_does(host: str, url: str) -> None:
    assert base_url(host) == url


def test_defaults_to_the_local_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(HOST_ENV, raising=False)

    assert OllamaProvider().host == "http://127.0.0.1:11434"


LIVE_MODEL = os.environ.get("SIMILE_OLLAMA_TEST_MODEL")


def ollama_running() -> bool:
    host = base_url(os.environ.get(HOST_ENV, "127.0.0.1"))
    try:
        return httpx.get(f"{host}/api/version").is_success
    except httpx.HTTPError:
        return False


@pytest.mark.skipif(
    not LIVE_MODEL or not ollama_running(),
    reason="needs a running Ollama and SIMILE_OLLAMA_TEST_MODEL naming a model it has",
)
async def test_a_real_ollama_answers() -> None:
    records: list[CallRecord] = []

    reply = await LLMClient(listeners=[records.append]).complete(
        "Say good morning in three words.", model=f"ollama:{LIVE_MODEL}"
    )

    assert reply.strip()
    assert records[0].usage is not None and records[0].usage.output_tokens > 0
