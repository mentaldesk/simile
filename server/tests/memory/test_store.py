from datetime import UTC, datetime, timedelta

import pytest

from simile.memory import MemoryStore
from simile.schema import (
    Aspect,
    Baseline,
    Flag,
    FlagKind,
    InteractionEvent,
    Memory,
    MemoryKind,
    Relationship,
)

NOW = datetime(2026, 3, 14, 12, tzinfo=UTC)


def memory(
    content: str,
    *,
    owner: str = "mei",
    salience: float = 0.5,
    hours_ago: float = 0,
    kind: MemoryKind = MemoryKind.CONVERSATION,
    about: tuple[str, ...] = (),
) -> Memory:
    return Memory(
        owner=owner,
        kind=kind,
        content=content,
        salience=salience,
        valence=0,
        timestamp=NOW - timedelta(hours=hours_ago),
        about=list(about),
    )


def event(
    actor: str, target: str, action: str, *, magnitude: float = 0.5, hours_ago: float = 0
) -> InteractionEvent:
    return InteractionEvent(
        actor=actor,
        target=target,
        action=action,
        aspects=[Aspect.LIKE],
        valence=0.5,
        magnitude=magnitude,
        timestamp=NOW - timedelta(hours=hours_ago),
    )


def flag(id: str, owner: str, about: str, *, resolved: bool = False) -> Flag:
    return Flag(
        id=id,
        kind=FlagKind.DEBT,
        owner=owner,
        about=about,
        description=id,
        created=NOW - timedelta(days=1),
        resolved=NOW if resolved else None,
    )


def relationship(owner: str, about: str, *, like: float = 0.5, flags: list[Flag]) -> Relationship:
    return Relationship(
        owner=owner,
        about=about,
        like=like,
        trust=0.5,
        respect=0.5,
        familiarity=0.5,
        baseline=Baseline(like=0.5, trust=0.5, respect=0.5),
        flags=flags,
    )


def test_recall_ranks_by_salience_times_recency(store: MemoryStore) -> None:
    old_but_vivid = memory("the bridge collapsed", salience=0.9, hours_ago=24)
    fresh_but_dull = memory("Viktor ordered a flat white", salience=0.3)
    recent_and_interesting = memory("Suki's drone crashed", salience=0.6, hours_ago=6)
    store.add(old_but_vivid, fresh_but_dull, recent_and_interesting)

    assert store.recall("mei", NOW) == [recent_and_interesting, fresh_but_dull, old_but_vivid]


def test_recall_prefers_recent_and_salient_memories(store: MemoryStore) -> None:
    older = memory("older", hours_ago=1)
    dull = memory("dull", salience=0.2)
    newer = memory("newer")
    store.add(older, dull, newer)

    assert store.recall("mei", NOW) == [newer, older, dull]


def test_a_longer_half_life_lets_salience_win(store: MemoryStore) -> None:
    old_but_vivid = memory("the bridge collapsed", salience=0.9, hours_ago=24)
    fresh_but_dull = memory("Viktor ordered a flat white", salience=0.3)
    store.add(old_but_vivid, fresh_but_dull)

    assert store.recall("mei", NOW, half_life=timedelta(days=7)) == [old_but_vivid, fresh_but_dull]


def test_recall_returns_the_top_k(store: MemoryStore) -> None:
    store.add(*(memory(f"memory {n}", hours_ago=n) for n in range(10)))

    recalled = store.recall("mei", NOW, k=3)

    assert [m.content for m in recalled] == ["memory 0", "memory 1", "memory 2"]


def test_recall_filters_by_owner_about_and_kind(store: MemoryStore) -> None:
    about_viktor = memory("Viktor praised my latte art", about=("viktor",))
    about_both = memory("Viktor and Suki argued", about=("suki", "viktor"), hours_ago=1)
    about_suki = memory("Suki waved", about=("suki",))
    news = memory("Drones regulated", kind=MemoryKind.NEWS)
    viktors = memory("Mei drew the bridge", owner="viktor", about=("viktor",))
    store.add(about_viktor, about_both, about_suki, news, viktors)

    assert store.recall("mei", NOW, about="viktor") == [about_viktor, about_both]
    assert store.recall("mei", NOW, kind=MemoryKind.NEWS) == [news]
    assert store.recall("mei", NOW, about="suki", kind=MemoryKind.NEWS) == []
    assert store.recall("viktor", NOW) == [viktors]
    assert store.recall("suki", NOW) == []


def test_now_must_be_timezone_aware(store: MemoryStore) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        store.recall("mei", datetime(2026, 3, 14, 12))


def test_shared_history_is_per_pair_in_both_directions(store: MemoryStore) -> None:
    mei_to_viktor = event("mei", "viktor", "remembered his order", hours_ago=2)
    viktor_to_mei = event("viktor", "mei", "praised her latte art", hours_ago=1)
    mei_to_suki = event("mei", "suki", "lent her a ladder")
    suki_to_viktor = event("suki", "viktor", "buzzed his garden")
    viktors_debt = flag("viktors_debt", "mei", "viktor")
    meis_debt = flag("meis_debt", "viktor", "mei")
    store.add(
        mei_to_viktor,
        viktor_to_mei,
        mei_to_suki,
        suki_to_viktor,
        viktors_debt,
        meis_debt,
        flag("repaid", "mei", "viktor", resolved=True),
        flag("sukis_debt", "mei", "suki"),
        flag("grudge", "viktor", "suki"),
    )

    history = store.shared_history("mei", "viktor", NOW)

    assert history.events == [mei_to_viktor, viktor_to_mei]
    assert history.flags == [meis_debt, viktors_debt]
    assert store.shared_history("viktor", "mei", NOW) == history
    assert store.shared_history("mei", "suki", NOW).events == [mei_to_suki]
    assert store.shared_history("suki", "mei", NOW).flags == [flag("sukis_debt", "mei", "suki")]
    assert store.shared_history("mei", "player", NOW).events == []


def test_shared_history_keeps_the_top_k_by_magnitude_times_recency_oldest_first(
    store: MemoryStore,
) -> None:
    bridge = event("viktor", "mei", "wrecked the bridge", magnitude=0.9, hours_ago=30)
    gift = event("mei", "viktor", "gave him a cake", magnitude=0.4, hours_ago=10)
    spat = event("viktor", "mei", "called her coffee bland", magnitude=0.6, hours_ago=2)
    hello = event("mei", "viktor", "said hello", magnitude=0.1, hours_ago=1)
    store.add(bridge, gift, spat, hello)

    assert store.shared_history("mei", "viktor", NOW, k=3).events == [bridge, gift, spat]


def test_relationship_comes_back_with_its_flags(store: MemoryStore) -> None:
    debt = flag("debt", "mei", "viktor")
    saved = relationship("mei", "viktor", flags=[debt])
    store.add(saved, flag("other", "viktor", "mei"))

    assert store.relationship("mei", "viktor") == saved
    assert store.relationship("mei", "suki") is None


def test_saving_a_relationship_replaces_its_scores_and_keeps_its_flags(store: MemoryStore) -> None:
    debt = flag("debt", "mei", "viktor")
    store.add(relationship("mei", "viktor", like=0.2, flags=[debt]))

    store.add(relationship("mei", "viktor", like=0.7, flags=[]))

    assert store.relationship("mei", "viktor") == relationship(
        "mei", "viktor", like=0.7, flags=[debt]
    )


def test_resolving_a_flag_updates_it_and_closes_it(store: MemoryStore) -> None:
    store.add(relationship("mei", "viktor", flags=[flag("debt", "mei", "viktor")]))

    repaid = flag("debt", "mei", "viktor", resolved=True)
    store.add(repaid)

    found = store.relationship("mei", "viktor")
    assert found is not None
    assert found.flags == [repaid]
    assert store.shared_history("mei", "viktor", NOW).flags == []


def test_relationships_lists_everyone_the_owner_knows(store: MemoryStore) -> None:
    suki = relationship("viktor", "suki", flags=[flag("grudge", "viktor", "suki")])
    mei = relationship("viktor", "mei", flags=[])
    store.add(suki, mei, relationship("mei", "viktor", flags=[]))

    assert store.relationships("viktor") == [mei, suki]


def test_add_is_all_or_nothing(store: MemoryStore) -> None:
    with pytest.raises(TypeError, match="can't store str"):
        store.add(memory("kept?"), "not a record")  # type: ignore[arg-type]

    assert store.recall("mei", NOW) == []
