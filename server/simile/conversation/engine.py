import asyncio
import itertools
import logging
import random
from collections import deque
from collections.abc import Callable, Iterator, Sequence
from contextlib import aclosing
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

from pydantic import JsonValue
from starlette.applications import Starlette

from simile.behaviour import Behaviour, Need
from simile.conversation.config import DEFAULT_CONFIG, ConversationConfig
from simile.conversation.engagement import (
    acceptance,
    accepts,
    engage,
    initial_engagement,
    leaving,
)
from simile.conversation.events import Direction, Facing, LineDrafted
from simile.conversation.prompt import (
    Cue,
    Draft,
    background,
    duration,
    first_name,
    parse_reply,
    system_prompt,
    turn_prompt,
)
from simile.llm import LLMClient
from simile.memory import SharedHistory
from simile.schema import PLAYER_ID, Conversation, CoreValue, Id, Line, Memory, Npc, Relationship
from simile.sim import Clock, ConversationEnded, ConversationStarted, EventBus, LineSpoken
from simile.social import as_of, meet
from simile.world import Point

logger = logging.getLogger(__name__)


class Memories(Protocol):
    def relationship(self, owner: str, about: str) -> Relationship | None: ...

    def recall(
        self, owner: str, now: datetime, *, about: str | None = None, k: int = 5
    ) -> list[Memory]: ...

    def shared_history(self, a: str, b: str, now: datetime, *, k: int = 10) -> SharedHistory: ...


@dataclass
class Party:
    npc: Npc
    system: str
    background: str
    like: float
    """How much they like the other person."""
    engagement: float
    facing: Direction


@dataclass
class Talk:
    conversation: Conversation
    parties: dict[Id, Party]
    speaker: Id
    """Whose line is being written or waiting to be spoken."""
    free_at: datetime
    """When the line being spoken, and the pause after it, ends."""
    cue: Cue = Cue.OPEN
    writing: asyncio.Task[Draft] | None = None
    pending: tuple[Line, tuple[CoreValue, ...]] | None = None
    """The next line, written and waiting for its turn, with the values it touches."""
    closing: bool = False
    """The last line has been spoken."""
    names: dict[Id, str] = field(default_factory=dict)

    def other(self, npc: Id) -> Id:
        return next(party for party in self.parties if party != npc)


class ConversationEngine:
    """NPC-NPC conversations, written a line ahead and spoken at talking pace. Tick it."""

    def __init__(
        self,
        clock: Clock,
        bus: EventBus,
        behaviour: Behaviour,
        memory: Memories,
        llm: Callable[[], LLMClient],
        *,
        line_ids: Iterator[int] | None = None,
        config: ConversationConfig = DEFAULT_CONFIG,
        seed: int | None = None,
    ) -> None:
        self.clock = clock
        self.bus = bus
        self.behaviour = behaviour
        self.memory = memory
        self.llm = llm
        self.line_ids = line_ids or itertools.count(1)
        self.config = config
        self.rng = random.Random(seed)
        self.finished: deque[Conversation] = deque(maxlen=config.keep_finished)
        self._talks: dict[str, Talk] = {}

    def request(self, a: Id, b: Id) -> bool:
        """B1's `request_conversation`: `b` accepts or declines `a`, who has walked up to them."""
        if PLAYER_ID in (a, b) or self.talking(a) or self.talking(b):
            return False
        if len(self._talks) >= self.config.max_conversations:
            self._log("%s and %s can't talk: %d conversations going on", a, b, len(self._talks))
            return False
        target = self.behaviour.npcs[b]
        score = acceptance(
            target.values,
            self._relationship(b, a),
            self.behaviour.goal(b),
            self.behaviour.needs(b)[Need.SOCIAL],
            self.config,
        )
        accepted = accepts(score, self.rng, self.config)
        verdict = "accepted" if accepted else "declined"
        self._log("%s asked %s to talk: %s (score %.2f)", a, b, verdict, score)
        if accepted:
            self.start(a, b)
        return accepted

    def start(self, a: Id, b: Id) -> Conversation:
        """Start a conversation that `a` opens, whatever `b` thinks of it."""
        now = self.clock.now
        movement = self.behaviour.movement
        here, there = movement.position(a), movement.position(b)
        parties = {
            a: self._party(a, b, facing(here, there)),
            b: self._party(b, a, facing(there, here)),
        }
        conversation = Conversation(
            id=f"{now:%Y%m%dT%H%M%S}-{a}-{b}", participants=[a, b], started=now
        )
        talk = Talk(
            conversation,
            parties,
            speaker=a,
            free_at=now,
            names={npc: first_name(party.npc) for npc, party in parties.items()},
        )
        self._talks[conversation.id] = talk
        for npc, party in parties.items():
            other = talk.other(npc)
            self.behaviour.pause(npc, other)
            self.bus.publish(Facing(npc, other, party.facing))
        self.bus.publish(ConversationStarted(conversation.model_copy(deep=True)))
        return conversation

    def tick(self, dt: float) -> None:
        for talk in tuple(self._talks.values()):
            self._advance(talk)

    def live(self) -> list[Conversation]:
        """Conversations going on, with their lines so far, for the snapshot."""
        return [talk.conversation.model_copy(deep=True) for talk in self._talks.values()]

    def conversation(self, conversation_id: str) -> Conversation | None:
        """A live or recently finished conversation, with all its lines."""
        talk = self._talks.get(conversation_id)
        if talk is not None:
            return talk.conversation.model_copy(deep=True)
        found = next((c for c in self.finished if c.id == conversation_id), None)
        return found.model_copy(deep=True) if found else None

    def talking(self, npc: Id) -> bool:
        return self._talk_of(npc) is not None

    def state(self, npc: Id) -> dict[str, JsonValue]:
        """The NPC's conversation, for the debug overlay."""
        talk = self._talk_of(npc)
        if talk is None:
            return {"conversation": None}
        party = talk.parties[npc]
        return {
            "conversation": talk.conversation.id,
            "talking_to": talk.other(npc),
            "engagement": round(party.engagement, 3),
            "facing": party.facing,
            "leaving": talk.cue is Cue.GOODBYE and talk.speaker == npc,
        }

    async def close(self) -> None:
        """Stop writing lines. Conversations still going on are left as they are."""
        tasks = [talk.writing for talk in self._talks.values() if talk.writing]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def _advance(self, talk: Talk) -> None:
        now = self.clock.now
        if talk.closing:
            if now >= talk.free_at:
                self._end(talk)
            return
        if talk.writing is not None and talk.writing.done():
            task, talk.writing = talk.writing, None
            if not self._drafted(talk, task):
                talk.closing = True
                return
        if talk.pending is not None and now >= talk.pending[0].timestamp:
            self._speak(talk)
        if not talk.closing and talk.writing is None and talk.pending is None:
            lines = list(talk.conversation.lines)
            talk.writing = asyncio.get_running_loop().create_task(
                self._write(talk, talk.speaker, talk.cue, lines)
            )

    async def _write(self, talk: Talk, speaker: Id, cue: Cue, lines: Sequence[Line]) -> Draft:
        party, other = talk.parties[speaker], talk.parties[talk.other(speaker)]
        prompt = turn_prompt(
            party.background, lines, talk.names, cue, first_name(other.npc), self.config
        )
        stream = self.llm().stream(
            prompt, system=party.system, model=self.config.model, purpose="conversation"
        )
        async with asyncio.timeout(self.config.line_timeout), aclosing(stream) as chunks:
            text = "".join([chunk async for chunk in chunks])
        return parse_reply(
            text,
            [talk.names[speaker], party.npc.name],
            [talk.names[talk.other(speaker)], other.npc.name],
        )

    def _drafted(self, talk: Talk, task: asyncio.Task[Draft]) -> bool:
        if task.cancelled():
            return False
        if error := task.exception():
            logger.warning(
                "Couldn't write %s's line in %s: %r", talk.speaker, talk.conversation.id, error
            )
            return False
        draft = task.result()
        if not draft.text:
            logger.warning("%s's line in %s came back empty", talk.speaker, talk.conversation.id)
            return False
        line = Line(
            id=next(self.line_ids),
            conversation_id=talk.conversation.id,
            speaker=talk.speaker,
            text=draft.text,
            timestamp=max(self.clock.now, talk.free_at),
            duration=round(duration(draft.text, self.config), 2),
        )
        talk.pending = (line, draft.values)
        self.bus.publish(LineDrafted(line))
        return True

    def _speak(self, talk: Talk) -> None:
        assert talk.pending is not None
        (line, values), talk.pending = talk.pending, None
        talk.conversation.lines.append(line)
        self.bus.publish(LineSpoken(line))
        for party in talk.parties.values():
            party.engagement = engage(
                party.engagement, party.npc.values, party.like, values, self.config
            )
        ends = line.timestamp + timedelta(seconds=line.duration)
        talk.free_at = ends + timedelta(seconds=self.config.turn_gap)
        said = talk.cue
        talk.speaker = talk.other(talk.speaker)
        if said is Cue.GOODBYE and self.config.farewell:
            talk.cue = Cue.FAREWELL
        elif said in (Cue.GOODBYE, Cue.FAREWELL):
            talk.closing, talk.free_at = True, ends
        elif leaving(
            talk.parties[talk.speaker].engagement, len(talk.conversation.lines), self.config
        ):
            talk.cue = Cue.GOODBYE
            self._log(
                "%s is leaving %s (engagement %.2f)",
                talk.speaker,
                talk.conversation.id,
                talk.parties[talk.speaker].engagement,
            )
        else:
            talk.cue = Cue.REPLY

    def _end(self, talk: Talk) -> None:
        now = self.clock.now
        conversation = talk.conversation
        conversation.ended = now
        del self._talks[conversation.id]
        self.finished.append(conversation)
        self._log(
            "%s ended after %d lines (engagement %s)",
            conversation.id,
            len(conversation.lines),
            ", ".join(f"{npc} {party.engagement:.2f}" for npc, party in talk.parties.items()),
        )
        self.bus.publish(ConversationEnded(conversation.model_copy(deep=True)))
        cooldown = now + timedelta(minutes=self.config.cooldown)
        for npc in talk.parties:
            mind = self.behaviour.minds.get(npc)
            if mind is not None:
                mind.cooldowns[talk.other(npc)] = cooldown
            self.behaviour.resume(npc)

    def _party(self, npc: Id, other: Id, direction: Direction) -> Party:
        now = self.clock.now
        speaker, them = self.behaviour.npcs[npc], self.behaviour.npcs[other]
        rel = self._relationship(npc, other)
        topics = self._topics(npc, now)
        location = self.behaviour.places.at(self.behaviour.movement.position(npc))
        return Party(
            npc=speaker,
            system=system_prompt(speaker, self.config),
            background=background(
                speaker,
                them,
                rel,
                self.memory.shared_history(npc, other, now, k=self.config.history),
                self._memories(npc, other, now, topics),
                topics,
                location.name if location else None,
                now,
            ),
            like=rel.like,
            engagement=initial_engagement(speaker.values, rel.like, self.config),
            facing=direction,
        )

    def _relationship(self, owner: Id, about: Id) -> Relationship:
        stored = self.memory.relationship(owner, about)
        return as_of(stored, self.clock.now) if stored else meet(self.behaviour.npcs[owner], about)

    def _memories(self, npc: Id, other: Id, now: datetime, topics: list[Memory]) -> list[Memory]:
        config = self.config
        found = [
            *self.memory.recall(npc, now, about=other, k=config.memories_about),
            *self.memory.recall(npc, now, k=config.memories_about + config.memories_recent),
        ]
        seen = {memory.content for memory in topics}
        unique = []
        for memory in found:
            if memory.content not in seen:
                seen.add(memory.content)
                unique.append(memory)
        return unique[: config.memories_about + config.memories_recent]

    def _topics(self, npc: Id, now: datetime) -> list[Memory]:
        if not self.config.topics:
            return []
        try:
            from simile.news.reactions import topics_to_raise
        except ImportError:
            return []
        try:
            return topics_to_raise(self.memory, npc, now, k=self.config.topics)
        except Exception:
            logger.exception("Couldn't get %s's news topics", npc)
            return []

    def _log(self, message: str, *args: object) -> None:
        logger.info(f"%s  {message}", self.clock, *args)

    def _talk_of(self, npc: Id) -> Talk | None:
        return next((talk for talk in self._talks.values() if npc in talk.parties), None)


def facing(here: Point, there: Point) -> Direction:
    dx, dy = there.x - here.x, there.y - here.y
    if dx == dy == 0:
        return "down"
    if abs(dx) >= abs(dy):
        return "right" if dx > 0 else "left"
    return "down" if dy > 0 else "up"


def line_ids(app: Starlette) -> Iterator[int]:
    """The server's line ids, unique across the world, on `app.state.line_ids`."""
    if not hasattr(app.state, "line_ids"):
        app.state.line_ids = itertools.count(1)
    return app.state.line_ids


def conversations_of(app: Starlette) -> ConversationEngine:
    """The server's engine on `app.state.conversation`, created on first use."""
    if not hasattr(app.state, "conversation"):
        app.state.conversation = create_engine(app)
    return app.state.conversation


def create_engine(
    app: Starlette, *, config: ConversationConfig = DEFAULT_CONFIG, seed: int | None = None
) -> ConversationEngine:
    from simile.behaviour import behaviour_of
    from simile.memory import memory_of
    from simile.sim import world_of

    world = world_of(app)
    return ConversationEngine(
        world.clock,
        world.bus,
        behaviour_of(app),
        memory_of(app),
        lambda: app.state.llm,
        line_ids=line_ids(app),
        config=config,
        seed=seed,
    )
