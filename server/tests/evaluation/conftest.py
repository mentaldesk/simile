import hashlib
import re
from collections.abc import Sequence

import pytest

from simile.characters.pool import load_pool
from simile.schema import Character

DIMENSIONS = 512


class HashingEmbedder:
    """Bag-of-words vectors, so the same words embed the same. Never downloads a model."""

    def __init__(self) -> None:
        self.texts: list[str] = []

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.texts += texts
        vectors = []
        for text in texts:
            vector = [0.0] * DIMENSIONS
            for word in re.findall(r"\w+", text.lower()):
                vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIMENSIONS] += 1
            vectors.append(vector)
        return vectors


@pytest.fixture(scope="session")
def pool() -> list[Character]:
    return load_pool()


@pytest.fixture
def embedder() -> HashingEmbedder:
    return HashingEmbedder()
