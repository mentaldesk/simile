from datetime import datetime, timedelta

import pytest

from simile.behaviour import (
    DEFAULT_CONFIG,
    Activity,
    Goal,
    IntentionBroken,
    IntentionKept,
    MuralSpot,
    Need,
    lapse_chance,
    reliability,
)
from simile.behaviour.intentions import boosted, deed, matches, when
from simile.schema import PLAYER_ID, CoreValue, Intention, IntentionKind, MapTile, Npc

from .test_mind import ANA, BEN, PAINTER, WALL, WRITER, Village, at

A = Activity
K = IntentionKind
STEADY = DEFAULT_CONFIG.model_copy(update={"temperature": 0.0, "head_starts": 0})
NEUTRAL = dict.fromkeys(CoreValue, 0.5)
COFFEE = "a mural of an ocean of coffee with cups half-sunk in it"


def promise(
    owner: str,
    kind: K,
    target: str | None = None,
    *,
    now: datetime,
    due: timedelta = timedelta(),
    lasts: timedelta = timedelta(hours=2),
    promised_to: tuple[str, ...] = (PLAYER_ID,),
    description: str = COFFEE,
    n: int = 1,
) -> Intention:
    return Intention(
        id=f"talk/{owner}/{n}",
        owner=owner,
        kind=kind,
        target=target,
        description=description,
        promised_to=list(promised_to),
        created=now,
        due=now + due,
        expires=now + due + lasts,
        conversation_id="talk",
    )


class Recorder:
    def __init__(self, village: Village) -> None:
        self.village = village
        self.works: list[tuple[str, str | None, Intention | None]] = []
        self.kept: list[Intention] = []
        self.broken: list[tuple[datetime, Intention]] = []
        bus = village.world.bus
        bus.subscribe(IntentionKept, lambda event: self.kept.append(event.intention))
        bus.subscribe(
            IntentionBroken, lambda event: self.broken.append((village.clock.now, event.intention))
        )

    def __call__(self, npc: Npc, wall: str | None, intention: Intention | None = None) -> None:
        self.works.append((npc.id, wall, intention))


def painting(village: Village) -> Recorder:
    recorder = Recorder(village)
    village.behaviour.hooks.set(create=recorder, mural_wall=lambda npc: WALL)
    village.behaviour.minds["pia"].needs[Need.INSPIRATION] = 0.1
    return recorder


def test_a_muralist_who_says_they_will_paint_it_now_goes_and_paints_it() -> None:
    village = Village([PAINTER], start=at(10), config=STEADY)
    seen = painting(village)
    village.run(minutes=5)
    assert village.behaviour.goal("pia").activity is not A.CREATE
    said = promise("pia", K.CREATE, "wall_a", now=village.clock.now)

    assert village.behaviour.intend(said)
    village.run(minutes=0.2)

    assert village.behaviour.goal("pia") == Goal(A.CREATE, "wall_a")
    assert village.behaviour.needs("pia")[Need.INSPIRATION] >= DEFAULT_CONFIG.inspiration_start
    village.run_until(lambda: village.behaviour.minds["pia"].walk is None)
    assert seen.kept == [said]
    assert village.behaviour.intentions("pia") == []
    village.run_until(lambda: bool(seen.works), minutes=90)
    assert seen.works == [("pia", "wall_a", said)]


def test_the_next_work_they_make_keeps_one_due_later_and_is_that_idea() -> None:
    village = Village([PAINTER], start=at(10), config=STEADY)
    seen = painting(village)
    village.behaviour.minds["pia"].needs[Need.INSPIRATION] = 0.95
    said = promise("pia", K.CREATE, now=village.clock.now, due=timedelta(hours=20))

    village.behaviour.intend(said)
    village.run_until(lambda: bool(seen.works), minutes=120)

    assert seen.kept == [said]
    assert seen.works == [("pia", "wall_a", said)]
    assert village.behaviour.intentions("pia") == []


def test_one_said_while_already_making_something_is_that_work() -> None:
    village = Village([PAINTER], start=at(10), config=STEADY)
    seen = painting(village)
    now = village.clock.now
    needs = village.behaviour.needs("pia")
    village.behaviour.restore(
        "pia", Goal(A.CREATE, "wall_a"), needs, now, now + timedelta(minutes=30), {}
    )
    said = promise("pia", K.CREATE, now=now, due=timedelta(minutes=20))

    village.behaviour.intend(said)

    assert seen.kept == [said]
    village.run(minutes=31)
    assert seen.works == [("pia", "wall_a", said)]


def test_going_somewhere_long_before_its_due_doesnt_keep_it() -> None:
    village = Village([ANA], start=at(10), config=STEADY)
    seen = Recorder(village)
    later = promise("ana", K.GO, "noodle_bar", now=village.clock.now, due=timedelta(hours=5))
    village.behaviour.intend(later)

    village.behaviour.nudge("ana", Goal(A.NOODLE_BAR, "noodle_bar"), 50.0)
    village.run_until(lambda: village.behaviour.goal("ana") == Goal(A.NOODLE_BAR, "noodle_bar"))
    village.run_until(lambda: village.behaviour.minds["ana"].walk is None)

    assert seen.kept == []
    assert village.behaviour.intentions("ana") == [later]


def test_an_urgent_need_comes_first_and_then_they_keep_it() -> None:
    village = Village([PAINTER], start=at(10), config=STEADY)
    seen = painting(village)
    village.run(minutes=5)
    village.behaviour.minds["pia"].needs[Need.HUNGER] = 0.95

    village.behaviour.intend(promise("pia", K.CREATE, now=village.clock.now))
    village.run(minutes=0.2)

    assert village.behaviour.goal("pia").activity in (A.HOME, A.NOODLE_BAR, A.COFFEE_SHOP)
    assert village.behaviour.minds["pia"].reasons == {}
    village.run_until(lambda: village.behaviour.goal("pia").activity is A.CREATE, minutes=110)
    assert village.behaviour.needs("pia")[Need.HUNGER] < 0.9
    assert not seen.broken


def test_an_intention_left_undone_expires_and_is_broken() -> None:
    village = Village([PAINTER], start=at(10), config=STEADY)
    seen = Recorder(village)
    said = promise("pia", K.CREATE, now=village.clock.now)

    village.behaviour.intend(said)
    village.run(minutes=119)
    assert village.behaviour.intentions("pia") == [said]
    village.run(minutes=1.1)

    assert village.behaviour.intentions("pia") == []
    assert [intention for _, intention in seen.broken] == [said]
    assert seen.broken[0][0] - said.expires < timedelta(seconds=DEFAULT_CONFIG.think_every + 1)
    assert seen.kept == []


def test_going_somewhere_is_kept_on_arrival_and_the_overlay_says_why() -> None:
    village = Village([ANA], start=at(10), config=STEADY)
    seen = Recorder(village)
    said = promise("ana", K.GO, "noodle_bar", now=village.clock.now, description="get noodles")

    village.behaviour.intend(said)
    state = village.behaviour.state("ana")
    assert state["intentions"] == [
        {
            "kind": "go",
            "target": "noodle_bar",
            "description": "get noodles",
            "promised_to": [PLAYER_ID],
            "due": said.due.isoformat(),
            "expires": said.expires.isoformat(),
            "following": None,
        }
    ]
    village.run(minutes=0.2)

    assert village.behaviour.goal("ana") == Goal(A.NOODLE_BAR, "noodle_bar")
    reasons = village.behaviour.state("ana")["reasons"]
    assert isinstance(reasons, dict)
    assert reasons["noodle_bar noodle_bar"] == {
        "bonus": DEFAULT_CONFIG.promise_weight,
        "kind": "go",
        "target": "noodle_bar",
        "description": "get noodles",
        "promised_to": [PLAYER_ID],
        "due": said.due.isoformat(),
        "expires": said.expires.isoformat(),
    }
    village.run_until(lambda: village.behaviour.minds["ana"].walk is None)
    assert seen.kept == [said]
    assert village.behaviour.state("ana")["intentions"] == []


def test_looking_someone_up_is_kept_once_they_talk() -> None:
    village = Village([ANA, BEN], start=at(10), config=STEADY, placed={"ben": "square"})
    now = village.clock.now
    needs = village.behaviour.needs("ben")
    village.behaviour.restore(
        "ben", Goal(A.SQUARE, "square"), needs, now, now + timedelta(hours=2), {}
    )
    talks: list[tuple[str, str]] = []
    village.behaviour.hooks.set(request_conversation=lambda a, b: talks.append((a, b)) or True)
    seen = Recorder(village)
    said = promise("ana", K.SEEK, "ben", now=now, promised_to=("ben",), description="see Ben")

    village.behaviour.intend(said)
    village.run_until(lambda: bool(talks), minutes=30)

    assert talks == [("ana", "ben")]
    assert seen.kept == [said]


def test_someone_who_lets_it_slide_gets_no_bonus() -> None:
    config = STEADY.model_copy(update={"lapse": 1.0, "reliable_from": 1.0})
    lax = {CoreValue.RESPONSIBILITY: 0.0, CoreValue.DISCIPLINE: 0.0}
    ana = ANA.model_copy(update={"values": ANA.values | lax})
    village = Village([ana], start=at(10), config=config)
    said = promise("ana", K.GO, "noodle_bar", now=village.clock.now)

    village.behaviour.intend(said)
    village.run(minutes=0.2)

    assert village.behaviour.minds["ana"].reasons == {}
    [row] = village.behaviour.state("ana")["intentions"]  # type: ignore[misc]
    assert row["following"] is False  # type: ignore[index]


def test_the_least_reliable_let_intentions_slide_now_and_then() -> None:
    lax = NEUTRAL | {CoreValue.RESPONSIBILITY: 0.0, CoreValue.DISCIPLINE: 0.0}
    middling = NEUTRAL | {CoreValue.RESPONSIBILITY: 0.3, CoreValue.DISCIPLINE: 0.2}

    assert reliability(NEUTRAL) == pytest.approx(0.5)
    assert lapse_chance(lax) == pytest.approx(DEFAULT_CONFIG.lapse)
    assert 0 < lapse_chance(middling) < DEFAULT_CONFIG.lapse
    assert lapse_chance(NEUTRAL) == 0
    assert lapse_chance(NEUTRAL | {CoreValue.RESPONSIBILITY: 0.9}) == 0


def test_b1_takes_on_only_what_it_can_act_on() -> None:
    village = Village([ANA, BEN, WRITER], start=at(10), config=STEADY)
    now = village.clock.now
    intend = village.behaviour.intend

    assert not intend(promise("ana", K.GO, "house_5", now=now))
    assert not intend(promise("ana", K.SEEK, "zed", now=now))
    assert not intend(promise("ana", K.CREATE, now=now))
    assert not intend(promise("ana", K.NEWS, "terminal_9", now=now))
    assert not intend(promise("zed", K.GO, "park", now=now))
    gone = promise("ana", K.GO, "park", now=now - timedelta(hours=3))
    assert not intend(gone)

    assert intend(promise("ana", K.GO, "park", now=now))
    assert not intend(promise("ana", K.GO, "park", now=now, n=2))
    assert intend(promise("ana", K.SEEK, PLAYER_ID, now=now, n=3))
    assert intend(promise("ana", K.NEWS, now=now, n=4))
    assert not intend(promise("ana", K.SEEK, "ben", now=now, n=5))
    assert intend(promise("wren", K.CREATE, "coffee_shop", now=now))
    assert len(village.behaviour.intentions()) == 4


def test_options_say_where_they_can_go_and_make_something() -> None:
    village = Village([ANA, WRITER, PAINTER], start=at(10), config=STEADY)
    behaviour = village.behaviour

    ana = behaviour.options("ana")
    assert ana.places["house_1"] == "home"
    assert ana.places["coffee_shop"] == "The Daily Grind"
    assert {"square", "park", "noodle_bar", "maker_space", "gallery"} <= set(ana.places)
    assert set(ana.terminals) == {"terminal_1", "terminal_2", "terminal_3"}
    assert (ana.medium, ana.making) == (None, {})
    assert list(behaviour.options("wren").making) == ["house_1", "coffee_shop", "maker_space"]

    assert behaviour.options("pia").making == {}
    behaviour.hooks.set(mural_wall=lambda npc: WALL)
    assert behaviour.options("pia").making == {"wall_a": "the wall a wall"}
    behaviour.hooks.set(
        mural_wall=lambda npc: MuralSpot("house_2", MapTile(map="lychee_lane", x=12, y=15))
    )
    assert behaviour.options("pia").making == {"house_2": "home"}


def test_restored_intentions_are_open_again_for_residents_still_here() -> None:
    village = Village([ANA], start=at(10), config=STEADY)
    now = village.clock.now
    kept = promise("ana", K.GO, "park", now=now, due=timedelta(hours=1))
    gone = promise("zed", K.GO, "park", now=now)
    stale = promise("ana", K.NEWS, now=now - timedelta(hours=5))

    village.behaviour.restore_intentions([kept, gone, stale])

    assert village.behaviour.intentions() == [kept]


def test_what_an_intention_matches_and_raises() -> None:
    now = at(10)
    wall = promise("pia", K.CREATE, "wall_a", now=now)
    anywhere = promise("pia", K.CREATE, now=now)
    news = promise("ana", K.NEWS, now=now)
    goals = [Goal(A.CREATE, "wall_b"), Goal(A.CREATE, "wall_a"), Goal(A.NEWS, "terminal_1")]

    assert boosted(wall, goals) == [Goal(A.CREATE, "wall_a")]
    assert boosted(anywhere, goals) == goals[:2]
    assert boosted(wall, goals[:1]) == goals[:1]
    assert boosted(news, goals) == goals[2:]
    assert matches(promise("ana", K.GO, "park", now=now), Goal(A.PARK, "park"))
    assert not matches(promise("ana", K.GO, "park", now=now), Goal(A.SQUARE, "square"))
    assert deed(wall) == f"make {COFFEE}"
    assert deed(promise("ana", K.GO, "park", now=now, description="walk")) == "walk"
    assert when(now, now) == "now"
    assert when(now + timedelta(hours=2), now) == "today 12:00"
    assert when(now + timedelta(days=1), now) == "tomorrow 10:00"
