import pytest

from simile.llm import FakeProvider, Message, Request, Usage

pytestmark = pytest.mark.anyio

REQUEST = Request((Message("user", "Good morning, Mara"),), "", "haiku")


async def collect(fake: FakeProvider, request: Request = REQUEST) -> list[str | Usage]:
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


async def test_replies_can_be_functions_of_the_request() -> None:
    async def shout(request: Request) -> str:
        return request.messages[-1].content.upper()

    fake = FakeProvider([lambda request: request.model, shout])

    assert (await collect(fake))[0] == "haiku"
    assert (await collect(fake))[:2] == ["GOOD ", "MORNING, "]
