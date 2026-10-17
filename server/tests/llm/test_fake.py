import asyncio

import pytest

from simile.llm import FakeProvider, Message, Request, Usage
from simile.llm.fake import GOODBYES, cast, scene
from simile.llm.lifespan import CANNED, CannedProvider

pytestmark = pytest.mark.anyio

REQUEST = Request((Message("user", "Good morning, Mara"),), "", "haiku")


async def collect(
    fake: FakeProvider | CannedProvider, request: Request = REQUEST
) -> list[str | Usage]:
    return [chunk async for chunk in fake.stream(request)]


async def test_streams_words_then_usage() -> None:
    chunks = await collect(FakeProvider(["  Morning,\nstranger. "]))

    assert chunks[:-1] == ["  Morning,\n", "stranger. "]
    assert chunks[-1] == Usage(input_tokens=3, output_tokens=2, model="fake-haiku")


async def test_replies_in_order_then_falls_back_to_the_default() -> None:
    fake = FakeProvider(["One.", "Two."], default="Again.")

    replies = ["".join(map(str, (await collect(fake))[:-1])) for _ in range(3)]

    assert replies == ["One.", "Two.", "Again."]
    assert fake.requests == [REQUEST] * 3


async def test_fails_when_the_script_runs_out() -> None:
    with pytest.raises(AssertionError, match="no reply left"):
        await collect(FakeProvider([]))


async def test_raises_scripted_exceptions() -> None:
    with pytest.raises(TimeoutError):
        await collect(FakeProvider([TimeoutError()]))


async def test_scripts_can_pause_and_fail_mid_stream() -> None:
    resume = asyncio.Event()
    stream = FakeProvider([["Hello ", "there", resume, TimeoutError()]]).stream(REQUEST)

    assert [await anext(stream), await anext(stream)] == ["Hello ", "there"]
    paused = asyncio.create_task(anext(stream))
    await asyncio.sleep(0.01)
    assert not paused.done()
    resume.set()
    with pytest.raises(TimeoutError):
        await paused


async def test_replies_can_be_functions_of_the_request() -> None:
    async def shout(request: Request) -> str:
        return request.messages[-1].content.upper()

    fake = FakeProvider([lambda request: request.model, shout])

    assert (await collect(fake))[0] == "haiku"
    assert (await collect(fake))[:2] == ["GOOD ", "MORNING, "]


def asking(prompt: str) -> Request:
    return Request((Message("user", prompt),), "", "haiku")


SCENE = (
    "It's 10:15, at The Daily Grind. Tobias has just walked up to Desmond.\n\n## Direction\n"
    "- Tobias speaks first. About 5 lines in all, ending when Desmond takes their leave."
)


def test_a_scene_request_gets_its_script() -> None:
    assert cast(asking(SCENE)) == ("Tobias", "Desmond", 5)
    assert scene(asking(SCENE), ["Morning!", "Hm."]) == (
        "Tobias: Morning! [values: connection]\n"
        "Desmond: Hm. [values: connection]\n"
        "Tobias: Morning! [values: connection]\n"
        f"Desmond: {GOODBYES[0]} [values: connection]\n"
        f"Tobias: {GOODBYES[1]} [values: connection]\n"
    )


def test_any_other_request_gets_no_script() -> None:
    assert cast(REQUEST) is None
    assert scene(REQUEST, ["Morning!"]) is None


async def test_the_canned_provider_answers_a_scene_with_a_script_of_its_lines() -> None:
    chunks = await collect(CannedProvider(), asking(SCENE))
    lines = "".join(chunk for chunk in chunks if isinstance(chunk, str)).splitlines()

    assert len(lines) == 5
    assert lines[0] == f"Tobias: {CANNED[0]} [values: connection]"
    assert lines[-1] == f"Tobias: {GOODBYES[1]} [values: connection]"
