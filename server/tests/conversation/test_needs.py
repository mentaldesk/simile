import re

import pytest

from simile.behaviour import DEFAULT_CONFIG as BEHAVIOUR
from simile.behaviour import Need
from simile.conversation import DEFAULT_CONFIG, ConversationConfig
from simile.conversation.needs import CRITICAL, critical, feels, mood, pressing

CALM = dict.fromkeys(Need, 0.3)


def needs(**levels: float) -> dict[Need, float]:
    return {**CALM, **{Need(need): level for need, level in levels.items()}}


def test_the_critical_levels_are_b1s() -> None:
    assert CRITICAL == critical(BEHAVIOUR.urgency) == {Need.HUNGER: 0.9, Need.BLADDER: 0.9}


def test_needs_below_drain_from_bring_nothing() -> None:
    calm = pressing(needs(hunger=DEFAULT_CONFIG.drain_from - 0.05))

    assert (calm.mood, calm.errand, calm.pressure, calm.urgent) == ((), None, 0, False)
    assert calm.drain() == 1


def test_pressure_rises_from_drain_from_to_the_critical_level() -> None:
    hungry = pressing(needs(hunger=0.825))

    assert hungry.pressure == pytest.approx(0.5)
    assert hungry.drain() == pytest.approx(1 + DEFAULT_CONFIG.need_drain / 2)
    assert hungry.errand == "get something to eat"
    assert not hungry.urgent


def test_a_need_at_its_critical_level_is_urgent_and_drains_fastest() -> None:
    bursting = pressing(needs(hunger=0.8, bladder=0.95))

    assert bursting.urgent
    assert (bursting.pressure, bursting.errand) == (1, "find a loo")
    assert bursting.drain(ConversationConfig(need_drain=2)) == 3


def test_only_needs_with_a_critical_level_press() -> None:
    grubby = pressing(needs(hygiene=1.0, rest=1.0, social=1.0))

    assert (grubby.pressure, grubby.errand, grubby.urgent) == (0, None, False)
    assert pressing(needs(hunger=0.95), {}).urgent is False


def test_moods_are_words_for_how_each_need_feels() -> None:
    assert mood(CALM) == ()
    assert mood(needs(hunger=0.8, rest=0.65)) == ("hungry", "tired")
    assert mood(needs(hunger=0.95, bladder=0.9, rest=0.9, hygiene=0.9)) == (
        "starving",
        "bursting for the loo",
        "exhausted",
        "badly in need of a shower",
    )
    assert mood(needs(bladder=0.8, hygiene=0.8)) == ("needing the loo", "feeling grubby")


def test_the_mood_line_uses_words_never_numbers() -> None:
    hungry = needs(hunger=0.93, rest=0.71, bladder=0.82)

    line = feels("you", mood(hungry))
    assert line == "Right now you're starving, needing the loo and tired."
    assert re.search(r"\d", line) is None
    assert feels("Kofi", mood(needs(hunger=0.8))) == "Right now Kofi is hungry."
    assert feels("you", ()) == ""
