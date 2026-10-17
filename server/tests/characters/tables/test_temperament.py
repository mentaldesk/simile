import random
import statistics
from collections import Counter
from collections.abc import Callable

from simile.characters.tables import (
    Happening,
    Skeleton,
    Tables,
    describe_temperament,
    sample_attachment,
    sample_temperament,
)

type Skeletons = Callable[..., Skeleton]


def mean(values: dict[str, float], score: str, times: int = 200) -> float:
    return statistics.mean(
        sample_temperament(random.Random(i), values)[score] for i in range(times)
    )


def test_every_domain_and_facet_gets_a_score(tables: Tables, values: Callable) -> None:
    scores = sample_temperament(random.Random(0), values(0.5))
    ids = {d.id for d in tables.temperament.domain}
    ids |= {f.id for d in tables.temperament.domain for f in d.facet}

    assert set(scores) == ids
    assert all(0 <= score <= 1 for score in scores.values())
    assert scores == sample_temperament(random.Random(0), values(0.5))


def test_values_pull_their_domains(values: Callable) -> None:
    honest = values(0.5, honesty=0.95, equality=0.9, success=0.1, ambition=0.1)
    grasping = values(0.5, honesty=0.1, equality=0.1, success=0.95, ambition=0.95)
    curious = values(0.5, creativity=0.95, open_mindedness=0.95, tradition=0.05)
    settled = values(0.5, creativity=0.05, open_mindedness=0.05, tradition=0.95)

    assert mean(honest, "honesty_humility") > mean(grasping, "honesty_humility") + 0.3
    assert mean(honest, "sincerity") > mean(grasping, "sincerity") + 0.2
    assert mean(curious, "openness") > mean(settled, "openness") + 0.3


def test_fixed_scores_are_kept_and_facets_follow_them(values: Callable) -> None:
    def calm(seed: int) -> dict[str, float]:
        return sample_temperament(random.Random(seed), values(0.5), fixed={"emotionality": 0.1})

    assert all(calm(seed)["emotionality"] == 0.1 for seed in range(20))
    assert statistics.mean(calm(seed)["anxiety"] for seed in range(100)) < 0.25


def test_describe_picks_the_most_extreme_facets(tables: Tables) -> None:
    scores = {"anxiety": 0.97, "sociability": 0.1, "prudence": 0.55}
    facets = {f.id: f for d in tables.temperament.domain for f in d.facet}

    assert describe_temperament(scores) == [facets["anxiety"].high, facets["sociability"].low]


def test_attachment_follows_childhood_and_temperament(skeleton: Skeletons) -> None:
    calm = {"emotionality": 0.2, "extraversion": 0.7, "social_self_esteem": 0.8}
    shaken = {"emotionality": 0.85, "social_self_esteem": 0.15}
    loved = skeleton(40, seed=0, upbringing="two_parents")
    in_care = skeleton(40, seed=0, upbringing="care")
    bullied = [Happening(10, "bullied", "bullied", 35, -0.6)]

    def styles(s: Skeleton, scores: dict[str, float], events: list[Happening]) -> Counter:
        return Counter(sample_attachment(random.Random(i), s, scores, events) for i in range(400))

    secure, insecure = styles(loved, calm, []), styles(in_care, shaken, bullied)
    assert secure["secure"] > 300
    assert insecure["secure"] < 100
    assert insecure["fearful"] > 4 * secure["fearful"]
