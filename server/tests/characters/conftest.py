import hashlib
import itertools
import json
import re
from collections.abc import Callable, Sequence
from typing import Any

import pytest

from simile.llm import FakeProvider, LLMClient, Request

APPEARANCE = {
    "skin": "#c28569",
    "hair_style": "short",
    "hair_colour": "#3e2731",
    "top_colour": "#265c42",
    "bottom_colour": "#3a4466",
    "shoe_colour": "#733e39",
    "build": "average",
    "accessories": ["glasses"],
}
REFERENCE_LINE = (
    "The early bus leaves at twenty to seven, and I like to be at the stop by half past."
)
DIMENSIONS = 512


class HashingEmbedder:
    """Bag-of-words vectors: the same words embed the same, unrelated words barely overlap."""

    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        vectors = []
        for text in texts:
            vector = [0.0] * DIMENSIONS
            for word in re.findall(r"\w+", text.lower()):
                vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIMENSIONS] += 1
            vectors.append(vector)
        return vectors


def words(seed: str, count: int = 14) -> str:
    """Made-up words that differ from one seed to the next."""
    digest = hashlib.sha256(seed.encode()).hexdigest()
    return " ".join(f"w{digest[i : i + 4]}" for i in range(0, count * 4, 4))


def requested(request: Request) -> dict[str, Any]:
    """The JSON Schema `LLMClient.structured` put in the system prompt."""
    return json.loads(request.system.split("no code fence:\n", 1)[1])


def name_in(request: Request) -> str:
    found = re.search(r"- Name: (.+?)\. Refer", request.messages[-1].content)
    return found[1] if found else "someone"


def answer(request: Request, *, tag: str = "", overrides: dict[str, Any] | None = None) -> str:
    """A valid reply to a biography or critic request, with text unique to the character."""
    critic = request.system.startswith("You edit")
    who = name_in(request) + tag + ("critic" if critic else "")
    reply: dict[str, Any] = {}
    for name, spec in requested(request)["properties"].items():
        if name == "notes":
            reply[name] = ["Swapped a stock phrase for something specific."]
        elif name in ("past", "hooks"):
            reply[name] = [
                f"{name} {i} {words(f'{who}{name}{i}', 6)}" for i in range(spec["minItems"])
            ]
        elif name == "interests":
            reply[name] = [words(f"{who}{name}{i}", 3) for i in range(3)]
        elif name == "craft":
            reply[name] = None
        elif name == "voice":
            reply[name] = {
                "description": f"A woman in her fifties. {words(who + name, 5)}.",
                "reference_line": REFERENCE_LINE,
            }
        elif name == "appearance":
            colour = "#" + hashlib.sha256(who.encode()).hexdigest()[:6]
            reply[name] = APPEARANCE | {"top_colour": colour}
        else:
            reply[name] = f"{'Revised: ' if critic else ''}{words(who + name)}."
    return json.dumps(reply | (overrides or {}))


Fakes = Callable[..., tuple[LLMClient, FakeProvider]]


@pytest.fixture
def fake_llm() -> Fakes:
    calls = itertools.count()

    def make(*replies: Any) -> tuple[LLMClient, FakeProvider]:
        def fresh(request: Request) -> str:
            return answer(request, tag=str(next(calls)))

        fake = FakeProvider(replies, default=fresh)
        return LLMClient(fake), fake

    return make


@pytest.fixture
def embedder() -> HashingEmbedder:
    return HashingEmbedder()


@pytest.fixture
def reply() -> Callable[..., str]:
    """`answer`, for a test that wants to change part of a reply."""
    return answer
