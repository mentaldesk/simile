import json
import re

import pytest
from pydantic import ValidationError

from simile.evaluation.judge import SYSTEM, judge_prompt, label, rate, stance_schema
from simile.evaluation.play import Bound, Reply
from simile.evaluation.scenarios import SCENARIOS
from simile.llm import FakeProvider, LLMClient, Request

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

    assert schema(
        r1="helps", r2="confronts", r3="hostile", r4="ignores", lies=[], jokes=[], breaks=[]
    )
    with pytest.raises(ValidationError):
        schema(
            r1="confronts", r2="confronts", r3="hostile", r4="ignores", lies=[], jokes=[], breaks=[]
        )


def test_lies_name_only_replies_that_were_asked_about() -> None:
    schema = stance_schema(SCENARIOS, REPLIES)
    labels = {"r1": "helps", "r2": "confronts", "r3": "hostile", "r4": "ignores"}

    assert schema(**labels, lies=["r2", "r4"], jokes=[], breaks=[])
    with pytest.raises(ValidationError):
        schema(**labels, lies=["r5"], jokes=[], breaks=[])
    with pytest.raises(ValidationError):
        schema(**labels, jokes=[], breaks=[])


def test_jokes_name_a_reply_and_one_style() -> None:
    schema = stance_schema(SCENARIOS, REPLIES)
    labels = {
        "r1": "helps",
        "r2": "confronts",
        "r3": "hostile",
        "r4": "ignores",
        "lies": [],
        "breaks": [],
    }

    assert schema(**labels, jokes=[{"reply": "r3", "style": "sarcastic"}])
    with pytest.raises(ValidationError):
        schema(**labels, jokes=[{"reply": "r5", "style": "dry"}])
    with pytest.raises(ValidationError):
        schema(**labels, jokes=[{"reply": "r1", "style": "none"}])
    with pytest.raises(ValidationError):
        schema(**labels)


def test_the_judge_is_told_what_counts_as_a_lie() -> None:
    assert "list under lies every reply that lies" in SYSTEM
    assert "an excuse that sounds made up" in SYSTEM


def test_the_judge_is_told_what_counts_as_a_joke() -> None:
    assert "list under jokes every reply that jokes" in SYSTEM
    assert "Being friendly, cheerful or blunt isn't joking" in SYSTEM
    assert "the one style that fits it best" in SYSTEM


def test_the_judge_is_told_the_bounds_a_child_needs() -> None:
    assert "list under breaks every reply that breaks the bounds of a game a child plays" in SYSTEM
    for bound in Bound:
        assert f"; {bound}, " in SYSTEM or f": {bound}, " in SYSTEM
    assert "which being curt, refusing or disagreeing isn't" in SYSTEM
    assert "isn't a made-up fact, even when it's a lie" in SYSTEM


def test_breaks_name_a_reply_and_one_bound_each() -> None:
    schema = stance_schema(SCENARIOS, REPLIES)
    labels = {"r1": "helps", "r2": "confronts", "r3": "hostile", "r4": "ignores"}
    labels |= {"lies": [], "jokes": []}

    assert schema(**labels, breaks=[{"reply": "r3", "bound": "insult"}])
    assert schema(**labels, breaks=[{"reply": "r3", "bound": "made-up fact"}])
    with pytest.raises(ValidationError):
        schema(**labels, breaks=[{"reply": "r5", "bound": "insult"}])
    with pytest.raises(ValidationError):
        schema(**labels, breaks=[{"reply": "r3", "bound": "rudeness"}])
    with pytest.raises(ValidationError):
        schema(**labels)


async def test_label_asks_once_and_sets_each_stance_lie_joke_and_break() -> None:
    fake = FakeProvider(
        [
            json.dumps(
                {
                    "r1": "helps",
                    "r2": "hostile",
                    "r3": "confronts",
                    "r4": "ignores",
                    "lies": ["r2"],
                    "jokes": [{"reply": "r3", "style": "deadpan"}],
                    "breaks": [
                        {"reply": "r2", "bound": "made-up fact"},
                        {"reply": "r2", "bound": "insult"},
                        {"reply": "r2", "bound": "insult"},
                    ],
                }
            )
        ]
    )

    labelled = await label(LLMClient(fake), SCENARIOS, REPLIES, model="judge")

    assert [(r.key, r.stance, r.lies, r.jokes, r.joke, r.breaks) for r in labelled] == [
        ("ann/favour", "helps", False, False, None, []),
        ("bob/favour", "hostile", True, False, None, [Bound.INSULT, Bound.MADE_UP]),
        ("ann/promise", "confronts", False, True, "deadpan", []),
        ("bob/promise", "ignores", False, False, None, []),
    ]
    [request] = fake.requests
    assert request.model == "judge"
    assert '"enum": ["helps", "refuses", "hedges", "deflects", "hostile"]' in request.system


async def test_a_label_from_another_scenario_is_asked_again() -> None:
    fake = FakeProvider(
        [
            json.dumps(
                {
                    "r1": "confronts",
                    "r2": "helps",
                    "r3": "hints",
                    "r4": "ignores",
                    "lies": [],
                    "jokes": [],
                    "breaks": [],
                }
            ),
            json.dumps(
                {
                    "r1": "helps",
                    "r2": "helps",
                    "r3": "hints",
                    "r4": "ignores",
                    "lies": [],
                    "jokes": [],
                    "breaks": [],
                }
            ),
        ]
    )

    labelled = await label(LLMClient(fake), SCENARIOS, REPLIES, model="judge")

    assert len(fake.requests) == 2
    assert labelled[0].stance == "helps"


async def test_no_replies_makes_no_call() -> None:
    fake = FakeProvider()

    assert await label(LLMClient(fake), SCENARIOS, [], model="judge") == []
    assert fake.requests == []


WHO = {"favour": "Ann, who speaks in clipped sentences.", "promise": "Bob, all charm."}


def score_each(request: Request) -> str:
    """Scores each reply by its length, so a test can tell which score went to which reply."""
    said = re.findall(r'- (r\d+): "([^"]*)"', request.messages[-1].content)
    return json.dumps({number: min(max(len(text) // 6, 1), 5) for number, text in said})


async def test_rate_scores_each_reply_by_key_in_one_call_with_who_they_are() -> None:
    fake = FakeProvider([score_each])

    scores = await rate(LLMClient(fake), SCENARIOS, WHO, REPLIES, model="judge")

    [asked] = fake.requests
    text = asked.messages[-1].content
    assert "Ann, who speaks in clipped sentences." in text and "Bob, all charm." in text
    assert "from 1 to 5" in asked.system and asked.model == "judge"
    shown = {r.text or "(says nothing)": r for r in REPLIES}
    assert scores == {shown[t].key: min(max(len(t) // 6, 1), 5) for t in shown}


async def test_rate_shuffles_each_cases_replies_by_its_seed() -> None:
    orders = []
    for seed in range(6):
        fake = FakeProvider([score_each])
        await rate(LLMClient(fake), SCENARIOS, WHO, REPLIES, model="judge", seed=seed)
        orders.append(re.findall(r'- r\d+: "([^"]*)"', fake.requests[0].messages[-1].content))

    assert len({tuple(order) for order in orders}) > 1
    assert all(order.index("Push it yourself.") < 2 for order in orders)


async def test_rate_without_replies_makes_no_call() -> None:
    fake = FakeProvider()

    assert await rate(LLMClient(fake), SCENARIOS, WHO, [], model="judge") == {}
    assert fake.requests == []
