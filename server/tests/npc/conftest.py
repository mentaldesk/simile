from collections.abc import Callable
from typing import Any

import pytest

from simile.llm import FakeProvider, LLMClient, Request
from simile.npc.generate import Draft

NAMES = [
    "Ana Folau",
    "Bram de Wit",
    "Chiamaka Obi",
    "Dmitri Volkov",
    "Elif Kaya",
    "Farid Haddad",
    "Grace Liu",
    "Hiro Tanaka",
    "Ines Duarte",
    "Jonas Berg",
]


def draft(name: str = "Ana Folau", **changes: Any) -> Draft:
    fields: dict[str, Any] = {
        "name": name,
        "occupation": f"{name.split()[0]}'s job",
        "backstory": f"{name} grew up by the sea. They moved here for the quiet.",
        "persona": f"{name} is steady and kind. They notice who is missing.",
        "speaking_style": "Measured and warm.",
        "interests": ["tides", "bread", "local history"],
        "voice_description": "A woman in her forties. Low, warm voice, speaks slowly and evenly.",
        "reference_line": "I open the bakery at six and close when the bread runs out, most days.",
        "appearance": {
            "skin": "#c28569",
            "hair_style": "bun",
            "hair_colour": "#3e2731",
            "top_colour": "#265c42",
            "bottom_colour": "#3a4466",
            "shoe_colour": "#733e39",
            "build": "average",
            "accessories": ["apron"],
        },
    }
    return Draft.model_validate(fields | changes)


MakeDraft = Callable[..., Draft]


@pytest.fixture
def make_draft() -> MakeDraft:
    return draft


@pytest.fixture
def names() -> list[str]:
    return list(NAMES)


@pytest.fixture
def residents() -> Callable[[], FakeProvider]:
    """A fake provider that writes one resident per call from NAMES, in order."""

    def make() -> FakeProvider:
        names = iter(NAMES)

        def reply(request: Request) -> str:
            return draft(next(names)).model_dump_json()

        return FakeProvider([reply] * len(NAMES))

    return make


@pytest.fixture
def llm(residents: Callable[[], FakeProvider]) -> LLMClient:
    return LLMClient(residents())
