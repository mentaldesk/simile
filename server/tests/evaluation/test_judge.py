import json

import pytest
from pydantic import ValidationError

from simile.evaluation.judge import judge_prompt, label, stance_schema
from simile.evaluation.play import Reply
from simile.evaluation.scenarios import SCENARIOS
from simile.llm import FakeProvider, LLMClient

pytestmark = pytest.mark.anyio

FAVOUR, PROMISE = SCENARIOS[:2]


def reply(character: str, scenario: str, text: str) -> Reply:
    return Reply(
        character=character,
        scenario=scenario,
        model="m",
        key=f"{character}/{scenario}",
        raw=text,
        text=text,
    )


REPLIES = [
    reply("ann", "favour", "Course I will, hang on."),
    reply("ann", "promise", "You stood me up this morning."),
    reply("bob", "favour", "Push it yourself."),
    reply("bob", "promise", ""),
]


def test_the_prompt_groups_replies_by_scenario_without_names() -> None:
    ordered = sorted(REPLIES, key=lambda r: r.scenario != "favour")

    text = judge_prompt(SCENARIOS, ordered)

    favour, promise = text.split("## ")[1:]
    assert favour.startswith(f"{FAVOUR.title}\n{FAVOUR.situation}\nVisitor says:")
    assert '- r1: "Course I will, hang on."\n- r2: "Push it yourself."' in favour
    assert "- hostile: rude, cold or attacking" in favour
    assert '- r4: "(says nothing)"' in promise
    assert "ann" not in text and "bob" not in text


def test_each_reply_takes_only_its_scenarios_labels() -> None:
    schema = stance_schema(SCENARIOS, REPLIES)

    assert schema(r1="helps", r2="confronts", r3="hostile", r4="ignores")
    with pytest.raises(ValidationError):
        schema(r1="confronts", r2="confronts", r3="hostile", r4="ignores")


async def test_label_asks_once_and_sets_each_stance() -> None:
    fake = FakeProvider(
        [json.dumps({"r1": "helps", "r2": "hostile", "r3": "confronts", "r4": "ignores"})]
    )

    labelled = await label(LLMClient(fake), SCENARIOS, REPLIES, model="judge")

    assert [(r.key, r.stance) for r in labelled] == [
        ("ann/favour", "helps"),
        ("bob/favour", "hostile"),
        ("ann/promise", "confronts"),
        ("bob/promise", "ignores"),
    ]
    [request] = fake.requests
    assert request.model == "judge"
    assert '"enum": ["helps", "refuses", "hedges", "deflects", "hostile"]' in request.system


async def test_a_label_from_another_scenario_is_asked_again() -> None:
    fake = FakeProvider(
        [
            json.dumps({"r1": "confronts", "r2": "helps", "r3": "hints", "r4": "ignores"}),
            json.dumps({"r1": "helps", "r2": "helps", "r3": "hints", "r4": "ignores"}),
        ]
    )

    labelled = await label(LLMClient(fake), SCENARIOS, REPLIES, model="judge")

    assert len(fake.requests) == 2
    assert labelled[0].stance == "helps"


async def test_no_replies_makes_no_call() -> None:
    fake = FakeProvider()

    assert await label(LLMClient(fake), SCENARIOS, [], model="judge") == []
    assert fake.requests == []
