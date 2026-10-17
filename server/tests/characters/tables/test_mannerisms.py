import random
import tomllib
from collections import Counter
from pathlib import Path

import pytest

from simile.characters.tables import Tables, Village, sample_mannerisms
from simile.characters.tables.generate_mannerisms import (
    PROMPTS,
    Batch,
    Prompt,
    dedupe,
    generate,
    read_toml,
    to_toml,
)
from simile.characters.tables.load import Mannerisms
from simile.llm import FakeProvider, LLMClient, Model


def test_mannerisms_fit_their_temperament(tables: Tables) -> None:
    [group] = [group for group in tables.mannerisms.group if group.id == "extraversion_high"]
    outgoing = set(group.items)

    def share(extraversion: float) -> float:
        picks = [
            item
            for seed in range(300)
            for item in sample_mannerisms(random.Random(seed), {"extraversion": extraversion})
        ]
        return sum(item in outgoing for item in picks) / len(picks)

    assert share(0.95) > 3 * share(0.05)


def test_no_two_residents_share_a_mannerism() -> None:
    rng, village = random.Random(0), Village()
    picks = [m for _ in range(40) for m in sample_mannerisms(rng, {}, count=3, village=village)]

    assert len(picks) == 120
    assert len(set(picks)) == len(picks)
    assert set(village.drawn) >= set(picks)


def test_dedupe_drops_repeats_and_rule_breakers() -> None:
    one, two = Prompt("one", {}, ""), Prompt("two", {}, "")
    batches = [
        (one, ["Taps the table twice before answering.", "hums while she cooks", "smokes outside"]),
        (two, ["taps the table twice before giving an answer", "whistles at birds on the fence"]),
    ]

    assert dedupe(batches) == [
        (one, ["taps the table twice before answering"]),
        (two, ["whistles at birds on the fence"]),
    ]


@pytest.mark.anyio
async def test_generate_makes_one_haiku_call_per_prompt() -> None:
    fake = FakeProvider([Batch(mannerisms=[f"hums song number {i} on the bus"]) for i in range(3)])

    batches = await generate(LLMClient(fake), PROMPTS[:3], count=12)

    assert [prompt for prompt, _ in batches] == list(PROMPTS[:3])
    assert len(fake.requests) == 3
    assert {request.model for request in fake.requests} == {Model.HAIKU.value}
    assert "Write 12 distinct mannerisms" in fake.requests[0].messages[-1].content


def test_the_toml_written_loads_back(tmp_path: Path) -> None:
    batches = [(PROMPTS[0], ["waves with both hands"]), (PROMPTS[-1], ["eats the crusts first"])]
    path = tmp_path / "mannerisms.toml"
    path.write_text(to_toml(batches))

    groups = Mannerisms.model_validate(tomllib.loads(path.read_text())).group
    assert [(g.id, g.lean, g.items) for g in groups] == [
        ("honesty_humility_high", {"honesty_humility": 1}, ["waves with both hands"]),
        ("routines", {}, ["eats the crusts first"]),
    ]
    assert [(p.id, items) for p, items in read_toml(path)] == [
        ("honesty_humility_high", ["waves with both hands"]),
        ("routines", ["eats the crusts first"]),
    ]


def test_the_committed_list_has_no_repeats(tables: Tables) -> None:
    items = Counter(item for group in tables.mannerisms.group for item in group.items)

    assert max(items.values()) == 1
