import random

import pytest

from simile.behaviour import Activity, Goal
from simile.conversation import (
    DEFAULT_CONFIG,
    ConversationConfig,
    acceptance,
    accepts,
    engage,
    initial_engagement,
    leaving,
    topic_match,
)
from simile.npc import load_npcs
from simile.schema import CoreValue, Npc
from simile.social import meet

V = CoreValue
TEMPLATE = load_npcs()[0]


def values(**scores: float) -> dict[CoreValue, float]:
    return {value: scores.get(value.value, 0.5) for value in CoreValue}


def npc(**scores: float) -> Npc:
    return TEMPLATE.model_copy(update={"id": "ana", "values": values(**scores)})


def test_topics_they_care_about_match_and_ones_they_dont_clash() -> None:
    mine = values(justice=0.9, pleasure=0.1)

    assert topic_match(mine, [V.JUSTICE]) == pytest.approx(0.8)
    assert topic_match(mine, [V.PLEASURE]) == pytest.approx(-0.8)
    assert topic_match(mine, [V.JUSTICE, V.PLEASURE]) == pytest.approx(0.0)
    assert topic_match(mine, [V.JUSTICE, V.JUSTICE]) == pytest.approx(0.8)
    assert topic_match(mine, []) == 0.0


def test_engagement_rises_with_topics_they_care_about() -> None:
    mine = values(justice=0.9, pleasure=0.1)

    assert engage(0.5, mine, 0.5, [V.JUSTICE]) > 0.5
    assert engage(0.5, mine, 0.5, [V.PLEASURE]) < engage(0.5, mine, 0.5, []) < 0.5


def test_liking_the_other_slows_the_drop() -> None:
    mine = values()

    assert engage(0.5, mine, 0.9, []) > engage(0.5, mine, 0.5, []) > engage(0.5, mine, 0.1, [])


def test_engagement_stays_between_0_and_1() -> None:
    mine = values(justice=1.0, pleasure=0.0)

    assert engage(0.99, mine, 1.0, [V.JUSTICE]) == 1.0
    assert engage(0.01, mine, 0.0, [V.PLEASURE]) == 0.0


def test_they_start_keener_on_people_they_like_and_when_they_value_connection() -> None:
    assert initial_engagement(values(), 0.9) > initial_engagement(values(), 0.5)
    assert initial_engagement(values(connection=0.9), 0.5) > initial_engagement(values(), 0.5)


def test_nobody_leaves_before_min_lines() -> None:
    assert not leaving(0.0, DEFAULT_CONFIG.min_lines - 1)
    assert leaving(0.0, DEFAULT_CONFIG.min_lines)
    assert not leaving(DEFAULT_CONFIG.leave_below, DEFAULT_CONFIG.min_lines)


def test_the_goodbyes_fit_in_max_lines() -> None:
    config = ConversationConfig(max_lines=8)

    assert not leaving(1.0, 5, config)
    assert leaving(1.0, 6, config)
    assert leaving(1.0, 7, config.model_copy(update={"farewell": False}))


def lines_until_leaving(like: float) -> int:
    engagement, lines = initial_engagement(values(), like), 0
    while not leaving(engagement, lines):
        engagement = engage(engagement, values(), like, [])
        lines += 1
    return lines


def test_low_like_pairs_have_short_conversations() -> None:
    assert lines_until_leaving(0.15) < lines_until_leaving(0.5) < lines_until_leaving(0.85)
    assert lines_until_leaving(0.15) == DEFAULT_CONFIG.min_lines


def test_friends_accept_and_people_they_dislike_are_declined() -> None:
    target = npc()
    idle = Goal(Activity.IDLE)
    friend = meet(target, "ben").model_copy(update={"like": 0.85, "trust": 0.8})
    enemy = meet(target, "ben").model_copy(update={"like": 0.1, "trust": 0.2})

    assert acceptance(target.values, friend, idle, 0.5) > 0
    assert acceptance(target.values, enemy, idle, 0.5) < 0


def test_values_needs_and_goals_move_acceptance() -> None:
    rel = meet(npc(), "ben")
    idle = Goal(Activity.IDLE)
    score = acceptance(npc().values, rel, idle, 0.5)

    assert acceptance(npc(connection=0.95).values, rel, idle, 0.5) > score
    assert acceptance(npc(independence=0.95).values, rel, idle, 0.5) < score
    assert acceptance(npc().values, rel, idle, 0.9) > score
    assert acceptance(npc().values, rel, Goal(Activity.NEWS, "terminal_1"), 0.5) < score
    assert acceptance(npc().values, rel, Goal(Activity.SEEK, "ben"), 0.5) > score
    assert acceptance(npc().values, rel, Goal(Activity.SEEK, "cal"), 0.5) < score


def test_the_lonely_accept_a_stranger_and_the_content_mostly_dont() -> None:
    rel = meet(npc(), "ben")
    idle = Goal(Activity.IDLE)

    assert acceptance(npc().values, rel, idle, 0.9) > 0 > acceptance(npc().values, rel, idle, 0.1)


def test_accepting_is_a_threshold_at_temperature_0_and_a_chance_otherwise() -> None:
    sharp = ConversationConfig(accept_temperature=0)
    rng = random.Random(0)

    assert accepts(0.01, rng, sharp)
    assert not accepts(-0.01, rng, sharp)
    keen = [accepts(0.2, rng) for _ in range(1000)]
    reluctant = [accepts(-0.2, rng) for _ in range(1000)]
    assert 800 < sum(keen) < 950
    assert 50 < sum(reluctant) < 200
