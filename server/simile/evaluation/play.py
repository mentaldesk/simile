import asyncio
import hashlib
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel

from simile.behaviour.scoring import savings
from simile.casting import Cast, Resident, history
from simile.conversation.config import DEFAULT_CONFIG, ConversationConfig
from simile.conversation.prompt import (
    Cue,
    Player,
    background,
    duration,
    first_name,
    jokes,
    parse_reply,
    system_prompt,
    turn_prompt,
)
from simile.conversation.temptation import (
    chance,
    found,
    honesty,
    lies,
    raised,
    standing,
    touched,
)
from simile.evaluation.scenarios import NOW, Scenario
from simile.llm import LLMClient, LLMError
from simile.memory import MemoryStore
from simile.schema import Character, HumourStyle, Id, Line, Memory, Npc
from simile.social import as_of, meet

logger = logging.getLogger(__name__)

PURPOSE = "evaluation"


class Reply(BaseModel):
    character: Id
    scenario: str
    model: str
    key: str
    raw: str
    text: str
    values: list[str] = []
    stance: str | None = None
    lies: bool | None = None
    jokes: bool | None = None
    joke: HumourStyle | None = None
    """The style of its joke, when it jokes."""
    directed: bool = False
    """Whether a lie roll gave the prompt a direction to lie."""
    joke_roll: bool | None = None
    """Whether a roll told it to joke, or not to. None without a humour."""


@dataclass(frozen=True)
class Prompt:
    system: str
    text: str
    names: tuple[str, ...]
    others: tuple[str, ...]
    lies: tuple[str, ...] = ()
    """The directions to lie a roll gave it."""
    joke: bool | None = None
    """Whether a roll told it to joke, or not to."""

    def key(self, model: str) -> str:
        """Changes whenever the model or anything in the prompt does."""
        return hashlib.sha256(f"{model}\0{self.system}\0{self.text}".encode()).hexdigest()[:16]


def resident(character: Character, now: datetime = NOW) -> tuple[Npc, Cast]:
    """The character cast alone, as P4 casts a village starting at `now`."""
    cast = Cast(
        game_date=now.date(), seed=0, residents=[Resident(character=character, home="home")]
    )
    return cast.npc(cast.residents[0]), cast


def prompt(
    character: Character,
    scenario: Scenario,
    now: datetime = NOW,
    config: ConversationConfig = DEFAULT_CONFIG,
    humour: bool = True,
) -> Prompt:
    """B5's system prompt and reply prompt for the character's answer to the scenario's line,
    without their humour unless `humour`. Rolls for lies and a joke are seeded by the scenario and
    the character."""
    if not humour:
        character = character.model_copy(update={"humour": None})
    npc, cast = resident(character, now)
    other = Player(name=scenario.name, description=scenario.description, id=scenario.other)
    with MemoryStore(":memory:") as memory:
        memory.add(*history(cast, now), *scenario.records(npc, now))
        stored = memory.relationship(npc.id, other.id)
        rel = as_of(stored, now) if stored else meet(npc, other.id)
        shared = memory.shared_history(npc.id, other.id, now, k=config.history)
        memories = on_mind(memory, npc.id, other.id, now, config)
        directed = tempted(character, npc, scenario, memory, now, config)
    said = Line(
        id=0,
        conversation_id=PURPOSE,
        speaker=other.id,
        text=scenario.line,
        timestamp=now,
        duration=duration(scenario.line, config),
    )
    text = turn_prompt(
        background(npc, other, rel, shared, memories, [], scenario.place, now),
        [said],
        {other.id: other.name, npc.id: first_name(npc)},
        Cue.REPLY,
        other.name,
        config,
        speaker=npc.id,
        lies=directed,
        joke=(joke := jokes(npc.humour, f"{PURPOSE}/{scenario.id}/{npc.id}")),
    )
    names = (first_name(npc), npc.name)
    return Prompt(system_prompt(npc, config), text, names, (other.name,), tuple(directed), joke)


def tempted(
    character: Character,
    npc: Npc,
    scenario: Scenario,
    memory: MemoryStore,
    now: datetime,
    config: ConversationConfig,
) -> list[str]:
    """B5's directions to lie about what the scenario's line touches, on a roll seeded by the
    scenario and the character."""
    names = {scenario.other: scenario.name}
    known = standing(
        npc,
        memory,
        now,
        [scenario.other],
        names,
        config,
        money=scenario.money,
        target=savings(npc.values),
        missed=scenario.missed(now),
    )
    every = [
        *found(known, scenario.other, now, config),
        *raised(scenario.line, scenario.name, npc.id),
    ]
    odds = chance(honesty(npc), character.traits, config)
    seed = f"{PURPOSE}/{scenario.id}/{npc.id}"
    return [
        temptation.direction()
        for temptation in every
        if touched(temptation, scenario.line) and lies(temptation, seed, odds)
    ]


def on_mind(
    memory: MemoryStore, npc: Id, other: Id, now: datetime, config: ConversationConfig
) -> list[Memory]:
    """The memories a speaker's prompt lists, picked as `ConversationEngine._memories` does."""
    found = [
        *memory.recall(npc, now, about=other, k=config.memories_about),
        *memory.recall(npc, now, k=config.memories_about + config.memories_recent),
    ]
    unique = list({m.content: m for m in found}.values())
    return unique[: config.memories_about + config.memories_recent]


async def play(
    llm: LLMClient,
    characters: Sequence[Character],
    scenarios: Sequence[Scenario],
    *,
    model: str,
    done: Sequence[Reply] = (),
    max_calls: int | None = None,
    on_reply: Callable[[Reply], None] = lambda reply: None,
    config: ConversationConfig = DEFAULT_CONFIG,
    humour: bool = True,
) -> list[Reply]:
    """Every character's reply to every scenario, reusing those in `done` whose prompt and model
    haven't changed. Starts at most `max_calls` calls; a reply that fails or isn't started is
    left out. Without `humour`, the prompts leave out the characters' humour."""
    reused = {reply.key: reply for reply in done}
    started = 0

    async def reply(character: Character, scenario: Scenario) -> Reply | None:
        nonlocal started
        asked = prompt(character, scenario, config=config, humour=humour)
        key = asked.key(model)
        if key in reused:
            return reused[key]
        if max_calls is not None and started >= max_calls:
            return None
        started += 1
        try:
            raw = await llm.complete(asked.text, system=asked.system, model=model, purpose=PURPOSE)
        except LLMError:
            logger.exception("No reply from %s to %s", character.id, scenario.id)
            return None
        draft = parse_reply(raw, asked.names, asked.others, config)
        made = Reply(
            character=character.id,
            scenario=scenario.id,
            model=model,
            key=key,
            raw=raw,
            text=draft.text,
            values=[value.value for value in draft.values],
            directed=bool(asked.lies),
            joke_roll=asked.joke,
        )
        on_reply(made)
        return made

    pairs = [(c, s) for c in characters for s in scenarios]
    replies = await asyncio.gather(*(reply(c, s) for c, s in pairs))
    return [r for r in replies if r is not None]
