import asyncio
import logging
from contextlib import aclosing

import pytest
from pydantic import BaseModel
from starlette.testclient import TestClient

from simile.app import create_app
from simile.llm import (
    CallRecord,
    FakeProvider,
    LLMClient,
    LLMError,
    Message,
    Model,
    Request,
    StructuredOutputError,
)

pytestmark = pytest.mark.anyio


class Mood(BaseModel):
    mood: str
    intensity: float


GLAD = '{"mood": "glad", "intensity": 0.5}'


async def test_streams_the_reply_in_chunks() -> None:
    client = LLMClient(FakeProvider(["Morning, stranger."]))

    chunks = [chunk async for chunk in client.stream("Hello")]

    assert chunks == ["Morning, ", "stranger."]


async def test_sends_the_messages_system_prompt_and_model() -> None:
    fake = FakeProvider(["Sure."])
    messages = [Message("user", "Hi"), Message("assistant", "Hello!"), Message("user", "Coffee?")]

    await LLMClient(fake).complete(messages, system="You are Mara.", model=Model.SONNET)

    assert fake.requests == [Request(tuple(messages), "You are Mara.", "sonnet")]


async def test_defaults_to_haiku() -> None:
    fake = FakeProvider(["Hi."])

    await LLMClient(fake).complete("Hello")

    assert fake.requests[0].model == "haiku"


async def test_the_last_message_must_be_from_the_user() -> None:
    client = LLMClient(FakeProvider(["Hi."]))

    with pytest.raises(ValueError, match="last message"):
        await client.complete([Message("user", "Hi"), Message("assistant", "Hello")])


async def test_records_and_logs_every_call(caplog: pytest.LogCaptureFixture) -> None:
    records: list[CallRecord] = []
    client = LLMClient(FakeProvider(["Morning, stranger."]), listeners=[records.append])

    with caplog.at_level(logging.INFO, logger="simile.llm"):
        await client.complete("Hello", purpose="greeting")

    [record] = records
    assert (record.purpose, record.model, record.provider, record.error) == (
        "greeting",
        "haiku",
        "fake",
        None,
    )
    assert record.usage is not None and record.usage.output_tokens == 2
    assert record.ttft_ms is not None and 0 <= record.ttft_ms <= record.latency_ms
    assert [r.llm_call for r in caplog.records] == [record]


async def test_records_failures() -> None:
    records: list[CallRecord] = []
    client = LLMClient(FakeProvider([LLMError("usage limit reached")]), listeners=[records.append])

    with pytest.raises(LLMError):
        await client.complete("Hello")

    assert records[0].error == "LLMError: usage limit reached"
    assert records[0].ttft_ms is None


async def test_caps_concurrent_calls() -> None:
    in_flight = peak = 0
    release = asyncio.Event()

    async def slow(request: Request) -> str:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await release.wait()
        in_flight -= 1
        return "done"

    records: list[CallRecord] = []
    client = LLMClient(FakeProvider([slow] * 5), max_concurrency=2, listeners=[records.append])
    calls = [asyncio.create_task(client.complete("Hi")) for _ in range(5)]
    for _ in range(10):
        await asyncio.sleep(0)

    assert in_flight == 2
    release.set()
    assert await asyncio.gather(*calls) == ["done"] * 5
    assert peak == 2
    assert max(r.queued_ms for r in records) > 0


async def test_leaving_a_stream_early_frees_its_slot() -> None:
    records: list[CallRecord] = []
    client = LLMClient(
        FakeProvider(default="one two three"), max_concurrency=1, listeners=[records.append]
    )

    async with aclosing(client.stream("Hi")) as chunks:
        async for _ in chunks:
            break

    assert await asyncio.wait_for(client.complete("Hi"), timeout=1) == "one two three"
    assert records[0].error == "cancelled"


async def test_structured_returns_the_validated_model() -> None:
    fake = FakeProvider([GLAD])

    mood = await LLMClient(fake).structured("How is Mara?", Mood, system="You read moods.")

    assert mood == Mood(mood="glad", intensity=0.5)
    assert fake.requests[0].system.startswith("You read moods.\n\n")
    assert '"intensity"' in fake.requests[0].system


async def test_structured_finds_the_json_in_a_code_fence() -> None:
    client = LLMClient(FakeProvider([f"Here you go:\n```json\n{GLAD}\n```"]))

    assert await client.structured("How is Mara?", Mood) == Mood(mood="glad", intensity=0.5)


async def test_structured_retries_once_with_the_validation_error() -> None:
    fake = FakeProvider(['{"mood": "glad"}', GLAD])

    mood = await LLMClient(fake).structured("How is Mara?", Mood)

    assert mood == Mood(mood="glad", intensity=0.5)
    retry = fake.requests[1].messages
    assert retry[:2] == (Message("user", "How is Mara?"), Message("assistant", '{"mood": "glad"}'))
    assert "intensity" in retry[2].content
    assert "Field required" in retry[2].content


async def test_structured_gives_up_after_one_retry() -> None:
    client = LLMClient(FakeProvider(["Glad, I think.", "Still glad."]))

    with pytest.raises(StructuredOutputError) as error:
        await client.structured("How is Mara?", Mood)

    assert error.value.text == "Still glad."


async def test_fake_replies_can_be_models() -> None:
    client = LLMClient(FakeProvider([Mood(mood="tired", intensity=0.2)]))

    assert await client.structured("How is Mara?", Mood) == Mood(mood="tired", intensity=0.2)


def test_the_server_shares_one_client() -> None:
    with TestClient(create_app()) as client:
        assert isinstance(client.app.state.llm, LLMClient)
