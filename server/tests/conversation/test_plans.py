from datetime import timedelta

import pytest

from simile.behaviour import Options
from simile.conversation.engine import Scene
from simile.conversation.plans import already, can_do
from simile.conversation.script import script_system
from simile.schema import PLAYER_ID, Intention, IntentionKind, Medium

from . import test_engine as scenes
from . import test_player as players

PLACES = {
    "house_6": "home",
    "coffee_shop": "The Daily Grind",
    "park": "Lotus Lake Park",
    "gallery": "The Gallery",
}
TERMINALS = {"terminal_1": "News terminal on the square"}
ROUTINE = (
    "go home; go to The Daily Grind, Lotus Lake Park or The Gallery; read the news at a terminal"
)


def options(medium: Medium | None, making: dict[str, str] | None = None) -> Options:
    return Options("house_6", PLACES, TERMINALS, medium, making or {})


def promise(owner: str, kind: IntentionKind, description: str, **fields: object) -> Intention:
    now = scenes.START
    return Intention.model_validate(
        {
            "id": f"talk/{owner}/1",
            "owner": owner,
            "kind": kind,
            "description": description,
            "created": now,
            "due": now,
            "expires": now + timedelta(hours=2),
            **fields,
        }
    )


@pytest.mark.parametrize(
    ("medium", "making", "craft"),
    [
        (None, {}, "; or look someone up for a chat"),
        (
            Medium.WRITING,
            {"house_6": "home", "coffee_shop": "The Daily Grind"},
            "; look someone up for a chat; or write at home or The Daily Grind",
        ),
        (
            Medium.PAINTING,
            {"house_6": "home"},
            "; look someone up for a chat; or paint a canvas for the gallery at home",
        ),
        (
            Medium.MURAL,
            {"banyan_row": "the banyan row wall"},
            "; look someone up for a chat; or paint a mural on the banyan row wall",
        ),
        (
            Medium.MURAL,
            {"house_6": "home"},
            "; look someone up for a chat; or paint a canvas for the gallery at home, since no "
            "wall is ready for a mural",
        ),
        (Medium.MURAL, {}, "; or look someone up for a chat. No wall is ready for a mural now"),
    ],
)
def test_what_a_resident_could_plan_to_do(
    medium: Medium | None, making: dict[str, str], craft: str
) -> None:
    assert can_do(options(medium, making)) == (
        f"What you could plan to do in the village: {ROUTINE}{craft}. Only promise what's on "
        "this list, and nothing further off than tomorrow."
    )
    assert can_do(options(medium, making), "Kofi") == (
        f"What Kofi could plan to do in the village: {ROUTINE}{craft}. Kofi only promises what's "
        "on this list, and nothing further off than tomorrow."
    )


def test_what_they_have_already_said_they_will_do() -> None:
    now = scenes.START
    made = [
        promise("kofi", IntentionKind.CREATE, "a coffee ocean", promised_to=[PLAYER_ID, "ana"]),
        promise(
            "kofi",
            IntentionKind.GO,
            "sketch the lake",
            target="park",
            due=now + timedelta(days=1),
            expires=now + timedelta(days=2),
        ),
    ]
    names = {PLAYER_ID: "Visitor", "ana": "Ana"}.__getitem__

    assert already(made, now, names) == (
        "You've already said you'd do these, so keep to them:\n"
        "- make a coffee ocean (told Visitor, Ana, now)\n"
        "- sketch the lake (tomorrow 10:00)"
    )
    assert already(made[1:], now, names, "Kofi").startswith(
        "Kofi has already said they'd do these, and keeps to them:\n- sketch the lake"
    )


def test_a_scene_says_what_each_could_plan_to_do_and_has_said_they_will() -> None:
    village = scenes.Village(relationships=scenes.friends(scenes.ANA, scenes.BEN))
    walk = promise("ana", IntentionKind.GO, "walk in the park", target="park", promised_to=["ben"])
    assert village.behaviour.intend(walk)

    village.engine.start("ana", "ben")

    [scene] = village.engine._talks.values()
    assert isinstance(scene, Scene)
    prompt = scene.prompt
    assert "What Ana could plan to do in the village: go home; go to The Daily Grind" in prompt
    assert "write at home, The Daily Grind or Spark Maker Space." in prompt
    assert "Ana only promises what's on this list" in prompt
    assert (
        "Ana has already said they'd do these, and keeps to them:\n- walk in the park (told "
        "Ben, now)" in prompt
    )
    assert "Ben only promises what's on this list" in prompt
    assert "Ben has already said" not in prompt


def test_the_script_keeps_to_what_they_can_do_and_says_where_they_are_off_to() -> None:
    system = script_system()

    assert "Nobody promises to do what isn't in their notes' list" in system
    assert "says where they're off to as they leave" in system


@pytest.mark.anyio
async def test_a_reply_to_the_player_says_what_they_could_plan_and_have_promised() -> None:
    village = players.Village()
    village.behaviour.intend(
        promise("ana", IntentionKind.NEWS, "read up on the drone rules", promised_to=[PLAYER_ID])
    )

    village.players.say("Hi there.", "ana")
    await village.run()

    [prompt] = village.script.prompts
    assert "What you could plan to do in the village: go home; go to The Daily Grind" in prompt
    assert (
        "You've already said you'd do these, so keep to them:\n- read up on the drone rules "
        "(told Visitor, now)" in prompt
    )
