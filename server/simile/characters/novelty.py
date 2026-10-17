from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from simile.schema import Character

MODEL = "BAAI/bge-small-en-v1.5"
THRESHOLD = 0.9
"""Cosine similarity at or above which two characters count as near-duplicates."""


class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class LocalEmbedder:
    """A small ONNX model run locally with fastembed, downloaded once on first use."""

    def __init__(self, model: str = MODEL) -> None:
        self.model = model
        self._embedding = None

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if self._embedding is None:
            from fastembed import TextEmbedding

            self._embedding = TextEmbedding(self.model)
        return [vector.tolist() for vector in self._embedding.embed(list(texts))]


@dataclass(frozen=True)
class Match:
    id: str
    name: str
    persona: str
    similarity: float


def text(character: Character) -> str:
    return f"{character.persona}\n{character.backstory}"


class Novelty:
    """How close a character comes to the rest of the library."""

    def __init__(self, embedder: Embedder, library: Iterable[Character] = ()) -> None:
        self.embedder = embedder
        self._characters: dict[str, Character] = {}
        self._vectors: dict[str, np.ndarray] = {}
        self.add(*library)

    def add(self, *characters: Character) -> None:
        if not characters:
            return
        for character, vector in zip(characters, self._embed(characters), strict=True):
            self._characters[character.id] = character
            self._vectors[character.id] = vector

    def closest(self, character: Character) -> Match | None:
        others = [id for id in self._vectors if id != character.id]
        if not others:
            return None
        [vector] = self._embed([character])
        best = max(others, key=lambda id: float(vector @ self._vectors[id]))
        match = self._characters[best]
        return Match(best, match.name, match.persona, round(float(vector @ self._vectors[best]), 3))

    def too_close(self, character: Character) -> Match | None:
        match = self.closest(character)
        return match if match and match.similarity >= THRESHOLD else None

    def _embed(self, characters: Sequence[Character]) -> list[np.ndarray]:
        vectors = np.array(self.embedder.embed([text(c) for c in characters]), dtype=float)
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        return list(vectors)
