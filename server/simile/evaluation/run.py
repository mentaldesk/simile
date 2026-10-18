import json
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from simile.characters.novelty import Embedder
from simile.characters.pool import CONTENT_DIR, within
from simile.evaluation.judge import label
from simile.evaluation.metric import Spread, spread
from simile.evaluation.play import Reply, play
from simile.evaluation.report import Run, report
from simile.evaluation.scenarios import SCENARIOS, Scenario
from simile.llm import CallRecord, FakeProvider, LLMClient
from simile.memory.store import DEFAULT_PATH
from simile.schema import Character, Id

REPLIES = "replies.json"
REPORT = "report.md"
MAX_WITH_CLAUDE = 10
"""Most characters a run that calls Claude may take."""


class Refused(ValueError):
    pass


@dataclass(frozen=True)
class Evaluation:
    replies: list[Reply]
    missing: int
    calls: int
    """Claude calls so far, this run's and those of earlier runs into the same folder."""
    spread: Spread | None = None
    report: str | None = None


def choose(
    pool: Sequence[Character], count: int, seed: int, picks: Sequence[Id] = ()
) -> list[Character]:
    """The picks, or `count` characters drawn at random, in id order."""
    library = {character.id: character for character in pool}
    if picks:
        if unknown := [id for id in picks if id not in library]:
            raise Refused(f"No character {', '.join(unknown)} in the pool")
        return sorted((library[id] for id in dict.fromkeys(picks)), key=lambda c: c.id)
    if not 1 < count <= len(library):
        raise Refused(f"Choose between 2 and {len(library)} characters, not {count}")
    drawn = random.Random(seed).sample(sorted(library), count)
    return sorted((library[id] for id in drawn), key=lambda c: c.id)


def check_writable(out: Path) -> None:
    """Refuse content/ and the default save's folder."""
    for folder in (CONTENT_DIR, DEFAULT_PATH.parent):
        if within(out, folder):
            raise Refused(f"won't write in {folder}")


def load(out: Path | None) -> tuple[list[Reply], int]:
    """The replies and the call count saved in `out` by earlier runs."""
    path = out / REPLIES if out else None
    if path is None or not path.exists():
        return [], 0
    saved = json.loads(path.read_text(encoding="utf-8"))
    return [Reply.model_validate(reply) for reply in saved["replies"]], saved["calls"]


def save(out: Path, replies: Sequence[Reply], calls: int) -> None:
    out.mkdir(parents=True, exist_ok=True)
    saved = {"calls": calls, "replies": [reply.model_dump() for reply in replies]}
    path = out / REPLIES
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(saved, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


async def evaluate(
    llm: LLMClient,
    characters: Sequence[Character],
    embedder: Embedder,
    *,
    model: str,
    judge: str,
    run: Callable[[int], Run],
    out: Path | None = None,
    max_calls: int | None = None,
    scenarios: Sequence[Scenario] = SCENARIOS,
) -> Evaluation:
    """Play every scenario for every character, label the stances and measure the spread.
    With `out`, replies are saved there as they come and reused by a later run. `run` describes
    the run for the report, given the call count."""
    if out is not None:
        check_writable(out)
    done, earlier = load(out)
    made: list[Reply] = []
    records: list[CallRecord] = []

    def called(record: CallRecord) -> None:
        if record.provider != FakeProvider.name:
            records.append(record)

    llm.listeners.append(called)

    def kept(reply: Reply) -> None:
        made.append(reply)
        if out is not None:
            save(out, [*done, *made], earlier + len(records))

    try:
        replies = await play(
            llm, characters, scenarios, model=model, done=done, max_calls=max_calls, on_reply=kept
        )
        missing = len(characters) * len(scenarios) - len(replies)
        if not missing and (unlabelled := [r for r in replies if r.stance is None]):
            labelled = {r.key: r for r in await label(llm, scenarios, unlabelled, model=judge)}
            replies = [labelled.get(r.key, r) for r in replies]
    finally:
        llm.listeners.remove(called)
    calls = earlier + len(records)
    if out is not None:
        keys = {r.key for r in replies}
        save(out, [*replies, *(r for r in done if r.key not in keys)], calls)
    if missing:
        return Evaluation(replies, missing, calls)
    measured = spread(characters, scenarios, replies, embedder)
    text = report(measured, replies, run(calls))
    if out is not None:
        (out / REPORT).write_text(text, encoding="utf-8")
    return Evaluation(replies, 0, calls, measured, text)
