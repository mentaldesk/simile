from collections import Counter
from typing import Any

import numpy as np
import pytest

from simile.evaluation.metric import correlation, distances, evenness, mean_pairwise, spread
from simile.evaluation.play import Reply
from simile.evaluation.scenarios import SCENARIOS
from simile.schema import Character, CoreValue

TWO = SCENARIOS[:2]


def replies(
    texts: dict[tuple[str, str], str], stances: dict[str, str] | None = None
) -> list[Reply]:
    return [
        Reply(
            character=character,
            scenario=scenario,
            model="m",
            key=f"{character}/{scenario}",
            raw=text,
            text=text,
            stance=(stances or {}).get(f"{character}/{scenario}"),
        )
        for (character, scenario), text in texts.items()
    ]


def test_distances_are_cosine() -> None:
    matrix = distances([[1, 0], [2, 0], [0, 3], [0, 0]])

    assert matrix[0, 1] == pytest.approx(0)
    assert matrix[0, 2] == pytest.approx(1)
    assert matrix[0, 3] == pytest.approx(1)
    assert mean_pairwise(matrix[:3, :3]) == pytest.approx(2 / 3)


@pytest.mark.parametrize(
    ("stances", "labels", "expected"),
    [
        (Counter(helps=10), 5, 0.0),
        (Counter(helps=2, refuses=2, hedges=2, deflects=2, hostile=2), 5, 1.0),
        (Counter(helps=1, refuses=1), 5, 1.0),
        (Counter(helps=5, refuses=5), 5, np.log(2) / np.log(5)),
        (Counter(), 5, 0.0),
    ],
)
def test_evenness(stances: Counter[str], labels: int, expected: float) -> None:
    assert evenness(stances, labels) == pytest.approx(expected)


def test_correlation_needs_three_pairs_that_vary() -> None:
    assert correlation(np.array([1.0, 2.0, 3.0]), np.array([2.0, 4.0, 7.0])) == pytest.approx(
        0.99, abs=0.01
    )
    assert correlation(np.array([1.0, 2.0]), np.array([1.0, 2.0])) is None
    assert correlation(np.array([1.0, 1.0, 1.0]), np.array([1.0, 2.0, 3.0])) is None


def test_characters_who_all_say_the_same_have_no_spread(
    pool: list[Character], embedder: Any
) -> None:
    characters = pool[:3]
    texts = {(c.id, s.id): f"{s.id}, {s.id}!" for c in characters for s in TWO}
    stances = {f"{c.id}/favour": "helps" for c in characters}

    measured = spread(characters, TWO, replies(texts, stances), embedder)

    assert [s.distance for s in measured.scenarios] == [pytest.approx(0), pytest.approx(0)]
    assert measured.scenarios[0].stances == Counter(helps=3)
    assert measured.scenarios[0].evenness == 0
    assert measured.scenarios[1].stances == Counter()
    assert measured.across == pytest.approx(1)
    assert measured.follows_values is None


def test_characters_who_differ_spread_out_and_paper_is_measured_as_p3_embeds_it(
    pool: list[Character], embedder: Any
) -> None:
    characters = pool[:3]
    texts = {(c.id, s.id): f"{c.id} answers {s.id}" for c in characters for s in TWO}

    measured = spread(characters, TWO, replies(texts), embedder)

    assert all(s.distance > 0.3 for s in measured.scenarios)
    assert measured.distance == pytest.approx(np.mean([s.distance for s in measured.scenarios]))
    assert embedder.texts[:3] == [f"{c.persona}\n{c.backstory}" for c in characters]
    assert 0 < measured.persona < 1
    assert 0 < measured.values < 1


def test_replies_that_follow_values_correlate(pool: list[Character], embedder: Any) -> None:
    characters = [
        pool[0].model_copy(update={"id": f"c{k}", "values": {v: k / 4 for v in CoreValue}})
        for k in range(5)
    ]
    texts = {
        (f"c{k}", s.id): " ".join(f"w{i}" for i in range(2 * k, 2 * k + 6))
        for k in range(5)
        for s in TWO
    }

    measured = spread(characters, TWO, replies(texts), embedder)

    assert measured.values == pytest.approx(0.5)
    assert measured.follows_values is not None and measured.follows_values > 0.8


def test_every_reply_is_needed(pool: list[Character], embedder: Any) -> None:
    characters = pool[:2]
    texts = {(characters[0].id, s.id): "Hello." for s in TWO}

    with pytest.raises(ValueError, match=f"No reply for {characters[1].id}/favour"):
        spread(characters, TWO, replies(texts), embedder)
