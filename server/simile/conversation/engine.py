import asyncio
import itertools
import logging
import random
import sys
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import aclosing
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

from pydantic import JsonValue
from starlette.applications import Starlette

from simile.behaviour import Behaviour, Need
from simile.conversation.config import DEFAULT_CONFIG, ConversationConfig
from simile.conversation.engagement import acceptance, accepts, engage, initial_engagement
from simile.conversation.events import Direction, Facing, LineDrafted
from simile.conversation.loans import Ask, Loan, Purse, arrange, told
from simile.conversation.needs import Pressing, critical, pressing
from simile.conversation.plan import PRESSING, Plan, plan, stance
from simile.conversation.plans import already, can_do
from simile.conversation.prompt import (
    Player,
    WorkTopic,
    background,
    duration,
    first_name,
    system_prompt,
    takes_leave,
)
from simile.conversation.script import (
    Character,
    ScriptLine,
    ScriptParser,
    continue_prompt,
    scene_prompt,
    script_system,
)
from simile.conversation.temptation import (
    Kind,
    Lie,
    Missed,
    Temptation,
    chance,
    found,
    honesty,
    lie,
    lies,
    standing,
    touched,
)
from simile.llm import LLMClient
from simile.memory import SharedHistory
from simile.memory.store import recency
from simile.schema import (
    PLAYER_ID,
    Conversation,
    CoreValue,
    FlagKind,
    Id,
    Line,
    Memory,
    MemoryKind,
    NewsItem,
    Npc,
    Relationship,
    Work,
)
from simile.sim import Clock, ConversationEnded, ConversationStarted, EventBus, LineSpoken
from simile.social import as_of, meet, traits_of
from simile.voice import speaking_rate
from simile.world import Point

logger = logging.getLogger(__name__)

RECHECK = timedelta(seconds=0.1)
PLAYER = "player"
"""Why a resident leaves a conversation when the player starts one with them."""

GOODBYES: dict[str, tuple[str, ...]] = {
    PLAYER: (
        "Sorry, {name}, I'd better say hello to our newcomer. Catch you later.",
        "Oh, excuse me, {name}, someone's after me. Talk later.",
        "Hang on, {name}, I'm wanted. See you soon.",
    ),
    Need.REST: ("Sorry, {name}, I'm flagging. I'll head off. See you.",),
    Need.NEWS: ("I must catch up on the news, {name}. See you later.",),
    Need.CURIOSITY: ("Sorry, {name}, I must get on. Catch you later.",),
    Need.HUNGER: (
        "Sorry, {name}, I'm starving. I'd better get something to eat. See you.",
        "I need some food, {name}, I'm running on empty. Catch you later.",
    ),
}
FAREWELLS = ("Bye, {name}.", "See you, {name}.")


class Memories(Protocol):
    def relationship(self, owner: str, about: str) -> Relationship | None: ...

    def relationships(self, owner: str) -> list[Relationship]: ...

    def recall(
        self,
        owner: str,
        now: datetime,
        *,
        about: str | None = None,
        kind: MemoryKind | None = None,
        k: int = 5,
        half_life: timedelta = ...,
    ) -> list[Memory]: ...

    def shared_history(self, a: str, b: str, now: datetime, *, k: int = 10) -> SharedHistory: ...


class Audio(Protocol):
    """I1's view of the audio it makes for each line."""

    def duration(self, line: Line) -> float | None:
        """How long the line's audio plays, once it's all made."""
        ...

    def remaining(self, line: Line) -> float | None:
        """Seconds until the line's audio has played, or None while it's still being made."""
        ...


@dataclass
class Party:
    npc: Npc
    like: float
    """How much they like the other person."""
    engagement: float
    facing: Direction
    system: str = ""
    background: str = ""
    works: list[WorkTopic] = field(default_factory=list)
    """Works they might bring up, in a conversation written a line at a time."""
    topics: list[Memory] = field(default_factory=list)
    """News they might bring up, in a conversation written a line at a time."""
    temptations: list[Temptation] = field(default_factory=list)
    """What they'd rather not own up to, in a conversation written a line at a time."""


@dataclass
class Talk:
    conversation: Conversation
    parties: dict[Id, Party]
    free_at: datetime
    """When the line being spoken, and the pause after it, ends."""
    names: dict[Id, str] = field(default_factory=dict)
    closing: bool = False
    """The last line has been spoken."""
    writing: asyncio.Task[Any] | None = None

    def other(self, npc: Id) -> Id:
        return next(other for other in self.conversation.participants if other != npc)

    def leaving(self, npc: Id) -> bool:
        """Whether `npc` is saying goodbye."""
        return False


@dataclass(kw_only=True)
class Scene(Talk):
    """A conversation between two residents, written as one script and played line by line."""

    plan: Plan
    prompt: str
    """Both sides, what's between them and the direction."""
    needs: dict[Id, dict[Need, float]]
    """Each side's needs when it started."""
    script: deque[ScriptLine] = field(default_factory=deque)
    """Lines streamed and not yet drafted."""
    written: list[ScriptLine] = field(default_factory=list)
    asked: int = 0
    """Lines written when the latest call was made."""
    retried: bool = False
    continued: bool = False
    streamed: bool = False
    """No more lines are coming."""
    pending: tuple[Line, tuple[CoreValue, ...]] | None = None
    """The next line, drafted and waiting for its turn, with the values it touches."""
    leaver: Id | None = None
    """Who was pulled away, cutting it short."""
    touched: set[CoreValue] = field(default_factory=set)

    def leaving(self, npc: Id) -> bool:
        if self.leaver is not None:
            return self.leaver == npc
        line = self.pending[0] if self.pending else None
        return line is not None and line.speaker == npc and takes_leave(line.text)


class ConversationEngine:
    """Conversations between NPCs, each written as one script and spoken at talking pace, and
    the player's, which `PlayerConversations` runs. Tick it."""

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
        self.player = Player()
        self.player_request: Callable[[Id, Id], bool] | None = None
        """Answers requests involving the player, which this engine declines without it."""
        self.audio: Audio | None = None
        """The audio being made for each line, which I1 sets while the server is voiced."""
        self.article: Callable[[str], NewsItem | None] = lambda _: None
        """B4's article by id, for what its news topics are about."""
        self.work: Callable[[str], Work | None] = lambda _: None
        """A work by id, for the works residents might bring up."""
        self.missed: Callable[[Id], list[Missed]] = lambda _: []
        """E3's shifts a resident skipped or was late to."""
        self._talks: dict[str, Talk] = {}
        self._loans: dict[str, Loan] = {}
        self._lies: dict[str, list[Lie]] = {}
        self._declined: dict[tuple[Id, Id], datetime] = {}
        """When each lender last turned each borrower down."""

    def request(self, a: Id, b: Id) -> bool:
        """B1's `request_conversation`: `b` accepts or declines `a`, who has walked up to them."""
        if PLAYER_ID in (a, b):
            return self.player_request is not None and self.player_request(a, b)
        if self.talking(a) or self.talking(b):
            return False
        going = sum(isinstance(talk, Scene) for talk in self._talks.values())
        if going >= self.config.max_conversations:
            self._log("%s and %s can't talk: %d conversations going on", a, b, going)
            return False
        score = self.accept_score(a, b)
        accepted = accepts(score, self.rng, self.config)
        verdict = "accepted" if accepted else "declined"
        self._log("%s asked %s to talk: %s (score %.2f)", a, b, verdict, score)
        if accepted:
            self.start(a, b)
        return accepted

    def accept_score(self, a: Id, b: Id) -> float:
        """How keen `b` is to talk if `a` walks up to them now: positive accepts at
        `accept_temperature` 0."""
        return acceptance(
            self.behaviour.npcs[b].values,
            self._relationship(b, a),
            self.behaviour.goal(b),
            self.behaviour.needs(b)[Need.SOCIAL],
            self.config,
            urgent=self.pressing(b).urgent,
        )

    def pressing(self, npc: Id) -> Pressing:
        """What `npc`'s needs bring to a conversation now."""
        return pressing(self.behaviour.needs(npc), self._critical(), self.config)

    def start(self, a: Id, b: Id) -> Conversation:
        """Start a conversation that `a` opens, whatever `b` thinks of it. Its script is asked
        for on the next tick."""
        now, config = self.clock.now, self.config
        npcs, movement = self.behaviour.npcs, self.behaviour.movement
        here, there = movement.position(a), movement.position(b)
        names = {a: first_name(npcs[a]), b: first_name(npcs[b])}
        rels = {a: self._relationship(a, b), b: self._relationship(b, a)}
        topics = {npc: self._topics(npc, now) for npc in names}
        works = self._scene_works(a, b, now)
        on_table = [
            topic
            for npc in names
            for topic in self._topic_values(npcs[npc], topics[npc], works[npc])
        ]
        needs = {npc: self.behaviour.needs(npc) for npc in names}
        conversation = Conversation(
            id=f"{now:%Y%m%dT%H%M%S}-{a}-{b}", participants=[a, b], started=now
        )
        stances = {
            npc: stance(
                npcs[npc].values,
                rels[npc],
                self.behaviour.goal(npc),
                needs[npc],
                on_table,
                names[other],
                config,
                critical=self._critical(),
            )
            for npc, other in ((a, b), (b, a))
        }
        loan = self._loan(a, b, rels)
        sides = {
            npc: Character(
                npcs[npc],
                rels[npc],
                self._memories(npc, other, now, [*topics[npc], *noted(works[npc])]),
                topics[npc],
                self._secrets(npc, other),
                works[npc],
                self._plans(npc, names[npc]),
            )
            for npc, other in ((a, b), (b, a))
        }
        history = self.memory.shared_history(a, b, now, k=config.history)
        lying = self._scene_lies(conversation.id, sides, history, loan)
        scene_plan = plan(
            names,
            stances,
            a,
            config,
            loan=loan,
            lies=[set_up.said for set_up in lying],
            humours={npc: npcs[npc].humour for npc in names},
            seed=conversation.id,
        )
        location = self.behaviour.places.at(here)
        prompt = scene_prompt(
            sides[a], sides[b], history, location.name if location else None, now, scene_plan
        )
        directions = {a: facing(here, there), b: facing(there, here)}
        parties = {
            npc: Party(npcs[npc], rels[npc].like, stances[npc].keen, directions[npc])
            for npc in names
        }
        scene = Scene(
            conversation, parties, now, names, plan=scene_plan, prompt=prompt, needs=needs
        )
        self._talks[conversation.id] = scene
        for npc, party in parties.items():
            other = scene.other(npc)
            self.behaviour.pause(npc, other)
            self.bus.publish(Facing(npc, other, party.facing))
        self.bus.publish(ConversationStarted(conversation.model_copy(deep=True)))
        self._log(
            "%s planned for %d lines, %s leaving (keen %s)",
            conversation.id,
            scene_plan.length,
            scene_plan.leaver,
            ", ".join(f"{npc} {stances[npc].keen:.2f}{felt(stances[npc].mood)}" for npc in names),
        )
        if loan is not None:
            self._loans[conversation.id] = loan
            if isinstance(loan, Ask) and not loan.lends:
                self._declined[(loan.borrower, loan.lender)] = now
            self._log("%s: %s", conversation.id, told(loan, names))
        for set_up in lying:
            self._log("%s: %s", conversation.id, set_up.said)
        return conversation

    def settle(self, conversation_id: str) -> Loan | None:
        """For B3, once: the loan a live or recently finished scene was set up to settle. Until
        then it's pending, and no other scene between the two settles anything."""
        return self._loans.pop(conversation_id, None)

    def lies(self, conversation_id: str) -> list[Lie]:
        """For B3, once: the lies a live or recently finished conversation set someone up to
        tell."""
        return self._lies.pop(conversation_id, [])

    def tempted(self, npc: Id, listener: Id) -> list[Temptation]:
        """What the game knows `npc` would rather not own up to, talking with `listener`."""
        resident, now = self.behaviour.npcs[npc], self.clock.now
        money = self.behaviour.hooks.money(resident)
        workplace = resident.workplace
        known = standing(
            resident,
            self.memory,
            now,
            self.behaviour.npcs,
            {id: self._name(id) for id in [*self.behaviour.npcs, PLAYER_ID]},
            self.config,
            money=money if isinstance(money, int | float) else None,
            target=self.behaviour.savings(npc),
            missed=self.missed(npc),
            workplace=self.behaviour.places.location(workplace).name if workplace else None,
            work=self.work,
        )
        return found(known, listener, now, self.config)

    def lies_about(self, temptation: Temptation, conversation_id: str) -> bool:
        """The roll, seeded by the conversation."""
        npc = self.behaviour.npcs[temptation.owner]
        odds = chance(honesty(npc), traits_of(npc.id), self.config)
        return lies(temptation, conversation_id, odds)

    def tell(self, conversation_id: str, temptation: Temptation, listener: Id) -> Lie:
        """Set `temptation`'s owner up to lie about it to `listener`, for B3."""
        names = {id: self._name(id) for id in (temptation.owner, listener)}
        lying = lie(temptation, listener, names)
        self._lies.setdefault(conversation_id, []).append(lying)
        return lying

    def tick(self, dt: float) -> None:
        for talk in tuple(self._talks.values()):
            if isinstance(talk, Scene):
                self._play(talk)

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
            "leaving": talk.leaving(npc),
        }

    def end(self, conversation_id: str) -> Conversation | None:
        """End a live conversation now, at its last spoken line, dropping any line still being
        written. Returns it with `ended` set, or None if it isn't live."""
        talk = self._talks.get(conversation_id)
        if talk is None:
            return None
        if talk.writing is not None:
            talk.writing.cancel()
        self._end(talk)
        return talk.conversation.model_copy(deep=True)

    def cut(self, npc: Id, why: str) -> datetime | None:
        """Pull `npc` out of their conversation with another resident, for `why`: the player
        (`PLAYER`) or an urgent need. It ends after the line being said, with `npc`'s goodbye
        where one fits. Returns when they're done, or None if they weren't in one."""
        scene = next(
            (
                talk
                for talk in self._talks.values()
                if isinstance(talk, Scene) and npc in talk.conversation.participants
            ),
            None,
        )
        if scene is None:
            return None
        now, lines = self.clock.now, scene.conversation.lines
        if scene.closing:
            return max(now, scene.free_at)
        if scene.leaver is not None and scene.pending is not None:
            line = scene.pending[0]
            return line.timestamp + timedelta(seconds=line.duration)
        if scene.writing is not None:
            scene.writing.cancel()
        scene.streamed, scene.pending = True, None
        scene.script.clear()
        if not lines:
            self._end(scene)
            return now
        scene.leaver = npc
        self._log("%s left %s (%s)", npc, scene.conversation.id, why)
        goodbye = self._goodbye(scene, npc, why)
        if goodbye is None:
            self._close(scene)
            return max(now, scene.free_at)
        line = self._line(scene, npc, goodbye)
        scene.pending = (line, ())
        self.bus.publish(LineDrafted(line))
        return line.timestamp + timedelta(seconds=line.duration)

    async def close(self) -> None:
        """Stop writing lines. Conversations still going on are left as they are."""
        tasks = [talk.writing for talk in self._talks.values() if talk.writing]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def _play(self, scene: Scene) -> None:
        now = self.clock.now
        if scene.closing:
            if now >= scene.free_at:
                self._end(scene)
            return
        if scene.writing is not None and scene.writing.done():
            self._written(scene)
        if scene.writing is None and not scene.streamed:
            scene.writing = asyncio.get_running_loop().create_task(self._write(scene))
        self._check_needs(scene)
        if scene.conversation.ended:
            return
        if scene.pending is None and scene.script:
            self._draft(scene)
        due = scene.pending is not None and now >= scene.pending[0].timestamp
        if due and self._speak(scene) and scene.script:
            self._draft(scene)
        if scene.pending is None and not scene.script and scene.streamed:
            if scene.conversation.lines:
                self._close(scene)
            else:
                logger.warning("%s never started", scene.conversation.id)
                self._end(scene)

    async def _write(self, scene: Scene) -> None:
        config = self.config
        spellings = {npc: [scene.names[npc], p.npc.name] for npc, p in scene.parties.items()}
        parser = ScriptParser(spellings, config)
        scene.asked = len(scene.written)
        prompt = scene.prompt
        if scene.written:
            prompt = continue_prompt(scene.prompt, scene.written, scene.names)
        stream = self.llm().stream(
            prompt,
            system=script_system(config, humour=any(p.npc.humour for p in scene.parties.values())),
            model=config.model,
            purpose="conversation",
        )
        loop = asyncio.get_running_loop()
        first = config.first_line_timeout
        async with asyncio.timeout(first) as deadline, aclosing(stream) as chunks:
            async for chunk in chunks:
                if self._add(scene, parser.feed(chunk)):
                    deadline.reschedule(loop.time() + config.line_timeout)
                if len(scene.written) >= config.max_lines:
                    return
        self._add(scene, parser.end())

    def _add(self, scene: Scene, lines: list[ScriptLine]) -> bool:
        if scene.streamed:
            return False
        lines = lines[: self.config.max_lines - len(scene.written)]
        scene.script.extend(lines)
        scene.written.extend(lines)
        return bool(lines)

    def _written(self, scene: Scene) -> None:
        task, scene.writing = scene.writing, None
        assert task is not None
        if scene.streamed:
            return
        if task.cancelled():
            scene.streamed = True
        elif isinstance(task.exception(), TimeoutError) and not scene.written and not scene.retried:
            scene.retried = True
            logger.warning(
                "%s had no line within %gs, so asking again",
                scene.conversation.id,
                self.config.first_line_timeout,
            )
        elif error := task.exception():
            logger.warning("Couldn't write %s: %r", scene.conversation.id, error)
            scene.streamed = True
        elif self._unfinished(scene):
            scene.continued = True
            self._log("%s stopped short, so asking for the rest", scene.conversation.id)
        else:
            scene.streamed = True

    def _unfinished(self, scene: Scene) -> bool:
        """Whether a script that streamed to its end in its first call stopped well short of its
        planned length, without a goodbye."""
        written = scene.written
        if scene.continued or not written:
            return False
        if len(written) >= scene.plan.length * self.config.continue_below:
            return False
        return not any(takes_leave(line.draft.text) for line in written[-2:])

    def _check_needs(self, scene: Scene) -> None:
        if scene.leaver is not None:
            return
        urgent = {**dict.fromkeys(PRESSING, self.config.urgent_need), **self._critical()}
        for npc in scene.conversation.participants:
            needs = self.behaviour.needs(npc)
            for need, level in urgent.items():
                if needs[need] >= level > scene.needs[npc][need]:
                    self.cut(npc, need)
                    return

    def _draft(self, scene: Scene) -> None:
        written = scene.script.popleft()
        line = self._line(scene, written.speaker, written.draft.text)
        scene.pending = (line, written.draft.values)
        self.bus.publish(LineDrafted(line))

    def _line(self, scene: Scene, speaker: Id, text: str) -> Line:
        return Line(
            id=next(self.line_ids),
            conversation_id=scene.conversation.id,
            speaker=speaker,
            text=text,
            timestamp=max(self.clock.now, scene.free_at),
            duration=round(duration(text, self.config, speaking_rate(speaker)), 2),
        )

    def _speak(self, scene: Scene) -> bool:
        assert scene.pending is not None
        line, values = scene.pending
        if (ends := self.still_playing(scene.conversation)) is not None:
            free_at = ends + timedelta(seconds=self.config.turn_gap)
            if free_at > self.clock.now:
                scene.pending = (line.model_copy(update={"timestamp": free_at}), values)
                return False
        scene.pending = None
        line = self.as_voiced(line)
        scene.conversation.lines.append(line)
        self.bus.publish(LineSpoken(line))
        new = [value for value in values if value not in scene.touched]
        scene.touched.update(values)
        for npc, party in scene.parties.items():
            drain = scene.plan.stances[npc].drain
            party.engagement = engage(
                party.engagement, party.npc.values, party.like, new, self.config, drain=drain
            )
        ends = line.timestamp + timedelta(seconds=line.duration)
        scene.free_at = ends + timedelta(seconds=self.config.turn_gap)
        return True

    def _close(self, scene: Scene) -> None:
        last = scene.conversation.lines[-1]
        scene.closing = True
        scene.free_at = last.timestamp + timedelta(seconds=last.duration)

    def _goodbye(self, scene: Scene, npc: Id, why: str) -> str | None:
        last, name = scene.conversation.lines[-1], scene.names[scene.other(npc)]
        if takes_leave(last.text):
            return None if last.speaker == npc else self.rng.choice(FAREWELLS).format(name=name)
        return self.rng.choice(GOODBYES.get(why, GOODBYES[Need.CURIOSITY])).format(name=name)

    def as_voiced(self, line: Line) -> Line:
        """The line lasting as long as its audio, if that's all made."""
        played = self.audio.duration(line) if self.audio else None
        return line if played is None else line.model_copy(update={"duration": round(played, 2)})

    def still_playing(self, conversation: Conversation) -> datetime | None:
        """Until when the last line's audio plays, while it's playing or still being made, but no
        later than `voice_wait` past the line's end."""
        if not conversation.lines or self.audio is None:
            return None
        last, now = conversation.lines[-1], self.clock.now
        latest = last.timestamp + timedelta(seconds=last.duration + self.config.voice_wait)
        if now >= latest:
            return None
        remaining = self.audio.remaining(last)
        if remaining is None:
            return min(now + RECHECK, latest)
        return min(now + timedelta(seconds=remaining), latest) if remaining > 0 else None

    def _end(self, talk: Talk) -> None:
        now = self.clock.now
        conversation = talk.conversation
        conversation.ended = now
        del self._talks[conversation.id]
        self.finished.append(conversation)
        kept = {*self._talks, *(finished.id for finished in self.finished)}
        self._loans = {id: loan for id, loan in self._loans.items() if id in kept}
        self._lies = {id: lying for id, lying in self._lies.items() if id in kept}
        self._log(
            "%s ended after %d lines (engagement %s)",
            conversation.id,
            len(conversation.lines),
            ", ".join(f"{npc} {party.engagement:.2f}" for npc, party in talk.parties.items()),
        )
        self.bus.publish(ConversationEnded(conversation.model_copy(deep=True)))
        cooldown = now + timedelta(minutes=self.config.cooldown)
        for npc in conversation.participants:
            mind = self.behaviour.minds.get(npc)
            if mind is not None:
                mind.cooldowns[talk.other(npc)] = cooldown
            if not self.talking(npc):
                self.behaviour.resume(npc)

    def _party(self, npc: Id, other: Id, direction: Direction) -> Party:
        """`npc`'s side of a conversation with `other`, written a line at a time."""
        now = self.clock.now
        speaker, them = self.behaviour.npcs[npc], self._person(other)
        rel = self._relationship(npc, other)
        topics = self._topics(npc, now)
        works = self._works(npc, other, now)
        location = self.behaviour.places.at(self.behaviour.movement.position(npc))
        return Party(
            npc=speaker,
            like=rel.like,
            engagement=initial_engagement(speaker.values, rel.like, self.config),
            facing=direction,
            system=system_prompt(speaker, self.config),
            background=background(
                speaker,
                them,
                rel,
                self.memory.shared_history(npc, other, now, k=self.config.history),
                self._memories(npc, other, now, [*topics, *noted(works)]),
                topics,
                location.name if location else None,
                now,
                self._plans(npc),
            ),
            works=works,
            topics=topics,
            temptations=self.tempted(npc, other),
        )

    def _plans(self, npc: Id, name: str | None = None) -> str:
        """What `npc` could plan to do and has said they will, told to them or, with `name`,
        about them."""
        parts = [can_do(self.behaviour.options(npc), name)]
        if intentions := self.behaviour.intentions(npc):
            parts.append(already(intentions, self.clock.now, self._name, name))
        return "\n\n".join(parts)

    def _critical(self) -> dict[Need, float]:
        return critical(self.behaviour.config.urgency)

    def _scene_lies(
        self,
        conversation_id: str,
        sides: dict[Id, Character],
        history: SharedHistory,
        loan: Loan | None,
    ) -> list[Lie]:
        """What each side is set up to lie about: what touches the other's notes or what's
        between them, on a lie roll. Nobody hides being short while asking for a loan."""
        lying = []
        for npc, other in itertools.permutations(sides):
            notes = brings_up(sides[other], history)
            borrowing = loan is not None and loan.borrower == npc
            for temptation in self.tempted(npc, other):
                if borrowing and temptation.kind in (Kind.SHORT, Kind.DEBT):
                    continue
                if touched(temptation, notes, other) and self.lies_about(
                    temptation, conversation_id
                ):
                    lying.append(self.tell(conversation_id, temptation, other))
        return lying

    def _loan(self, a: Id, b: Id, rels: dict[Id, Relationship]) -> Loan | None:
        purses = {}
        for npc in (a, b):
            money = self.behaviour.hooks.money(self.behaviour.npcs[npc])
            if not isinstance(money, int | float):
                return None
            purses[npc] = Purse(money, self.behaviour.savings(npc))
        since = self.clock.now - self.config.ask_again
        declined = [pair for pair, when in self._declined.items() if when > since]
        pending = list(self._loans.values())
        return arrange(purses, rels, self.config, declined=declined, pending=pending)

    def _person(self, id: Id) -> Npc | Player:
        return self.player if id == PLAYER_ID else self.behaviour.npcs[id]

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

    def _works(self, npc: Id, other: Id, now: datetime) -> list[WorkTopic]:
        """`npc`'s strongest unfaded work memories, those about `other` first."""
        config = self.config
        if not config.works:
            return []
        half_life = config.works_half_life
        found = [
            *self.memory.recall(
                npc, now, about=other, kind=MemoryKind.WORK, k=config.works, half_life=half_life
            ),
            *self.memory.recall(
                npc, now, kind=MemoryKind.WORK, k=config.works, half_life=half_life
            ),
        ]
        strong = [m for m in found if pull(m, now, half_life) >= config.works_min_score]
        return self._work_topics(strong)[: config.works]

    def _scene_works(self, a: Id, b: Id, now: datetime) -> dict[Id, list[WorkTopic]]:
        """Each side's works, and their making of any the other might bring up."""
        found = {a: self._works(a, b, now), b: self._works(b, a, now)}
        result = {}
        for npc, other in ((a, b), (b, a)):
            ids = {topic.work.id for topic in found[other] if topic.work.artist == npc}
            ids -= {topic.work.id for topic in found[npc]}
            made = []
            if ids:
                memories = self.memory.recall(npc, now, kind=MemoryKind.WORK, k=sys.maxsize)
                made = self._work_topics([memory for memory in memories if memory.work_id in ids])
            result[npc] = [*found[npc], *made]
        return result

    def _work_topics(self, memories: list[Memory]) -> list[WorkTopic]:
        """A topic for each memory of a work still stored, one for each work."""
        topics, seen = [], set()
        for memory in memories:
            work = self.work(memory.work_id) if memory.work_id else None
            if work is not None and work.id not in seen:
                seen.add(work.id)
                topics.append(WorkTopic(memory, work))
        return topics

    def _topic_values(
        self, npc: Npc, topics: list[Memory], works: list[WorkTopic]
    ) -> list[dict[CoreValue, float]]:
        """What `npc`'s news and works are about, or else what they care about most."""
        found = []
        for memory in topics:
            item = self.article(memory.news_id) if memory.news_id else None
            if item is not None and item.values:
                found.append(dict(item.values))
        found += [dict(topic.work.values) for topic in works]
        if found:
            return found
        ranked = sorted(npc.values, key=lambda value: -npc.values[value])
        return [dict.fromkeys(ranked[:3], 1.0)]

    def _secrets(self, npc: Id, other: Id) -> list[tuple[str, str]]:
        """What people besides `other` told `npc` in confidence."""
        found = []
        for rel in self.memory.relationships(npc):
            if rel.about == other:
                continue
            for flag in rel.flags:
                if flag.kind is FlagKind.SECRET and flag.resolved is None:
                    found.append((self._name(rel.about), flag.description))
        return found

    def _name(self, id: Id) -> str:
        known = id == PLAYER_ID or id in self.behaviour.npcs
        return first_name(self._person(id)) if known else id

    def _log(self, message: str, *args: object) -> None:
        logger.info(f"%s  {message}", self.clock, *args)

    def _talk_of(self, npc: Id) -> Talk | None:
        return next(
            (
                talk
                for talk in reversed(self._talks.values())
                if npc in talk.conversation.participants
            ),
            None,
        )


def pull(memory: Memory, now: datetime, half_life: timedelta) -> float:
    """Salience × recency."""
    age = (now - memory.timestamp).total_seconds()
    return memory.salience * recency(age, half_life.total_seconds())


def brings_up(side: Character, history: SharedHistory) -> str:
    """What one side of a scene might bring up, and what's between the two: their memories and
    their topics, news, works and secrets."""
    said = [memory.content for memory in [*side.memories, *side.topics]]
    said += [topic for memory in side.memories for topic in memory.topics]
    said += [topic.memory.content for topic in side.works]
    said += [what for _, what in side.secrets]
    said += [event.action for event in history.events]
    said += [flag.description for flag in history.flags]
    return "\n".join(said)


def felt(mood: tuple[str, ...]) -> str:
    return f" ({', '.join(mood)})" if mood else ""


def noted(works: list[WorkTopic]) -> list[Memory]:
    return [topic.memory for topic in works]


def facing(here: Point, there: Point) -> Direction:
    """Which way to turn to face them: left or right, unless they're straight above or below, and
    then towards the camera."""
    dx = there.x - here.x
    if dx == 0:
        return "down"
    return "right" if dx > 0 else "left"


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
