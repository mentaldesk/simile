from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.behaviour import behaviour_of
from simile.behaviour.mind import create_behaviour
from simile.conversation import DEFAULT_CONFIG, conversations_of, create_engine
from simile.llm.fake import GOODBYES
from simile.llm.lifespan import CANNED, FAKE_ENV
from simile.protocol import hub_of
from simile.sim import (
    Clock,
    ConversationEnded,
    ConversationStarted,
    FakeWallClock,
    LineSpoken,
    World,
)

MakePackage = Callable[[dict[str, str]], str]

START = datetime(2026, 1, 1, 8, tzinfo=UTC)


@pytest.fixture
def app(make_package: MakePackage) -> Starlette:
    package = make_package(
        {
            f"{module}/lifespan.py": f"from simile.{module}.lifespan import lifespan\n"
            for module in ("behaviour", "conversation", "llm", "memory", "protocol", "world")
        }
    )
    app = create_app(package)
    app.state.world = World(Clock(START))
    return app


def test_plugs_into_the_behaviour_hooks_until_shutdown(app: Starlette) -> None:
    with TestClient(app) as client:
        engine, hooks = conversations_of(app), behaviour_of(app).hooks
        assert hooks.request_conversation == engine.request
        assert hooks.conversations == engine.live

        started = client.portal.call(engine.start, "kofi", "henrietta")
        snapshot = client.portal.call(hub_of(app).snapshot)
        assert [c.id for c in snapshot.conversations] == [started.id]

    assert hooks.request_conversation("kofi", "henrietta") is False
    assert hooks.conversations() == []


def test_the_server_never_reaches_claude_under_tests() -> None:
    app = create_app()

    with TestClient(app):
        assert app.state.llm.provider.name == "canned"


def test_the_llm_uses_claude_unless_told_otherwise(
    make_package: MakePackage, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(FAKE_ENV)
    app = create_app(
        make_package({"llm/lifespan.py": "from simile.llm.lifespan import lifespan\n"})
    )

    with TestClient(app):
        assert app.state.llm.provider.name == "claude-code"


async def run_village(hours: float, calls: list[str] | None = None) -> list[object]:
    app = create_app()
    world = World(Clock(START), FakeWallClock())
    app.state.world = world
    app.state.headless = True
    app.state.behaviour = create_behaviour(app, seed=0)
    app.state.conversation = create_engine(app, seed=0)
    events: list[object] = []
    for kind in (ConversationStarted, LineSpoken, ConversationEnded):
        world.bus.subscribe(kind, events.append)
    async with app.router.lifespan_context(app):
        if calls is not None:
            app.state.llm.listeners.append(lambda record: calls.append(record.purpose))
        await world.loop.run(timedelta(hours=hours))
    return events


@pytest.mark.anyio
async def test_the_village_talks_with_the_fake_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_claude(*args: object, **kwargs: object) -> None:
        raise AssertionError("A test reached Claude Code")

    monkeypatch.setattr("simile.llm.claude_code.ClaudeCodeProvider.__init__", no_claude)

    calls: list[str] = []
    events = await run_village(hours=2, calls=calls)

    ended = [event.conversation for event in events if isinstance(event, ConversationEnded)]
    assert ended
    assert all(conversation.ended for conversation in ended)
    lines = [event.line for event in events if isinstance(event, LineSpoken)]
    assert all(len(c.lines) >= DEFAULT_CONFIG.min_lines + 2 for c in ended)
    assert all(c.lines[-1].text == GOODBYES[-1] for c in ended)
    assert {line.text for line in lines} <= {*CANNED, *GOODBYES}
    assert len(lines) == len({line.id for line in lines})
    assert calls.count("conversation") == len(ended)
