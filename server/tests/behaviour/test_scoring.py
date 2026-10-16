import random
from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from simile.behaviour import (
    DEFAULT_CONFIG,
    Activity,
    BehaviourConfig,
    Goal,
    Need,
    Other,
    Places,
    Situation,
    choose,
    score,
    scores,
)
from simile.behaviour.scoring import (
    affinity,
    asleep,
    bedtime,
    best_per_activity,
    curve,
    promised,
    relief,
    wake,
)
from simile.schema import PLAYER_ID, Baseline, CoreValue, Relationship
from simile.world.map import load_map
from simile.world.movement import Point

PLACES = Places(load_map())
SQUARE = Point(31, 22)
NEUTRAL = {value: 0.5 for value in CoreValue}
CONTENT = {Need.SOCIAL: 0.2, Need.CURIOSITY: 0.2, Need.REST: 0.2, Need.NEWS: 0.2}

V = CoreValue
A = Activity


def situation(
    values: dict[CoreValue, float] | None = None,
    needs: dict[Need, float] | None = None,
    *,
    hour: float = 11.0,
    others: Sequence[Other] = (),
    last: Goal | None = None,
    position: Point = SQUARE,
    news: float = 0.0,
) -> Situation:
    return Situation(
        {**NEUTRAL, **(values or {})},
        {**CONTENT, **(needs or {})},
        hour,
        position,
        "house_1",
        22.5,
        others,
        last,
        news,
    )


def best(s: Situation) -> Goal:
    return choose(scores(s, PLACES), random.Random(0), 0)


def score_of(goal: Goal, s: Situation) -> float:
    return score(goal, s, PLACES)


def test_wanting_the_news_and_a_good_article_send_npcs_to_the_nearest_terminal() -> None:
    s = situation(needs={Need.NEWS: 0.9}, news=0.8)

    assert best(s) == Goal(A.NEWS, "terminal_1")


def test_nothing_worth_reading_keeps_them_from_the_terminals() -> None:
    s = situation(needs={Need.NEWS: 1.0}, news=0.0)

    assert all(goal.activity is not A.NEWS for goal in scores(s, PLACES))


def test_a_gripping_article_pulls_harder_than_a_so_so_one() -> None:
    news = Goal(A.NEWS, "terminal_1")

    def pull(interest: float) -> float:
        return score_of(news, situation(needs={Need.NEWS: 0.7}, news=interest))

    assert pull(1.0) > pull(0.6) > pull(0.1)


def test_wanting_the_news_barely_registers_until_it_builds() -> None:
    news = Goal(A.NEWS, "terminal_1")

    def pull(need: float) -> float:
        return score_of(news, situation(needs={Need.NEWS: need}, news=1.0))

    assert pull(0.9) - pull(0.6) > 2 * (pull(0.6) - pull(0.3)) > 0
    assert best(situation(needs={Need.NEWS: 0.2}, news=1.0)).activity is not A.NEWS


def test_peace_of_mind_and_tiredness_send_npcs_home() -> None:
    s = situation({V.PEACE_OF_MIND: 0.95, V.SECURITY: 0.9}, {Need.REST: 0.9})

    assert best(s) == Goal(A.HOME, "house_1")


def test_peace_of_mind_without_tiredness_prefers_the_park_in_the_afternoon() -> None:
    s = situation({V.PEACE_OF_MIND: 0.95, V.FREEDOM: 0.8}, hour=15)

    assert best(s) == Goal(A.PARK, "park")


def test_adventure_wanders() -> None:
    s = situation({V.ADVENTURE: 0.95, V.FREEDOM: 0.9, V.SECURITY: 0.1})

    assert best(s) == Goal(A.WANDER)


def test_creativity_goes_to_the_maker_space() -> None:
    s = situation({V.CREATIVITY: 0.95, V.SELF_ACTUALIZATION: 0.9}, {Need.CURIOSITY: 0.6})

    assert best(s) == Goal(A.MAKER_SPACE, "maker_space")


def test_connection_and_loneliness_seek_someone_out() -> None:
    kofi = Other("kofi", Point(33, 24), affinity=0.2)
    s = situation({V.CONNECTION: 0.95}, {Need.SOCIAL: 0.9}, others=[kofi])

    assert best(s) == Goal(A.SEEK, "kofi")


def test_low_connection_does_not_seek_anyone_out() -> None:
    kofi = Other("kofi", Point(33, 24), affinity=0.2)
    s = situation({V.CONNECTION: 0.05, V.INDEPENDENCE: 0.9}, {Need.SOCIAL: 0.6}, others=[kofi])

    assert best(s).activity is not A.SEEK


def test_peace_of_mind_keeps_them_from_seeking_company() -> None:
    kofi = [Other("kofi", Point(33, 24), affinity=0.2)]
    seek = Goal(A.SEEK, "kofi")

    content = situation({V.PEACE_OF_MIND: 0.95}, others=kofi)

    assert score_of(seek, content) < score_of(seek, situation(others=kofi))


def test_a_little_loneliness_barely_registers_and_a_lot_crowds_out_the_rest() -> None:
    kofi = [Other("kofi", Point(33, 24), affinity=0.0)]
    seek = Goal(A.SEEK, "kofi")

    def pull(social: float) -> float:
        return score_of(seek, situation(needs={Need.SOCIAL: social}, others=kofi))

    assert pull(0.9) - pull(0.7) > 4 * (pull(0.5) - pull(0.3)) > 0
    assert best(situation({V.CONNECTION: 0.7}, {Need.SOCIAL: 0.9}, others=kofi)) == seek


def test_the_same_relief_is_worth_far_more_to_someone_desperate() -> None:
    assert relief(0.9, -0.6, 3) == pytest.approx((0.9**4 - 0.3**4) / 4)
    assert relief(0.3, -0.6, 3) == pytest.approx(0.3**4 / 4)
    assert relief(0.9, -0.6, 3) > 50 * relief(0.3, -0.6, 3)
    assert relief(0.5, 0.0, 3) == 0.0
    assert relief(0.5, 0.2, 1) == pytest.approx((0.5**2 - 0.7**2) / 2)


def test_a_need_is_priced_by_its_curve_or_its_weights_not_both() -> None:
    weights = {**DEFAULT_CONFIG.need_weights, A.SEEK: {Need.SOCIAL: 1.0}}

    with pytest.raises(ValidationError, match="social can't be in both"):
        BehaviourConfig(need_weights=weights)


def test_seeking_someone_out_promises_a_talk() -> None:
    config = DEFAULT_CONFIG
    talk = config.effects[A.TALK][Need.SOCIAL] * config.talk_minutes / 60
    stay = sum(config.dwell[A.COFFEE_SHOP]) / 2 / 60

    assert promised(A.SEEK, Need.SOCIAL) == pytest.approx(talk)
    assert promised(A.COFFEE_SHOP, Need.SOCIAL) == pytest.approx(
        config.effects[A.COFFEE_SHOP][Need.SOCIAL] * stay
    )
    assert promised(A.MAKER_SPACE, Need.SOCIAL) == 0.0
    assert promised(A.SEEK, Need.SOCIAL) < promised(A.COFFEE_SHOP, Need.SOCIAL) < 0


def test_seeking_the_player_promises_less_relief_than_seeking_a_resident() -> None:
    resident = Other("kofi", Point(33, 24), affinity=0.0)
    player = Other(PLAYER_ID, Point(33, 24), affinity=0.0)
    s = situation({V.CONNECTION: 0.9}, {Need.SOCIAL: 0.8}, others=[resident, player])
    urgency, talk = DEFAULT_CONFIG.urgency[Need.SOCIAL], promised(A.SEEK, Need.SOCIAL)
    halved = talk * DEFAULT_CONFIG.player_relief

    gap = urgency.weight * (relief(0.8, talk, urgency.power) - relief(0.8, halved, urgency.power))
    assert gap > 0
    assert score_of(Goal(A.SEEK, "kofi"), s) - score_of(Goal(A.SEEK, PLAYER_ID), s) == (
        pytest.approx(gap)
    )

    same = DEFAULT_CONFIG.model_copy(update={"player_relief": 1.0})
    assert score(Goal(A.SEEK, PLAYER_ID), s, PLACES, same) == pytest.approx(
        score(Goal(A.SEEK, "kofi"), s, PLACES, same)
    )


def test_seeks_a_friend_over_a_stranger() -> None:
    friend = Other("mei", Point(34, 24), affinity=0.6)
    stranger = Other("kofi", Point(28, 20), affinity=0.0)
    s = situation({V.CONNECTION: 0.9}, {Need.SOCIAL: 0.9}, others=[stranger, friend])

    assert best(s) == Goal(A.SEEK, "mei")


def test_nobody_seeks_someone_who_is_not_available() -> None:
    busy = Other("kofi", Point(33, 24), affinity=0.8, available=False)
    s = situation({V.CONNECTION: 0.95}, {Need.SOCIAL: 0.9}, others=[busy])

    assert all(goal.activity is not A.SEEK for goal in scores(s, PLACES))


def test_avoids_a_place_where_someone_they_dislike_is() -> None:
    values = {V.PLEASURE: 0.9, V.CONNECTION: 0.8}
    rival = Other("viktor", Point(31, 9), affinity=-0.6, place="coffee_shop")
    alone = situation(values, {Need.SOCIAL: 0.6}, hour=8.5)
    spoiled = situation(values, {Need.SOCIAL: 0.6}, hour=8.5, others=[rival])

    assert best(alone) == Goal(A.COFFEE_SHOP, "coffee_shop")
    assert best(spoiled).activity is not A.COFFEE_SHOP


def test_friends_make_a_place_more_attractive() -> None:
    friend = Other("mei", Point(31, 9), affinity=0.6, place="coffee_shop")
    coffee = Goal(A.COFFEE_SHOP, "coffee_shop")

    assert score_of(coffee, situation(others=[friend])) > score_of(coffee, situation())


def test_connection_scales_the_pull_of_friends() -> None:
    friend = Other("mei", Point(31, 9), affinity=0.6, place="coffee_shop")
    coffee = Goal(A.COFFEE_SHOP, "coffee_shop")

    def gain(connection: float) -> float:
        values = {V.CONNECTION: connection}
        return score_of(coffee, situation(values, others=[friend])) - score_of(
            coffee, situation(values)
        )

    assert gain(0.9) > gain(0.1)


def test_home_pulls_harder_towards_bedtime() -> None:
    home = Goal(A.HOME, "house_1")

    assert (
        score_of(home, situation(hour=22))
        > score_of(home, situation(hour=21))
        > score_of(home, situation(hour=15))
    )


def test_time_of_day_favours_lunch_at_the_noodle_bar() -> None:
    noodles = Goal(A.NOODLE_BAR, "noodle_bar")

    assert score_of(noodles, situation(hour=12.5)) > score_of(noodles, situation(hour=16))


def test_the_activity_just_finished_scores_less() -> None:
    news = Goal(A.NEWS, "terminal_1")
    after_reading = situation(last=Goal(A.NEWS, "terminal_2"))

    assert score_of(news, after_reading) < score_of(news, situation())


def test_further_places_score_less() -> None:
    news = Goal(A.NEWS, "terminal_3")

    assert score_of(news, situation(position=Point(46, 36))) > score_of(
        news, situation(position=Point(3, 11))
    )


def test_needs_raise_the_activities_that_meet_them() -> None:
    seek = Goal(A.SEEK, "kofi")
    kofi = [Other("kofi", Point(33, 24), affinity=0.0)]

    lonely = situation({}, {Need.SOCIAL: 0.9}, others=kofi)
    content = situation({}, {Need.SOCIAL: 0.1}, others=kofi)

    assert score_of(seek, lonely) > score_of(seek, content)


def test_each_activity_is_offered_once_with_its_best_place() -> None:
    options = scores(situation(news=0.5), PLACES)
    best = best_per_activity(options)

    assert sum(goal.activity is A.NEWS for goal in options) == 3
    assert best[A.NEWS][0] == Goal(A.NEWS, "terminal_1")
    assert set(best) == {
        A.HOME,
        A.COFFEE_SHOP,
        A.SQUARE,
        A.NEWS,
        A.PARK,
        A.NOODLE_BAR,
        A.MAKER_SPACE,
        A.WANDER,
        A.IDLE,
    }


def test_choice_is_random_but_seeded() -> None:
    options = scores(situation(), PLACES)

    def picks(seed: int) -> list[Goal]:
        rng = random.Random(seed)
        return [choose(options, rng, 0.1) for _ in range(50)]

    assert picks(1) == picks(1)
    assert len({goal.activity for goal in picks(1)}) > 1


def test_zero_temperature_always_picks_the_best() -> None:
    options = {Goal(A.IDLE): 0.1, Goal(A.WANDER): 0.3, Goal(A.NEWS, "terminal_1"): 0.2}

    assert {choose(options, random.Random(seed), 0) for seed in range(10)} == {Goal(A.WANDER)}


def test_affinity_ranks_friends_strangers_and_enemies() -> None:
    def rel(score: float, familiarity: float) -> Relationship:
        baseline = Baseline(like=0.5, trust=0.5, respect=0.5)
        return Relationship(
            owner="mei",
            about="kofi",
            like=score,
            trust=score,
            respect=score,
            familiarity=familiarity,
            baseline=baseline,
        )

    assert affinity(rel(0.9, 0.8)) > affinity(rel(0.5, 0.0)) == 0 > affinity(rel(0.1, 0.8))


def test_discipline_keeps_early_hours_and_pleasure_late_ones() -> None:
    early = {**NEUTRAL, V.DISCIPLINE: 0.95, V.RESPONSIBILITY: 0.9}
    late = {**NEUTRAL, V.PLEASURE: 0.95, V.ADVENTURE: 0.9, V.DISCIPLINE: 0.05}

    assert bedtime(early) < bedtime(NEUTRAL) < bedtime(late) <= 23.75
    assert 5.5 <= wake(early) < wake(NEUTRAL) < wake(late)


@pytest.mark.parametrize(
    ("hour", "sleeping"), [(3, True), (6.5, True), (7, False), (15, False), (22.5, True)]
)
def test_asleep_between_bedtime_and_waking(hour: float, sleeping: bool) -> None:
    assert asleep(hour, 22.5, 7) is sleeping


def test_curve_is_linear_between_points_and_zero_outside() -> None:
    points = ((8.0, 0.0), (10.0, 0.4), (12.0, 0.0))

    assert [curve(points, h) for h in (7, 8, 9, 10, 11, 12, 13)] == pytest.approx(
        [0, 0, 0.2, 0.4, 0.2, 0, 0]
    )
