from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, create_model

from simile.evaluation.play import Reply
from simile.evaluation.scenarios import Scenario
from simile.llm import LLMClient

PURPOSE = "evaluation-stance"

SYSTEM = (
    "You label replies from a life simulation. In each situation someone says one line to a "
    "character, and the character replies. For each reply, choose the one label that best fits "
    "what the reply does, going by the label's meaning rather than its name. Judge the words "
    "alone, and pick the label for its main move when it does more than one thing."
)


def judge_prompt(scenarios: Sequence[Scenario], replies: Sequence[Reply]) -> str:
    """Each situation with its labels and its replies, numbered r1, r2, ... in order."""
    numbers = {reply.key: f"r{n}" for n, reply in enumerate(replies, 1)}
    parts = []
    for scenario in scenarios:
        theirs = [reply for reply in replies if reply.scenario == scenario.id]
        if not theirs:
            continue
        labels = "\n".join(f"- {label}: {meaning}" for label, meaning in scenario.stances.items())
        said = "\n".join(
            f'- {numbers[reply.key]}: "{reply.text or "(says nothing)"}"' for reply in theirs
        )
        parts.append(
            f"## {scenario.title}\n{scenario.situation}\n"
            f'{scenario.name} says: "{scenario.line}"\n\nLabels:\n{labels}\n\nReplies:\n{said}'
        )
    return "\n\n".join(parts)


def stance_schema(scenarios: Sequence[Scenario], replies: Sequence[Reply]) -> type[BaseModel]:
    """One field per reply, r1, r2, ..., that takes only its scenario's labels."""
    labels = {scenario.id: tuple(scenario.stances) for scenario in scenarios}
    fields: dict[str, Any] = {
        f"r{n}": (Literal[labels[reply.scenario]], ...) for n, reply in enumerate(replies, 1)
    }
    return create_model("Stances", **fields)


async def label(
    llm: LLMClient, scenarios: Sequence[Scenario], replies: Sequence[Reply], *, model: str
) -> list[Reply]:
    """`replies` with their stances, labelled in one structured call, grouped by scenario."""
    if not replies:
        return []
    order = [scenario.id for scenario in scenarios]
    replies = sorted(replies, key=lambda reply: order.index(reply.scenario))
    found = await llm.structured(
        judge_prompt(scenarios, replies),
        stance_schema(scenarios, replies),
        system=SYSTEM,
        model=model,
        purpose=PURPOSE,
    )
    stances = found.model_dump()
    return [
        reply.model_copy(update={"stance": stances[f"r{n}"]}) for n, reply in enumerate(replies, 1)
    ]
