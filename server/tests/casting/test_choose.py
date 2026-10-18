import random
from collections.abc import Callable
from statistics import mean

import pytest

from simile.casting import CastError, Pin, affinities, cast, conflicts, spread
from simile.schema import Character, HookKind

type Make = Callable[..., Character]

SEEDS = range(50)


@pytest.mark.parametrize("count", [4, 10])
def test_a_random_cast_is_more_spread_out_than_a_uniform_draw(
    pool: list[Character], count: int
) -> None:
    drawn = mean(spread(cast(pool, count, seed=seed, houses=10)) for seed in SEEDS)
    uniform = mean(spread(random.Random(seed).sample(pool, count)) for seed in SEEDS)

    assert drawn > uniform


def test_a_random_cast_clashes_and_agrees_on_purpose(pool: list[Character]) -> None:
    def both(residents: list[Character]) -> bool:
        return bool(conflicts(residents)) and bool(affinities(residents))

    drawn = [both(cast(pool, 4, seed=seed, houses=10)) for seed in SEEDS]
    uniform = [both(random.Random(seed).sample(pool, 4)) for seed in SEEDS]

    assert all(drawn)
    assert sum(uniform) < len(SEEDS) * 0.75


def test_a_seed_gives_the_same_cast_and_seeds_differ(pool: list[Character]) -> None:
    def ids(seed: int) -> list[str]:
        return [c.id for c in cast(pool, 6, seed=seed, houses=10)]

    assert ids(3) == ids(3)
    assert len({tuple(sorted(ids(seed))) for seed in range(10)}) == 10


def test_a_hand_picked_cast_is_taken_as_given(pool: list[Character]) -> None:
    picks = [pool[5].id, pool[0].id, pool[12].id]

    assert [c.id for c in cast(pool, picks=picks, houses=10)] == picks


def test_picks_and_pins_join_a_random_cast(pool: list[Character]) -> None:
    a, b, c = pool[1].id, pool[7].id, pool[19].id
    pins = [Pin(kind=HookKind.DEBT, actor=b, target=c)]

    for seed in range(10):
        chosen = [r.id for r in cast(pool, 6, picks=[a], pins=pins, seed=seed, houses=10)]
        assert len(set(chosen)) == 6
        assert chosen[:3] == [a, b, c]


def test_a_cast_bigger_than_the_houses_is_refused(pool: list[Character]) -> None:
    with pytest.raises(CastError, match="10 houses, too few for 11"):
        cast(pool, 11)
    with pytest.raises(CastError, match="2 houses, too few for 3"):
        cast(pool, picks=[c.id for c in pool[:3]], houses=2)


def test_a_cast_too_small_for_its_picks_or_unknown_ids_is_refused(pool: list[Character]) -> None:
    with pytest.raises(CastError, match="can't hold the 3"):
        cast(pool, 2, picks=[c.id for c in pool[:3]], houses=10)
    with pytest.raises(CastError, match="No character nobody"):
        cast(pool, 2, picks=["nobody"], houses=10)


def test_no_two_residents_share_a_voice_clip(make: Make) -> None:
    clips = ["a.wav", "a.wav", "a.wav", "b.wav", "b.wav", "c.wav", None, None]
    library = [make(f"resident_{i}", clip=clip) for i, clip in enumerate(clips)]

    for seed in SEEDS:
        voiced = [c.voice.reference_clip for c in cast(library, 5, seed=seed, houses=10)]
        clipped = [clip for clip in voiced if clip is not None]
        assert len(clipped) == len(set(clipped))
        assert voiced.count(None) == 2


def test_residents_without_a_clip_never_clash(make: Make) -> None:
    library = [make(f"resident_{i}") for i in range(10)]

    assert len(cast(library, 10, houses=10)) == 10


def test_picks_sharing_a_clip_or_too_few_clips_are_refused(make: Make) -> None:
    library = [make(f"resident_{i}", clip="same.wav") for i in range(4)]

    with pytest.raises(CastError, match="share the voice clip same.wav"):
        cast(library, picks=["resident_0", "resident_2"], houses=10)
    with pytest.raises(CastError, match="voice clip of their own"):
        cast(library, 2, houses=10)
