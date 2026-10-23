from collections.abc import Callable

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.conversation.flush import flushed
from simile.schema import PLAYER_ID, Line, Player
from simile.sim import Clock, LineSpoken, World

from ..story.test_journal import ALIBI, ASLEEP, EYE, Listening
from .test_player import START

MakePackage = Callable[[dict[str, str]], str]


def flushes(listening: Listening, player: Player) -> list[tuple[str, bool]]:
    """Each of the resident's lines as they say it, and whether the eye sees them flush."""
    seen: list[tuple[str, bool]] = []

    def spoken(event: LineSpoken) -> None:
        if event.line.speaker != PLAYER_ID:
            talk = listening.village.players.talk()
            seen.append((event.line.text, flushed(talk, event.line, player)))

    listening.village.world.bus.subscribe(LineSpoken, spoken)
    return seen


@pytest.mark.anyio
async def test_the_eye_shows_a_flush_exactly_on_the_lie_and_the_journal_agrees() -> None:
    listening = Listening(EYE, f"Me? {ALIBI} Why do you ask?")
    listening.village.walk_to("ben", 1)
    seen = flushes(listening, EYE)

    await listening.say("Where were you the night Aris was attacked?", "ben")

    assert [text for text, flush in seen if flush] == [ALIBI]
    assert len(seen) > 1
    assert [(e.fact_id, e.flushed) for e in listening.notebook.entries] == [
        ("gone", False),
        ("there_ben", True),
    ]


@pytest.mark.anyio
async def test_a_cover_of_two_sentences_flushes_on_the_second_as_the_journal_writes_it() -> None:
    listening = Listening(EYE, "I was fast asleep that night. I didn’t hear a THING!")
    seen = flushes(listening, EYE)

    await listening.say("Did you hear anything the night Aris was attacked?", "ana")

    assert [flush for _, flush in seen] == [False, True]
    assert listening.notebook.entries[-1].flushed is True
    assert listening.notebook.entries[-1].text == f"“{ASLEEP}”"


@pytest.mark.anyio
async def test_no_flush_without_the_eye_nor_on_the_truth() -> None:
    lie = Listening(None, f"Me? {ALIBI}")
    lie.village.walk_to("ben", 1)
    unseen = flushes(lie, Player())
    truth = Listening(EYE)
    told = flushes(truth, EYE)

    await lie.say("Where were you the night Aris was attacked?", "ben")
    await truth.say("Did you see anything the night Aris was attacked?", "ana")

    assert unseen and not any(flush for _, flush in unseen)
    assert told and not any(flush for _, flush in told)


def test_the_lifespan_sets_the_flush_hook_while_running(make_package: MakePackage) -> None:
    lifespans = ("behaviour", "conversation", "llm", "memory", "protocol", "world")
    files = {f"{m}/lifespan.py": f"from simile.{m}.lifespan import lifespan\n" for m in lifespans}
    app: Starlette = create_app(make_package(files))
    app.state.world = World(Clock(START))
    line = Line(id=1, conversation_id="c", speaker="ben", text=ALIBI, timestamp=START, duration=1)

    with TestClient(app):
        assert app.state.flushed(line) is False
    assert not hasattr(app.state, "flushed")
