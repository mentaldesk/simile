import random
from collections import Counter
from collections.abc import Callable

from simile.characters.tables import (
    Drawn,
    Happening,
    Skeleton,
    Tension,
    Village,
    sample_skeleton,
    sample_tension,
    sample_want,
    tension_context,
)

type Skeletons = Callable[..., Skeleton]


def tensions(
    s: Skeleton,
    scores: dict[str, float],
    events: list[Happening] | None = None,
    times: int = 300,
    fixed: Tension | None = None,
) -> list[Tension]:
    return [
        sample_tension(random.Random(i), s, scores, events or [], None, fixed=fixed)
        for i in range(times)
    ]


def test_a_contradiction_betrays_one_of_their_top_values(
    skeleton: Skeletons, values: Callable
) -> None:
    s = skeleton(50, seed=0)
    drawn = tensions(s, values(0.3, honesty=0.95, loyalty=0.9))
    betrayed = Counter(t.contradiction.value for t in drawn)

    assert betrayed["honesty"] + betrayed["loyalty"] > 0.8 * len(drawn)
    for t in drawn:
        assert t.contradiction.age <= 50


def test_a_secret_that_needs_an_event_only_comes_with_it(
    skeleton: Skeletons, values: Callable
) -> None:
    s = skeleton(50, seed=1)
    prison = [Happening(25, "prison", "spent eight months in prison", 63, -0.7)]
    without = Counter(t.secret.id for t in tensions(s, values(0.5)))
    served = Counter(t.secret.id for t in tensions(s, values(0.5), prison))

    assert "prison_past" not in without
    assert served["prison_past"] > 0.25 * 300


def test_high_and_low_values_want_different_things(skeleton: Skeletons, values: Callable) -> None:
    s = skeleton(40, seed=2)
    restless = Counter(t.want.id for t in tensions(s, values(0.5, adventure=0.95, freedom=0.9)))
    homebody = Counter(t.want.id for t in tensions(s, values(0.5, adventure=0.05, freedom=0.1)))

    assert restless["see_the_world"] > 4 * homebody["see_the_world"]


def test_a_want_leans_on_the_wound(skeleton: Skeletons, values: Callable) -> None:
    s = skeleton(60, seed=3, partnership="single")
    lonely = tension_context(s, values(0.5), [])

    def wants(wound: str | None) -> Counter:
        context = lonely
        if wound:
            context = tension_context(s, values(0.5), [Happening(0, wound, "", 1, 0)])
        return Counter(sample_want(random.Random(i), context).id for i in range(400))

    assert wants("old_and_alone")["find_partner"] > 2 * wants(None)["find_partner"]


def test_fixed_parts_are_kept(skeleton: Skeletons, values: Callable) -> None:
    wound = Drawn("mine", "a wound the player wrote")
    kept = Tension(None, wound, None, None)

    for t in tensions(skeleton(30), values(0.5), times=20, fixed=kept):
        assert t.wound == wound
        assert t.contradiction and t.secret and t.want


def test_a_rare_secret_goes_to_one_resident_at_most(values: Callable) -> None:
    rng, village = random.Random(4), Village()
    secrets = Counter()
    for _ in range(150):
        s = sample_skeleton(rng, rng.randint(25, 80), village=village)
        secrets[
            sample_tension(rng, s, values(rng.random()), [], None, village=village).secret.id
        ] += 1

    assert secrets["anonymous_donor"] <= 1
    assert secrets["cash_under_floor"] <= 1
    assert max(secrets.values()) < 20
