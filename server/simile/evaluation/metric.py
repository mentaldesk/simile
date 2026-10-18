import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from simile.casting import value_distance
from simile.characters.novelty import Embedder, text
from simile.evaluation.play import Reply
from simile.evaluation.scenarios import Scenario
from simile.schema import Character


@dataclass(frozen=True)
class ScenarioSpread:
    scenario: Scenario
    distance: float
    """Mean embedding distance between two characters' replies."""
    stances: Counter[str]
    evenness: float
    """The stances' Shannon entropy over the most it could be with this many replies, 0-1."""


@dataclass(frozen=True)
class Spread:
    characters: list[Character]
    persona: float
    """Mean embedding distance between two characters' persona and backstory, as P3 embeds them."""
    values: float
    """Mean RMS difference between two characters' core values."""
    scenarios: list[ScenarioSpread]
    across: float
    """Mean embedding distance between two characters' replies to different scenarios: how far
    apart replies this long sit when they answer different things."""
    follows_values: float | None
    """Pearson r, over pairs of characters, between their values' distance and their replies'."""
    follows_persona: float | None
    """The same against their persona and backstory's embedding distance."""

    @property
    def distance(self) -> float:
        return float(np.mean([s.distance for s in self.scenarios]))

    @property
    def evenness(self) -> float:
        return float(np.mean([s.evenness for s in self.scenarios]))


def distances(vectors: Sequence[Sequence[float]]) -> np.ndarray:
    """Cosine distance between every two vectors."""
    matrix = np.array(vectors, dtype=float)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    matrix = matrix / np.where(norms == 0, 1, norms)
    return np.clip(1 - matrix @ matrix.T, 0, 2)


def pairs(matrix: np.ndarray) -> np.ndarray:
    """The values above the diagonal: one per pair."""
    return matrix[np.triu_indices(len(matrix), k=1)]


def mean_pairwise(matrix: np.ndarray) -> float:
    above = pairs(matrix)
    return float(above.mean()) if above.size else 0.0


def evenness(stances: Counter[str], labels: int) -> float:
    """How evenly the replies spread over the labels: 0 when all agree, 1 when as spread as
    they can be."""
    total = sum(stances.values())
    most = math.log(min(labels, total)) if min(labels, total) > 1 else 0.0
    if most == 0:
        return 0.0
    entropy = sum(n / total * math.log(total / n) for n in stances.values() if n)
    return entropy / most


def correlation(a: np.ndarray, b: np.ndarray) -> float | None:
    if a.size < 3 or np.std(a) == 0 or np.std(b) == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def spread(
    characters: Sequence[Character],
    scenarios: Sequence[Scenario],
    replies: Sequence[Reply],
    embedder: Embedder,
) -> Spread:
    """How far apart the characters are on paper and in what they say. Needs every character's
    reply to every scenario."""
    by = {(reply.character, reply.scenario): reply for reply in replies}
    if missing := [
        f"{c.id}/{s.id}" for c in characters for s in scenarios if (c.id, s.id) not in by
    ]:
        raise ValueError(f"No reply for {', '.join(missing)}")
    persona = distances(embedder.embed([text(c) for c in characters]))
    values = np.array([[value_distance(a, b) for b in characters] for a in characters])
    n = len(characters)
    said = [by[c.id, s.id] for s in scenarios for c in characters]
    every = distances(embedder.embed([reply.text or reply.raw for reply in said]))
    blocks = [
        [every[i * n : (i + 1) * n, j * n : (j + 1) * n] for j in range(len(scenarios))]
        for i in range(len(scenarios))
    ]
    results = []
    for i, scenario in enumerate(scenarios):
        stances = Counter(reply.stance for reply in said[i * n : (i + 1) * n] if reply.stance)
        results.append(
            ScenarioSpread(
                scenario,
                mean_pairwise(blocks[i][i]),
                stances,
                evenness(stances, len(scenario.stances)),
            )
        )
    across = [
        pairs(blocks[i][j]) for i in range(len(scenarios)) for j in range(len(scenarios)) if i != j
    ]
    behaviour = pairs(np.mean([blocks[i][i] for i in range(len(scenarios))], axis=0))
    return Spread(
        characters=list(characters),
        persona=mean_pairwise(persona),
        values=mean_pairwise(values),
        scenarios=results,
        across=float(np.mean(np.concatenate(across))) if across else 0.0,
        follows_values=correlation(pairs(values), behaviour),
        follows_persona=correlation(pairs(persona), behaviour),
    )
