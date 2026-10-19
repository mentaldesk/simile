from collections import Counter
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta

import pytest

from simile.conversation import DEFAULT_CONFIG, ConversationConfig
from simile.conversation.temptation import (
    BROKE,
    BROKEN,
    Kind,
    Missed,
    Temptation,
    chance,
    found,
    lie,
    lies,
    missed_shifts,
    raised,
    standing,
    touched,
)
from simile.economy.economy import Turn
from simile.memory import MemoryStore, Record
from simile.npc import load_npcs
from simile.reflection.intentions import broken
from simile.schema import (
    CoreValue,
    Flag,
    FlagKind,
    Intention,
    IntentionKind,
    Medium,
    Memory,
    MemoryKind,
    Npc,
    Relationship,
    Traits,
    Work,
)
from simile.social import loan, meet, open_flag

from .conftest import work

NOW = datetime(2026, 1, 1, 10, tzinfo=UTC)
NAMES = {"ana": "Ana", "ben": "Ben", "cal": "Cal"}


def resident(id: str, honesty: float = 0.5) -> Npc:
    values = dict.fromkeys(CoreValue, 0.5) | {CoreValue.HONESTY: honesty}
    return load_npcs()[0].model_copy(
        update={"id": id, "name": f"{id.title()} Test", "values": values}
    )


ANA = resident("ana")
PEOPLE = {"ana": ANA, "ben": resident("ben")}


@pytest.fixture
def store() -> Iterator[MemoryStore]:
    with MemoryStore(":memory:") as store:
        yield store


def held(owner: str, kind: FlagKind, description: str, id: str = "f1") -> Relationship:
    """`owner`'s feelings about Ana, with one open flag."""
    flag = Flag(id=id, kind=kind, owner=owner, about="ana", description=description, created=NOW)
    return open_flag(meet(resident(owner), "ana"), flag)


def tempted(
    store: MemoryStore,
    *records: Record,
    listener: str = "ben",
    money: float | None = None,
    missed: Sequence[Missed] = (),
    works: Sequence[Work] = (),
) -> list[Temptation]:
    store.add(*records)
    known = standing(
        ANA,
        store,
        NOW,
        ["ana", "ben", "cal"],
        NAMES,
        money=money,
        target=300,
        missed=missed,
        workplace="The Daily Grind",
        work={made.id: made for made in works}.get,
    )
    return found(known, listener, NOW)


ONLY = "Use that cover story and nothing else: no days, times, places or other people."


def told(temptation: Temptation) -> str:
    """The direction told to them, without the line every direction ends with."""
    said = temptation.direction()
    assert said.endswith(f" {ONLY}")
    return said.removesuffix(f" {ONLY}")


def test_being_short_of_money_is_found_from_what_they_hold(store: MemoryStore) -> None:
    [short] = tempted(store, money=40)

    assert short.kind is Kind.SHORT
    assert told(short) == (
        "You are short of money this week. If it comes up, say you're doing fine."
    )
    assert short.direction("Ana") == (
        "Ana is short of money this week. If it comes up, Ana says they're doing fine. Ana uses "
        "that cover story and nothing else: no days, times, places or other people."
    )
    assert tempted(store, money=250) == []
    assert tempted(store) == []


def test_a_lender_knows_they_were_short(store: MemoryStore) -> None:
    lent = open_flag(meet(resident("cal"), "ana"), loan("cal", "ana", 50, "talk_1", NOW))

    short, debt = tempted(store, lent, money=40)

    assert short.known_by == {"cal"}
    assert debt.kind is Kind.DEBT


def test_a_debt_is_found_from_the_lenders_flag(store: MemoryStore) -> None:
    lent = open_flag(meet(resident("cal"), "ana"), loan("cal", "ana", 50, "talk_1", NOW))

    [debt] = tempted(store, lent)
    [to_lender] = tempted(store, listener="cal")

    assert told(debt) == (
        "You still owe Cal for a loan of 50. If it comes up, say you don't owe anyone anything."
    )
    assert debt.known_by == {"cal"} and debt.involves == {"cal"}
    assert told(to_lender) == (
        "You still owe Cal for a loan of 50. If it comes up, say you'll pay Cal back in a day "
        "or two."
    )
    assert to_lender.known_by == frozenset()


def test_a_secret_is_found_from_who_knows_it(store: MemoryStore) -> None:
    [secret] = tempted(store, held("cal", FlagKind.SECRET, "the dented van"))

    assert told(secret) == (
        "You have a secret to keep: the dented van. If anyone gets near it, say there's nothing "
        "to tell."
    )
    assert secret.known_by == {"cal"}


def test_a_grudge_against_them_is_a_complaint_they_could_deny(store: MemoryStore) -> None:
    [grudge] = tempted(store, held("ben", FlagKind.GRUDGE, "the broken fence"))

    assert grudge.kind is Kind.COMPLAINT
    assert told(grudge) == (
        "Ben blames you for the broken fence. If it comes up, say it wasn't your fault, without "
        "blaming anyone or anything else."
    )
    assert grudge.known_by == {"ben"}


def test_what_others_hold_that_isnt_a_temptation_is_left_out(store: MemoryStore) -> None:
    assert tempted(store, held("ben", FlagKind.PROMISE, "fixing the fence")) == []
    resolved = held("ben", FlagKind.SECRET, "the van").model_copy(update={"flags": []})
    assert tempted(store, resolved) == []


def promised(when: datetime) -> Intention:
    return Intention(
        id="talk_1/ana/1",
        owner="ana",
        kind=IntentionKind.SEEK,
        target="ben",
        description="look Ben up for a chat",
        promised_to=["ben"],
        created=when - timedelta(hours=3),
        due=when - timedelta(hours=2),
        expires=when,
        conversation_id="talk_1",
    )


def test_a_promise_they_broke_is_found_from_their_memory_of_it(store: MemoryStore) -> None:
    left = broken(promised(NOW - timedelta(hours=5)), PEOPLE, store, NOW - timedelta(hours=5))
    stale = broken(promised(NOW - timedelta(days=3)), PEOPLE, store, NOW - timedelta(days=3))
    [mine] = [m for m in left if isinstance(m, Memory) and m.owner == "ana"]

    [promise] = tempted(store, *left, *stale)

    assert mine.content == BROKE.format(told="Ben", deed="look Ben up for a chat")
    assert BROKEN in mine.topics
    assert told(promise) == (
        "You told Ben you'd look Ben up for a chat, and didn't. If it comes up, say something "
        "came up that you couldn't get out of."
    )
    assert promise.involves == {"ben"}


def test_a_missed_shift_is_found_from_e3s_turns(store: MemoryStore) -> None:
    skipped = Missed(NOW - timedelta(hours=2))
    late = Missed(NOW - timedelta(days=1), late=True)
    old = Missed(NOW - timedelta(days=5))

    one, other = tempted(store, missed=[skipped, late, old])

    assert told(one) == (
        "You skipped your shift at The Daily Grind today. If it comes up, say you were ill."
    )
    assert told(other) == (
        "You were late for your shift at The Daily Grind yesterday. If it comes up, say you were "
        "on time."
    )


def test_e3s_turns_count_once_skipped_or_late() -> None:
    def turn(hours_ago: float, arrived_after: float | None, npc: str = "ana") -> Turn:
        start = NOW - timedelta(hours=hours_ago)
        arrived = None if arrived_after is None else start + timedelta(minutes=arrived_after)
        return Turn(npc, start, start + timedelta(hours=4), arrived)

    skipped, late, on_time = turn(6, None), turn(30, 20), turn(54, 2)
    under_way, someone_elses = turn(1, None), turn(6, None, npc="ben")

    found = missed_shifts(
        [skipped, late, on_time, under_way, someone_elses], "ana", NOW, timedelta(minutes=5)
    )

    assert found == [Missed(skipped.start), Missed(late.start, late=True)]


def test_a_work_that_went_down_badly_is_found_from_others_memories(store: MemoryStore) -> None:
    mural = work("w1", "ana", "Mars Rising", NOW - timedelta(days=1), medium=Medium.MURAL)
    poem = work("w2", "ana", "Small Hours", NOW - timedelta(days=1), medium=Medium.WRITING)

    def seen(owner: str, made: Work, valence: float) -> Memory:
        return Memory(
            owner=owner,
            kind=MemoryKind.WORK,
            content=f"Saw {made.title}.",
            salience=0.6,
            valence=valence,
            timestamp=NOW - timedelta(hours=1),
            about=["ana"],
            work_id=made.id,
        )

    [panned] = tempted(
        store,
        seen("ben", mural, -0.6),
        seen("cal", mural, -0.4),
        seen("ben", poem, 0.4),
        works=[mural, poem],
    )

    assert told(panned) == (
        'Your mural "Mars Rising" went down badly. If it comes up, say you never took it seriously.'
    )
    assert panned.involves == {"ben", "cal"}


def test_being_asked_to_cover_or_complained_at_is_found_from_the_line() -> None:
    [cover] = raised("If Sandra asks, can you say I was helping you on Thursday?", "Sam", "ana")
    [complaint] = raised("Your bins have been out on the pavement since Thursday.", "Pat", "ana")

    assert told(cover) == "Sam is asking you to cover for them. Say you'll do it."
    assert cover.direction("Ana").startswith(
        "Sam is asking Ana to cover for them. Ana says they'll do it. Ana uses that cover story"
    )
    assert told(complaint) == (
        "Pat is complaining to you. If it's fair, don't own up to it: say you hadn't noticed, "
        "and give no other reason."
    )
    assert raised("Did you see the cameras? Nothing to hide, nothing to fear.", "Jo", "ana") == []
    assert raised("Sorry to bother you. My car's blocking the road.", "Visitor", "ana") == []


@pytest.mark.parametrize(
    ("said", "other", "touches"),
    [
        pytest.param("You're not struggling for money, are you?", None, True, id="a cue"),
        pytest.param("Lovely morning, isn't it?", None, False, id="nothing"),
        pytest.param("Lovely morning, isn't it?", "cal", True, id="someone involved"),
        pytest.param("Lovely morning, isn't it?", "ben", False, id="someone else"),
    ],
)
def test_what_touches_a_temptation(said: str, other: str | None, touches: bool) -> None:
    short = Temptation(Kind.SHORT, "ana", "short", "", "", "money", involves=frozenset({"cal"}))

    assert touched(short, said, other) is touches


def test_the_words_of_what_its_about_touch_it() -> None:
    promise = Temptation(Kind.PROMISE, "ana", "p", "", "", "", frozenset({"wardrobe"}))

    assert touched(promise, "How did the wardrobes go?")
    assert not touched(promise, "How did the fence go?")


@pytest.mark.parametrize(
    ("honesty", "odds"),
    [(1.0, 0.0), (0.6, 0.0), (0.59, 0.014), (0.35, 0.35), (0.1, 0.7), (0.0, 0.7)],
)
def test_the_chance_of_lying_rises_as_honesty_falls(honesty: float, odds: float) -> None:
    assert chance(honesty) == pytest.approx(odds, abs=1e-9)


def test_the_curve_is_configurable() -> None:
    config = ConversationConfig(honest_from=0.5, lie_peak=0.2, lie_most=0.9)

    assert chance(0.5, config=config) == 0
    assert chance(0.35, config=config) == pytest.approx(0.45)
    assert chance(0.2, config=config) == pytest.approx(0.9)


def test_negativity_bias_bends_the_chance_but_not_for_the_honest() -> None:
    biased, easy = Traits(negativity_bias=1.0), Traits(negativity_bias=0.0)

    assert chance(0.35, biased) == pytest.approx(0.35 * DEFAULT_CONFIG.lie_bias)
    assert chance(0.35, easy) == pytest.approx(0.35 / DEFAULT_CONFIG.lie_bias)
    assert chance(0.0, biased) == 1.0
    assert chance(0.8, biased) == 0.0


def test_the_roll_repeats_under_a_seed_and_follows_the_chance() -> None:
    short = Temptation(Kind.SHORT, "ana", "short", "", "", "")
    other = Temptation(Kind.SHIFT, "ana", "shift/x", "", "", "")

    rolls = Counter(lies(short, f"talk_{n}", 0.35) for n in range(4000))

    assert [lies(short, "talk_1", 0.5) for _ in range(5)] == [lies(short, "talk_1", 0.5)] * 5
    assert rolls[True] / 4000 == pytest.approx(0.35, abs=0.03)
    assert not any(lies(short, f"talk_{n}", 0.0) for n in range(200))
    assert {lies(short, f"t{n}", 0.5) == lies(other, f"t{n}", 0.5) for n in range(50)} == {
        True,
        False,
    }


def test_a_lie_says_what_b3_needs() -> None:
    secret = Temptation(
        Kind.SECRET,
        "ana",
        "secret/f1",
        "{Who} {has} a secret to keep: the van.",
        "If anyone gets near it, {say} there's nothing to tell.",
        "a secret",
        known_by=frozenset({"ben"}),
    )

    told = lie(secret, "ben", NAMES)

    assert (told.liar, told.listener, told.known) == ("ana", "ben", True)
    assert told.said == (
        "Ana has a secret to keep: the van. If anyone gets near it, Ana says there's nothing to "
        "tell. Ana uses that cover story and nothing else: no days, times, places or other people."
    )
    assert told.admits == "I lied to Ben about a secret."
    assert not lie(secret, "cal", NAMES).known
