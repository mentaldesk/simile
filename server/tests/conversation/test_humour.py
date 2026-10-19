from typing import Any

import pytest

from simile.conversation import ConversationConfig
from simile.conversation import engine as engine_module
from simile.conversation.prompt import JOKE, PLAIN, jokes
from simile.schema import Humour, HumourStyle, Npc
from simile.sim import ConversationStarted

from .test_lies import Scenes
from .test_player import Village, make_npc

pytestmark = pytest.mark.anyio

ALWAYS = Humour(style=HumourStyle.SILLY, seriousness=0)
NEVER = Humour(style=HumourStyle.NONE, seriousness=1)
HALF = Humour(style=HumourStyle.DRY, seriousness=0.5)
CHATTY = ConversationConfig(leave_below=0.0, long_talk=40)
SAID = ("Morning!", "Lovely day.", "Busy today?", "Off anywhere nice?", "Nice.", "Right then.")


def with_humour(humour: Humour | None, id: str = "ana", home: str = "house_1") -> Npc:
    return make_npc(id, home).model_copy(update={"humour": humour})


async def chat(humour: Humour | None) -> tuple[Village, list[bool]]:
    """The player says each of `SAID` to Ana in turn, and whether each reply was told to joke."""
    village = Village(["Right. [values: connection]"], npcs=(with_humour(humour),), config=CHATTY)
    for line in SAID:
        village.players.say(line, "ana")
        await village.run()
    told = [
        JOKE in prompt for prompt in village.script.prompts if JOKE in prompt or PLAIN in prompt
    ]
    return village, told


@pytest.mark.parametrize(("humour", "told"), [(ALWAYS, JOKE), (NEVER, PLAIN)])
async def test_a_reply_to_the_player_is_told_whether_to_joke(humour: Humour, told: str) -> None:
    village = Village(["Hello there. [values: connection]"], npcs=(with_humour(humour),))

    village.players.say("Morning!", "ana")
    await village.run()

    assert told in village.script.prompts[-1]


async def test_a_reply_without_a_humour_has_no_joke_direction() -> None:
    village = Village(["Hello there. [values: connection]"], npcs=(with_humour(None),))

    village.players.say("Morning!", "ana")
    await village.run()

    assert JOKE not in village.script.prompts[-1]
    assert PLAIN not in village.script.prompts[-1]


async def test_a_resident_never_jokes_in_two_replies_running() -> None:
    _, told = await chat(ALWAYS)

    assert len(told) >= 5
    assert told == [n % 2 == 0 for n in range(len(told))]


async def test_each_reply_rolls_on_the_conversation_the_resident_and_the_line() -> None:
    village, told = await chat(HALF)

    conversation = village.of(ConversationStarted)[0].conversation.id
    replies = [n for n, line in enumerate(village.spoken) if line.speaker == "ana"]
    expected, joked = [], False
    for n in replies[: len(told)]:
        joked = bool(jokes(HALF, f"{conversation}/ana/{n}", after_joke=joked))
        expected.append(joked)
    assert len(told) >= 5
    assert told == expected
    assert True in told and False in told


def test_a_roll_straight_after_a_joke_never_jokes() -> None:
    assert not any(jokes(ALWAYS, f"talk/ana/{n}", after_joke=True) for n in range(50))
    assert jokes(None, "talk/ana/1", after_joke=True) is None


async def test_a_scene_says_how_many_lines_each_humour_jokes_in() -> None:
    prompt, _ = await Scenes(with_humour(NEVER)).scene()

    direction = prompt.split("## Direction\n", 1)[1]
    assert "- Ana doesn't joke this time." in direction.splitlines()


async def test_a_scene_plan_rolls_on_the_conversation(monkeypatch: pytest.MonkeyPatch) -> None:
    planned: list[dict[str, Any]] = []
    plan = engine_module.plan

    def recording(*args: Any, **kwargs: Any) -> Any:
        planned.append(kwargs)
        return plan(*args, **kwargs)

    monkeypatch.setattr(engine_module, "plan", recording)
    scenes = Scenes(with_humour(HALF))
    conversation = scenes.engine.start("ana", "ben")

    [asked] = planned
    assert asked["seed"] == conversation.id
    assert asked["humours"] == {"ana": HALF, "ben": make_npc("ben", "house_2").humour}


async def test_only_a_scene_with_a_humour_gets_the_rule_for_jokes() -> None:
    with_one = Scenes(with_humour(HALF))
    await with_one.scene()
    without = Scenes(with_humour(None))
    without.engine.behaviour.npcs["ben"] = without.engine.behaviour.npcs["ben"].model_copy(
        update={"humour": None}
    )
    await without.scene()

    assert "A character with a humour" in with_one.provider.requests[-1].system
    assert "humour" not in without.provider.requests[-1].system
