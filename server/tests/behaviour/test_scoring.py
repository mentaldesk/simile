import math
import random
from collections.abc import Sequence
from dataclasses import replace

import pytest
from pydantic import ValidationError

from simile.behaviour import (
    DEFAULT_CONFIG,
    Activity,
    BehaviourConfig,
    Goal,
    MuralSpot,
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
from simile.schema import (
    PLAYER_ID,
    Baseline,
    CoreValue,
    LocationKind,
    MapTile,
    Medium,
    Relationship,
)
from simile.sim import EventBus
from simile.world.map import MapKind, load_maps, with_every_location
from simile.world.movement import Movement, Point
from simile.world.paths import DOOR

MAPS = load_maps()
PLACES = Places(with_every_location(MAPS))
SQUARE = Point(51, 15, "high_street")
CAFE_FLOOR = "coffee_shop_floor_0"
NEUTRAL = {value: 0.5 for value in CoreValue}
CONTENT = {need: 0.2 for need in Need}

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
    craft: Medium | None = None,
    mural: MuralSpot | None = None,
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
        craft,
        mural,
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


def test_open_mindedness_knowledge_and_creativity_go_to_the_gallery() -> None:
    gallery = Goal(A.GALLERY, "gallery")
    s = situation({V.OPEN_MINDEDNESS: 0.95, V.KNOWLEDGE: 0.95, V.CREATIVITY: 0.9})
    unmoved = situation({V.OPEN_MINDEDNESS: 0.1, V.KNOWLEDGE: 0.1, V.CREATIVITY: 0.1})

    assert best(s) == gallery
    assert score_of(gallery, unmoved) < score_of(gallery, s) - 0.5


def test_connection_and_loneliness_seek_someone_out() -> None:
    kofi = Other("kofi", Point(53, 15, "high_street"), affinity=0.2)
    s = situation({V.CONNECTION: 0.95}, {Need.SOCIAL: 0.9}, others=[kofi])

    assert best(s) == Goal(A.SEEK, "kofi")


def test_low_connection_does_not_seek_anyone_out() -> None:
    kofi = Other("kofi", Point(53, 15, "high_street"), affinity=0.2)
    s = situation({V.CONNECTION: 0.05, V.INDEPENDENCE: 0.9}, {Need.SOCIAL: 0.6}, others=[kofi])

    assert best(s).activity is not A.SEEK


def test_peace_of_mind_keeps_them_from_seeking_company() -> None:
    kofi = [Other("kofi", Point(53, 15, "high_street"), affinity=0.2)]
    seek = Goal(A.SEEK, "kofi")

    content = situation({V.PEACE_OF_MIND: 0.95}, others=kofi)

    assert score_of(seek, content) < score_of(seek, situation(others=kofi))


def test_a_little_loneliness_barely_registers_and_a_lot_crowds_out_the_rest() -> None:
    kofi = [Other("kofi", Point(53, 15, "high_street"), affinity=0.0)]
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


def test_every_need_has_an_urgency_curve() -> None:
    curves = {need: u for need, u in DEFAULT_CONFIG.urgency.items() if need is not Need.EXERCISE}

    with pytest.raises(ValidationError, match="exercise need an urgency curve"):
        BehaviourConfig(urgency=curves)


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
    resident = Other("kofi", Point(53, 15, "high_street"), affinity=0.0)
    player = Other(PLAYER_ID, Point(53, 15, "high_street"), affinity=0.0)
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
    friend = Other("mei", Point(54, 15, "high_street"), affinity=0.6)
    stranger = Other("kofi", Point(48, 15, "high_street"), affinity=0.0)
    s = situation({V.CONNECTION: 0.9}, {Need.SOCIAL: 0.9}, others=[stranger, friend])

    assert best(s) == Goal(A.SEEK, "mei")


def test_nobody_seeks_someone_who_is_not_available() -> None:
    busy = Other("kofi", Point(53, 15, "high_street"), affinity=0.8, available=False)
    s = situation({V.CONNECTION: 0.95}, {Need.SOCIAL: 0.9}, others=[busy])

    assert all(goal.activity is not A.SEEK for goal in scores(s, PLACES))


def test_avoids_a_place_where_someone_they_dislike_is() -> None:
    values = {V.PLEASURE: 0.9, V.CONNECTION: 0.8}
    rival = Other("viktor", Point(12, 2, CAFE_FLOOR), affinity=-0.6, place="coffee_shop")
    alone = situation(values, {Need.SOCIAL: 0.6}, hour=8.5)
    spoiled = situation(values, {Need.SOCIAL: 0.6}, hour=8.5, others=[rival])

    assert best(alone) == Goal(A.COFFEE_SHOP, "coffee_shop")
    assert best(spoiled).activity is not A.COFFEE_SHOP


def test_friends_make_a_place_more_attractive() -> None:
    friend = Other("mei", Point(12, 2, CAFE_FLOOR), affinity=0.6, place="coffee_shop")
    coffee = Goal(A.COFFEE_SHOP, "coffee_shop")

    assert score_of(coffee, situation(others=[friend])) > score_of(coffee, situation())


def test_connection_scales_the_pull_of_friends() -> None:
    friend = Other("mei", Point(12, 2, CAFE_FLOOR), affinity=0.6, place="coffee_shop")
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


def test_a_shut_daily_grind_scores_nothing_for_hunger() -> None:
    cafe, noodles = Goal(A.COFFEE_SHOP, "coffee_shop"), Goal(A.NOODLE_BAR, "noodle_bar")

    def shut(goal: Goal, need: Need) -> float:
        return 0.0 if goal == cafe and need is Need.HUNGER else 1.0

    hungry, full = situation(needs={Need.HUNGER: 0.9}), situation(needs={Need.HUNGER: 0.0})

    def hunger_term(goal: Goal, closed: bool) -> float:
        def at(s: Situation) -> float:
            return score_of(goal, replace(s, supply=shut) if closed else s)

        return at(hungry) - at(full)

    assert hunger_term(cafe, closed=False) > 0.5
    assert hunger_term(cafe, closed=True) == 0.0
    assert hunger_term(noodles, closed=True) == hunger_term(noodles, closed=False) > 0.5


def test_hunger_not_the_clock_sends_them_to_eat() -> None:
    noodles = Goal(A.NOODLE_BAR, "noodle_bar")
    hungry = {Need.HUNGER: 0.85}

    assert score_of(noodles, situation(hour=12.5)) == score_of(noodles, situation(hour=16))
    assert score_of(noodles, situation(needs=hungry, hour=16)) > score_of(
        noodles, situation(hour=12.5)
    )
    assert best(situation(needs=hungry, hour=16)).activity in (A.NOODLE_BAR, A.COFFEE_SHOP, A.HOME)


def test_the_activity_just_finished_scores_less() -> None:
    news = Goal(A.NEWS, "terminal_1")
    after_reading = situation(last=Goal(A.NEWS, "terminal_2"))

    assert score_of(news, after_reading) < score_of(news, situation())


def test_further_places_score_less() -> None:
    news = Goal(A.NEWS, "terminal_3")

    assert score_of(news, situation(position=Point(60, 18, "banyan_row"))) > score_of(
        news, situation(position=Point(3, 2, "house_1_floor_0"))
    )


def test_needs_raise_the_activities_that_meet_them() -> None:
    seek = Goal(A.SEEK, "kofi")
    kofi = [Other("kofi", Point(53, 15, "high_street"), affinity=0.0)]

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
        A.GALLERY,
        A.WANDER,
        A.IDLE,
        A.EXERCISE,
    }
    assert sum(goal.activity is A.EXERCISE for goal in options) == len(DEFAULT_CONFIG.loops)


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


INSPIRED = {Need.INSPIRATION: 0.9}
WALL = MuralSpot("wall_a", MapTile(map="high_street", x=22, y=15))


def creating(s: Situation) -> list[Goal]:
    return [goal for goal in scores(s, PLACES) if goal.activity is A.CREATE]


def test_only_crafters_create_and_muralists_only_with_a_wall() -> None:
    assert creating(situation(needs=INSPIRED)) == []
    assert creating(situation(needs=INSPIRED, craft=Medium.MURAL)) == []
    assert creating(situation(needs=INSPIRED, craft=Medium.MURAL, mural=WALL)) == [
        Goal(A.CREATE, "wall_a")
    ]
    assert {goal.target for goal in creating(situation(needs=INSPIRED, craft=Medium.WRITING))} == {
        "house_1",
        "coffee_shop",
        "maker_space",
    }


def test_painters_paint_where_writers_write() -> None:
    painting = creating(situation(needs=INSPIRED, craft=Medium.PAINTING))
    writing = creating(situation(needs=INSPIRED, craft=Medium.WRITING))

    assert painting == writing
    assert best(situation(needs=INSPIRED, craft=Medium.PAINTING)).activity is A.CREATE


@pytest.mark.parametrize(
    ("values", "place"),
    [
        ({V.PEACE_OF_MIND: 0.9, V.INDEPENDENCE: 0.9}, "house_1"),
        ({V.CONNECTION: 0.9, V.PLEASURE: 0.8}, "coffee_shop"),
        ({V.AMBITION: 0.95, V.SUCCESS: 0.9}, "maker_space"),
    ],
)
def test_writers_write_where_their_values_fit(values: dict[CoreValue, float], place: str) -> None:
    s = situation(values, INSPIRED, craft=Medium.WRITING)

    assert best(s) == Goal(A.CREATE, place)


def test_creativity_alone_does_not_send_writers_to_the_maker_space() -> None:
    s = situation({V.CREATIVITY: 0.95, V.SELF_ACTUALIZATION: 0.9}, INSPIRED, craft=Medium.WRITING)

    assert best(s).activity is A.CREATE
    assert best(s).target != "maker_space"


def test_inspiration_barely_registers_until_it_builds() -> None:
    def pull(need: float) -> float:
        s = situation(needs={Need.INSPIRATION: need}, craft=Medium.MURAL, mural=WALL)
        return score_of(Goal(A.CREATE, "wall_a"), s)

    assert pull(0.9) - pull(0.6) > 2 * (pull(0.6) - pull(0.3)) > 0
    assert best(situation(needs={Need.INSPIRATION: 0.3}, craft=Medium.MURAL, mural=WALL)) != (
        Goal(A.CREATE, "wall_a")
    )
    assert best(situation(needs=INSPIRED, craft=Medium.MURAL, mural=WALL)) == Goal(
        A.CREATE, "wall_a"
    )


def test_a_farther_wall_scores_less() -> None:
    near = MuralSpot("near", MapTile(map="high_street", x=52, y=15))
    far = MuralSpot("far", MapTile(map="high_street", x=22, y=15))

    def pull(spot: MuralSpot) -> float:
        s = situation(needs=INSPIRED, craft=Medium.MURAL, mural=spot)
        return score_of(Goal(A.CREATE, spot.wall), s)

    assert pull(near) > pull(far)


def test_nobody_starts_making_something_just_before_bed() -> None:
    assert creating(situation(needs=INSPIRED, craft=Medium.WRITING, hour=20.5))
    assert creating(situation(needs=INSPIRED, craft=Medium.WRITING, hour=22)) == []


def test_finishing_counts_towards_what_a_stay_promises() -> None:
    assert promised(A.CREATE, Need.INSPIRATION) == -1.0
    assert promised(A.CREATE, Need.CURIOSITY) == pytest.approx(-0.6 * (20 + 45) / 2 / 60)


def test_places_are_looked_up_on_the_points_own_map() -> None:
    cafe = Places(MAPS[CAFE_FLOOR])

    assert PLACES.at(Point(3, 2, "house_1_floor_0")) == PLACES.location("house_1")
    assert PLACES.at(Point(3, 2, CAFE_FLOOR)) == PLACES.location("coffee_shop")
    assert cafe.at(Point(3, 2, CAFE_FLOOR)) == cafe.location("coffee_shop")
    assert cafe.at(Point(3, 2, "house_1_floor_0")) is None


def test_residents_at_the_counter_or_behind_it_are_at_the_coffee_shop() -> None:
    cafe = Places(MAPS[CAFE_FLOOR])
    coffee_shop = cafe.location("coffee_shop")

    for spot in ("coffee_shop_queue", "coffee_shop_staff"):
        entry = cafe.location(spot).entry
        assert cafe.at(Point(entry.x, entry.y, coffee_shop.map)) == coffee_shop
    assert PLACES.at(Point(47, 15, "lychee_lane")) == PLACES.location("park")


@pytest.mark.parametrize(
    "activity", [A.COFFEE_SHOP, A.NOODLE_BAR, A.MAKER_SPACE, A.GALLERY], ids=str
)
def test_each_building_is_inside_on_its_own_floors_under_its_own_kind(activity: Activity) -> None:
    [location] = PLACES.by_activity[activity]
    ground = MAPS[location.map]

    assert location.id == ground.building == activity.value
    assert (ground.kind, ground.floor) == (MapKind.FLOOR, 0)
    assert location.kind is LocationKind(activity.value)


def door(id: str) -> tuple[Point, Point]:
    """The door's tiles outside and inside."""
    found = next(d for d in PLACES.town.doors if d.id == id)
    outside, inside = found.outside, found.inside
    return Point(outside.x, outside.y, outside.map), Point(inside.x, inside.y, inside.map)


def test_trips_inside_are_priced_through_the_door() -> None:
    cafe, noodles = PLACES.location("coffee_shop"), PLACES.location("noodle_bar")
    counter = Point(cafe.entry.x, cafe.entry.y, cafe.map)
    bowl = Point(noodles.entry.x, noodles.entry.y, noodles.map)
    (cafe_out, cafe_in), (noodles_out, noodles_in) = door("coffee_shop"), door("noodle_bar")

    assert PLACES.tiles(SQUARE, counter) == pytest.approx(
        math.dist(SQUARE, cafe_out) + DOOR + math.dist(cafe_in, counter)
    )
    assert PLACES.tiles(counter, bowl) == pytest.approx(
        math.dist(counter, cafe_in)
        + DOOR
        + math.dist(cafe_out, noodles_out)
        + DOOR
        + math.dist(noodles_in, bowl)
    )


def test_a_trip_inside_is_priced_about_as_long_as_the_walk() -> None:
    movement = Movement(MAPS, EventBus())
    movement.place("mei", MapTile(map="high_street", x=51, y=15))
    cafe = PLACES.location("coffee_shop")

    walk = movement.walk_to("mei", "coffee_shop")
    estimate = PLACES.tiles(SQUARE, Point(cafe.entry.x, cafe.entry.y, cafe.map))

    assert estimate <= walk.distance <= 1.2 * estimate


def test_a_map_without_a_door_is_out_of_reach() -> None:
    shut = Places(replace(with_every_location(MAPS), doors=()))

    terrace = Point(35, 15, "high_street")
    assert shut.walk_minutes(SQUARE, Point(12, 2, CAFE_FLOOR)) == math.inf
    assert shut.walk_minutes(SQUARE, Point(47, 15, "lychee_lane")) == math.inf
    assert shut.walk_minutes(SQUARE, terrace) == PLACES.walk_minutes(SQUARE, terrace)


def test_nobody_starts_making_something_with_an_urgent_need() -> None:
    inspired = {Need.INSPIRATION: 0.9}
    calm = situation(needs=inspired, craft=Medium.WRITING)
    starving = situation(needs=inspired | {Need.HUNGER: 0.95}, craft=Medium.WRITING)

    assert any(goal.activity is A.CREATE for goal in scores(calm, PLACES))
    assert not any(goal.activity is A.CREATE for goal in scores(starving, PLACES))


def test_staying_on_where_nothing_is_relieved_is_worth_less_than_coming_fresh() -> None:
    park = Goal(A.PARK, "park")
    s = situation(position=Point(55, 15, "lychee_lane"))

    assert score(park, s, PLACES, staying=True) < score(park, s, PLACES)
