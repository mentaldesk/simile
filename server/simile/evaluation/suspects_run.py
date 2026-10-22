import json
import logging
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from simile.conversation.config import DEFAULT_CONFIG, ConversationConfig
from simile.conversation.prompt import parse_reply
from simile.evaluation.judge import label, rate
from simile.evaluation.play import Reply
from simile.evaluation.run import check_writable
from simile.evaluation.suspects import (
    PURPOSE,
    SEEDS,
    Case,
    cases,
    incident,
    prompt,
    scenario,
    sketch,
    written,
)
from simile.llm import CallRecord, LLMClient, LLMError
from simile.llm.claude_code import ClaudeCodeProvider
from simile.schema import Npc
from simile.story.writing import Backstory

logger = logging.getLogger(__name__)

REPLIES = "replies.json"
REPORT = "report.md"
BACKSTORIES = "backstories.json"


class Voiced(Reply):
    """A liar's reply, with how long it took and what it cost."""

    first_word: float | None = None
    seconds: float | None = None
    tokens: int | None = None
    cost_usd: float | None = None
    """What it would have cost on the API, for a Claude reply."""
    in_character: int | None = None
    """The judge's score, from 1 to 5."""


@dataclass(frozen=True)
class Comparison:
    cases: list[Case]
    replies: list[Voiced]
    missing: int
    calls: dict[str, int]
    """Claude calls by model, this run's and those of earlier runs into the same folder."""
    written: list[int]
    """The seeds whose covers Sonnet wrote, rather than the templates."""


def load(out: Path | None) -> tuple[list[Voiced], Counter[str], dict[int, Backstory]]:
    """The replies, Claude calls and backstories that earlier runs saved in `out`."""
    replies, calls, stories = [], Counter[str](), {}
    if out is not None and (out / REPLIES).exists():
        saved = json.loads((out / REPLIES).read_text(encoding="utf-8"))
        replies = [Voiced.model_validate(reply) for reply in saved["replies"]]
        calls.update(saved["calls"])
    if out is not None and (out / BACKSTORIES).exists():
        saved = json.loads((out / BACKSTORIES).read_text(encoding="utf-8"))
        stories = {int(seed): Backstory.model_validate(story) for seed, story in saved.items()}
    return replies, calls, stories


def save(out: Path, replies: Sequence[Voiced], calls: Counter[str]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    saved = {"calls": dict(calls), "replies": [reply.model_dump() for reply in replies]}
    path = out / REPLIES
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(saved, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def save_stories(out: Path, stories: dict[int, Backstory]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    saved = {str(seed): story.model_dump() for seed, story in sorted(stories.items())}
    (out / BACKSTORIES).write_text(json.dumps(saved, indent=2, ensure_ascii=False) + "\n")


async def compare(
    llm: LLMClient,
    npcs: Sequence[Npc],
    *,
    models: Sequence[str],
    judge: str,
    seeds: Sequence[int] = SEEDS,
    out: Path | None = None,
    write: bool = False,
    max_calls: int | None = None,
    config: ConversationConfig = DEFAULT_CONFIG,
) -> Comparison:
    """Each model's reply to every case, one call at a time, then judged. See the README's S14."""
    if out is not None:
        check_writable(out)
    done, calls, stories = load(out)
    reused = {reply.key: reply for reply in done}
    records: list[CallRecord] = []

    def called(record: CallRecord) -> None:
        records.append(record)
        if record.provider == ClaudeCodeProvider.name:
            calls[record.model] += 1

    llm.listeners.append(called)
    try:
        if write:
            for seed in seeds:
                if seed not in stories and (story := await written(llm, npcs, seed)):
                    stories[seed] = story
                    if out is not None:
                        save_stories(out, stories)
        every = [
            case
            for seed in seeds
            for case in cases(incident(npcs, seed, stories.get(seed)), npcs, seed)
        ]
        replies: list[Voiced] = []
        started = 0
        for model in models:
            for case in every:
                asked = prompt(case, config)
                key = asked.key(model)
                if key in reused:
                    replies.append(reused[key])
                    continue
                if max_calls is not None and started >= max_calls:
                    continue
                started += 1
                try:
                    raw = await llm.complete(
                        asked.text, system=asked.system, model=model, purpose=PURPOSE
                    )
                except LLMError:
                    logger.exception("No reply from %s to %s", model, case.id)
                    continue
                record = records[-1]
                usage = record.usage
                draft = parse_reply(raw, asked.names, asked.others, config)
                replies.append(
                    Voiced(
                        character=case.npc.id,
                        scenario=case.id,
                        model=model,
                        key=key,
                        raw=raw,
                        text=draft.text,
                        values=[value.value for value in draft.values],
                        directed=bool(asked.lies),
                        joke_roll=asked.joke,
                        first_word=None if record.ttft_ms is None else record.ttft_ms / 1000,
                        seconds=record.latency_ms / 1000,
                        tokens=usage.output_tokens if usage else None,
                        cost_usd=usage.cost_usd if usage else None,
                    )
                )
                if out is not None:
                    save(out, merged(replies, done), calls)
        missing = len(every) * len(models) - len(replies)
        if not missing:
            replies = await judged(llm, every, replies, judge)
    finally:
        llm.listeners.remove(called)
    if out is not None:
        save(out, merged(replies, done), calls)
        if stories:
            save_stories(out, stories)
    return Comparison(every, replies, missing, dict(calls), sorted(stories))


async def judged(
    llm: LLMClient, every: Sequence[Case], replies: Sequence[Voiced], judge: str
) -> list[Voiced]:
    """`replies` labelled as #298's judge labels them, and scored for character, where not yet."""
    scenarios = [scenario(case) for case in every]
    unlabelled = [r for r in replies if r.stance is None or r.breaks is None or r.lies is None]
    labelled = {r.key: r for r in await label(llm, scenarios, unlabelled, model=judge)}
    replies = [labelled.get(r.key, r) for r in replies]
    unrated = [r for r in replies if r.in_character is None]
    who = {case.id: sketch(case.npc) for case in every}
    scores = await rate(llm, scenarios, who, unrated, model=judge)
    return [
        r.model_copy(update={"in_character": scores[r.key]}) if r.key in scores else r
        for r in replies
    ]


def merged(replies: Sequence[Voiced], done: Sequence[Voiced]) -> list[Voiced]:
    keys = {reply.key for reply in replies}
    return [*replies, *(reply for reply in done if reply.key not in keys)]
