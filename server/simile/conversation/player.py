import asyncio
import logging
import random
import re
from collections import deque
from collections.abc import Callable, Iterator, Sequence
from contextlib import aclosing
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import takewhile

from pydantic import BaseModel, ConfigDict, Field

from simile.behaviour import Activity, Need
from simile.conversation.engagement import acceptance, accepts, engage, leaving
from simile.conversation.engine import PLAYER, ConversationEngine, Talk, facing
from simile.conversation.events import Direction, Facing, LineDrafted
from simile.conversation.prompt import (
    Cue,
    Draft,
    WorkTopic,
    duration,
    first_name,
    parse_reply,
    system_prompt,
    turn_prompt,
)
from simile.llm import Model
from simile.news.interest import shared, words
from simile.news.reactions import mentioned
from simile.schema import PLAYER_ID, Conversation, CoreValue, Id, Line, Memory, NewsItem
from simile.sim import ConversationStarted, LineSpoken
from simile.voice import speaking_rate

logger = logging.getLogger(__name__)

SENTENCE_END = re.compile(r"[.!?…]+[\"'”’)\]*]*(?=\s)")
CLAUSE_END = re.compile(
    r"\s*(?<!\d)(?<!\d\s)(?:[—–]|--|(?<=\s)-(?=\s))(?!\s?\d)|;(?=\s)|(?P<comma>,)(?=\s)"
)
CLAUSE_WORDS = 6
COMMA_CLAUSE_WORDS = 10
FOLLOWING_WORDS = 4
ABBREVIATION = re.compile(r"\b(?:mr|mrs|ms|dr|st|prof|vs|etc|e\.g|i\.e)\.$", re.IGNORECASE)
TAG = re.compile(r"\[\s*values?\s*:[^\]\n]*\]?|^\s*values?\s*:.*$", re.IGNORECASE | re.MULTILINE)
UNCLOSED = re.compile(r"\[[^\]\n]*$")

ANYWHERE = r"good-?\s?bye|bye|farewell|cya|ciao|cheerio"
AT_THE_END = (
    r"(?<!to )see (?:you|ya)|see (?:you|ya) (?:later|soon|around|tomorrow|then)|take care|"
    r"(?:was|been) (?:so )?(?:nice|good|great|lovely) to see (?:you|ya)|"
    r"catch you later|talk (?:to you )?(?:later|soon)|good\s?night|"
    r"(?:gotta|got to|have to|need to|must|should) (?:go|run|head off|get going)(?: now)?"
)
GOODBYE = re.compile(rf"\b(?:{ANYWHERE})\b|\b(?:{AT_THE_END})\W*$", re.IGNORECASE)

MURAL_WORD = r"(?:murals?|paint(?:s|ed|ing|ings)?|walls?)"
WORK_WORD = rf"(?:{MURAL_WORD}|poems?|verses?|pieces?|notices|writing|wrote|written)"
NOTICE = r"\b(?:the|a|your|my|her|his|their|that|this) notice\b"
A_WORK = re.compile(rf"\b{WORK_WORD}\b|{NOTICE}", re.IGNORECASE)
A_MURAL = re.compile(rf"\b{MURAL_WORD}\b", re.IGNORECASE)
MY_WORK = re.compile(rf"\bmy (?:{WORK_WORD}|notice)\b", re.IGNORECASE)
YOUR_WORK = re.compile(rf"\byour (?:{WORK_WORD}|notice)\b", re.IGNORECASE)
QUOTES_OPEN, QUOTES_CLOSE = "\"“‘'", "\"”’'"

TURNED_AWAY = (
    "I'll let you talk to {name}. See you around.",
    "Go on, {name}'s waiting. Catch you later.",
    "I'll leave you with {name}. Bye for now.",
    "Right, I'll let you go. See you!",
)


def says_goodbye(text: str) -> bool:
    return GOODBYE.search(text) is not None


def came_up(topic: WorkTopic, artist: str, lines: Sequence[Line]) -> bool:
    """Whether a line has brought the work up."""
    work = topic.work
    labels = [label for label in [*work.tags, *topic.memory.topics] if label.isalpha()]
    headline = words(" ".join([work.title, *labels]))
    wall = words(work.wall.replace("_", " ")) if work.wall else set()
    named = re.compile(rf"\b{re.escape(artist)}\b", re.IGNORECASE)
    own = work.artist == topic.memory.owner
    for line in lines:
        text = line.text
        a_work = A_WORK.search(text) is not None
        if line.speaker == work.artist:
            by = MY_WORK.search(text) is not None
        elif own:
            by = YOUR_WORK.search(text) is not None
        else:
            by = named.search(text) is not None
        on_wall = A_MURAL.search(text) is not None and bool(words(text) & wall)
        if on_wall or titled(work.title, text, loosely=a_work or by):
            return True
        if bool(shared(words(A_WORK.sub(" ", text)), headline)) + a_work + by >= 2:
            return True
    return False


def titled(title: str, text: str, *, loosely: bool) -> bool:
    """Whether `text` names `title` quoted, as written, or, if `loosely`, in any case."""
    title = title.strip().rstrip(".!?")
    if loosely and title.lower() in text.lower():
        return True
    quoted = rf"[{QUOTES_OPEN}]{re.escape(title)}[.,!?]?[{QUOTES_CLOSE}]"
    return re.search(quoted, text, re.IGNORECASE) is not None or (" " in title and title in text)


class PlayerConfig(BaseModel):
    """Every constant of player conversations. Distances are in tiles, times in sim seconds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str = Field(
        default=Model.HAIKU_4_5,
        description="The model that writes NPC replies to the player. Haiku 4.5 rather than "
        "Haiku 5.5, which can't turn thinking off and thinks for over a second before its first "
        "word.",
    )
    say_range: float = Field(
        default=4.0,
        gt=0,
        description="Furthest the player can be from an NPC to start talking to them. The chat box "
        "picks NPCs within 3.",
    )
    leave_range: float = Field(
        default=6.0,
        gt=0,
        description="Walking further than this from the NPC ends it. Until then the player's "
        "lines reach them.",
    )
    silence: float = Field(
        default=60, gt=0, description="How long the NPC waits for the player before leaving."
    )
    farewell_wait: float = Field(
        default=8,
        ge=0,
        description="How long after the NPC's goodbye the player's answer still joins it.",
    )
    look_every: float = Field(
        default=5, gt=0, description="Time between looks for NPCs near the player."
    )
    near: float = Field(
        default=3.0,
        ge=0,
        description="How near the player an NPC may greet them from. The nearest free NPC this "
        "near gets a Claude Code process started for their reply.",
    )
    greet_bar: float = Field(
        default=0.5,
        description="How far above zero B2's acceptance score must be for an NPC to greet the "
        "player unasked.",
    )
    greet_cooldown: float = Field(
        default=10, ge=0, description="Minutes before an NPC who didn't greet considers it again."
    )


DEFAULT_PLAYER_CONFIG = PlayerConfig()


@dataclass(kw_only=True)
class PlayerTalk(Talk):
    """A conversation with the player. `speaker` is the NPC while they reply, else the player."""

    speaker: Id
    cue: Cue = Cue.OPEN
    queued: deque[Line] = field(default_factory=deque)
    """Sentences written and waiting for their turn."""
    turns: int = 0
    said: int = 0
    """Sentences of the reply being written that have been published."""
    topics: tuple[CoreValue, ...] = ()
    ends: datetime | None = None
    quiet_until: datetime
    """The NPC's lines wait for the goodbye of the resident the player turned away from."""
    pulled_from: str | None = None
    """The conversation the NPC was pulled out of, whose end their lines wait for."""

    @property
    def npc(self) -> Id:
        return self.other(PLAYER_ID)

    def leaving(self, npc: Id) -> bool:
        return self.cue is Cue.GOODBYE and self.speaker == npc


class PlayerConversations:
    """The player talking with NPCs, hosted by B2's engine. Tick it on the sim loop."""

    def __init__(
        self,
        engine: ConversationEngine,
        *,
        connected: Callable[[], bool] = lambda: True,
        article: Callable[[str], NewsItem | None] = lambda _: None,
        config: PlayerConfig = DEFAULT_PLAYER_CONFIG,
        seed: int | None = None,
    ) -> None:
        self.engine = engine
        self.connected = connected
        self.article = article
        self.config = config
        self.rng = random.Random(seed)
        self._considered: dict[Id, datetime] = {}
        self._elapsed = 0.0

    def talk(self) -> PlayerTalk | None:
        talk = self.engine._talk_of(PLAYER_ID)
        return talk if isinstance(talk, PlayerTalk) else None

    def request(self, a: Id, b: Id) -> bool:
        """B1's `request_conversation` for an NPC who walked up to the player: they say hello."""
        if a == PLAYER_ID or not self._player_free() or not self._free(a):
            return False
        self.start(a, opener=a)
        return True

    def say(self, text: str, target: Id) -> Line | None:
        """`player_say`: the player says `text` to `target`, starting a conversation if needed."""
        text = " ".join(text.split())
        if not text or target not in self.engine.behaviour.npcs:
            logger.warning("Ignoring the player saying %r to %r", text, target)
            return None
        talk = self.talk()
        joined = talk if talk is not None and talk.npc == target else None
        reach = self.config.say_range if joined is None else self.config.leave_range
        distance = self._distance(target)
        if distance is None or distance > reach:
            self.engine._log("The player is too far from %s to talk (%s tiles)", target, distance)
            return None
        if joined is None:
            if not self._free(target, interrupting=True):
                self.engine._log("%s is busy, so the player gets no answer", target)
                return None
            left = self.engine._talk_of(target)
            goodbyes = [
                self._turned_away(talk, target) if talk is not None else None,
                self.engine.cut(target, PLAYER),
            ]
            joined = self._start(target, opener=PLAYER_ID)
            joined.quiet_until = max([joined.quiet_until, *filter(None, goodbyes)])
            if left is not None and left.conversation.id in self.engine._talks:
                joined.pulled_from = left.conversation.id
        return self._hear(joined, text)

    def start(self, npc: Id, *, opener: Id) -> Conversation:
        return self._start(npc, opener=opener).conversation

    def tick(self, dt: float) -> None:
        if talk := self.talk():
            self._advance(talk)
        self._elapsed += dt
        if self._elapsed >= self.config.look_every - 1e-9:
            self._elapsed = 0.0
            self._look_around()

    def _start(self, npc: Id, *, opener: Id) -> PlayerTalk:
        engine, now = self.engine, self.engine.clock.now
        direction = self._facing(npc)
        party = engine._party(npc, PLAYER_ID, direction)
        participants = [PLAYER_ID, npc] if opener == PLAYER_ID else [npc, PLAYER_ID]
        conversation = Conversation(
            id=self._conversation_id(participants, now), participants=participants, started=now
        )
        talk = PlayerTalk(
            conversation,
            {npc: party},
            speaker=opener,
            free_at=now,
            quiet_until=now,
            names={npc: first_name(party.npc), PLAYER_ID: engine.player.name},
        )
        engine._talks[conversation.id] = talk
        engine.behaviour.pause(npc, PLAYER_ID)
        engine.bus.publish(Facing(npc, PLAYER_ID, direction))
        engine.bus.publish(ConversationStarted(conversation.model_copy(deep=True)))
        engine._log("%s started %s", opener, conversation.id)
        if opener == npc:
            self._write(talk, Cue.OPEN)
        return talk

    def _hear(self, talk: PlayerTalk, text: str) -> Line:
        engine, now = self.engine, self.engine.clock.now
        self._interrupt(talk)
        line = Line(
            id=next(engine.line_ids),
            conversation_id=talk.conversation.id,
            speaker=PLAYER_ID,
            text=text,
            timestamp=now,
            duration=round(duration(text, engine.config), 2),
        )
        self._speak(talk, line)
        if talk.closing:
            self._end(talk)
            return line
        party = talk.parties[talk.npc]
        party.engagement = engage(
            party.engagement, party.npc.values, party.like, talk.topics, engine.config
        )
        talk.turns += 1
        if says_goodbye(text):
            self._write(talk, Cue.FAREWELL)
        elif leaving(party.engagement, talk.turns, engine.config):
            engine._log(
                "%s is leaving %s (engagement %.2f)",
                talk.npc,
                talk.conversation.id,
                party.engagement,
            )
            self._write(talk, Cue.GOODBYE)
        else:
            self._write(talk, Cue.REPLY)
        return line

    def _interrupt(self, talk: PlayerTalk) -> None:
        if talk.writing is not None:
            talk.writing.cancel()
            talk.writing = None
        talk.queued.clear()
        talk.free_at = max(min(talk.free_at, self.engine.clock.now), talk.quiet_until)

    def _write(self, talk: PlayerTalk, cue: Cue) -> None:
        talk.cue, talk.speaker, talk.said = cue, talk.npc, 0
        lines = list(talk.conversation.lines)
        talk.writing = asyncio.get_running_loop().create_task(self._reply(talk, cue, lines))

    async def _reply(self, talk: PlayerTalk, cue: Cue, lines: Sequence[Line]) -> Draft:
        engine, npc = self.engine, talk.npc
        party = talk.parties[npc]
        prompt = turn_prompt(
            party.background,
            lines,
            talk.names,
            cue,
            engine.player.name,
            engine.config,
            speaker=npc,
            recalled=self._recalled(npc, lines),
            works=self._works(talk, lines),
        )
        stream = engine.llm().stream(
            prompt,
            system=party.system,
            model=self.config.model,
            purpose="player-reply",
            priority=1,
        )
        sentences = Sentences([talk.names[npc], party.npc.name], [engine.player.name])
        async with asyncio.timeout(engine.config.line_timeout), aclosing(stream) as chunks:
            async for chunk in chunks:
                for sentence in sentences.feed(chunk):
                    self._sentence(talk, sentence)
        for sentence in sentences.end():
            self._sentence(talk, sentence)
        return sentences.draft

    def _works(self, talk: PlayerTalk, lines: Sequence[Line]) -> list[WorkTopic]:
        """The NPC's works that haven't come up before their last reply."""
        npc = talk.npc
        last = max((n for n, line in enumerate(lines) if line.speaker == npc), default=-1)
        return [
            topic
            for topic in talk.parties[npc].works
            if not came_up(topic, self.engine._name(topic.work.artist), lines[: last + 1])
        ]

    def _recalled(self, npc: Id, lines: Sequence[Line]) -> list[Memory]:
        """What `npc` read about the articles the player has mentioned since `npc` last spoke."""
        latest = takewhile(lambda line: line.speaker != npc, reversed(lines))
        said = " ".join(line.text for line in latest)
        if not said:
            return []
        try:
            return mentioned(
                self.engine.memory, npc, said, self.engine.clock.now, article=self.article
            )
        except Exception:
            logger.exception("Couldn't recall the news %s read", npc)
            return []

    def _sentence(self, talk: PlayerTalk, text: str, *, at_once: bool = False) -> None:
        engine, now = self.engine, self.engine.clock.now
        starts = max(now, talk.free_at)
        if not at_once and (ends := engine.still_playing(talk.conversation)) is not None:
            starts = max(starts, ends)
        line = Line(
            id=next(engine.line_ids),
            conversation_id=talk.conversation.id,
            speaker=talk.npc,
            text=text,
            timestamp=starts,
            duration=round(duration(text, engine.config, speaking_rate(talk.npc)), 2),
        )
        talk.free_at = line.timestamp + timedelta(seconds=line.duration)
        talk.said += 1
        engine.bus.publish(LineDrafted(line))
        if line.timestamp <= now and not self._pulled_away(talk):
            self._speak(talk, line)
        else:
            talk.queued.append(line)

    def _speak(self, talk: PlayerTalk, line: Line) -> None:
        line = self.engine.as_voiced(line)
        talk.conversation.lines.append(line)
        self.engine.bus.publish(LineSpoken(line))
        if line.speaker != PLAYER_ID:
            self._follow(talk, line.timestamp + timedelta(seconds=line.duration))

    def _follow(self, talk: PlayerTalk, ends: datetime) -> None:
        """Moves the queued sentences to follow each other from `ends`."""
        for n, line in enumerate(talk.queued):
            talk.queued[n] = line.model_copy(update={"timestamp": ends})
            ends += timedelta(seconds=line.duration)
        talk.free_at = ends

    def _advance(self, talk: PlayerTalk) -> None:
        now = self.engine.clock.now
        distance = self._distance(talk.npc)
        if not self.connected() or distance is None or distance > self.config.leave_range:
            self.engine._log("The player left %s", talk.conversation.id)
            self._end(talk)
            return
        while talk.queued and talk.queued[0].timestamp <= now and not self._pulled_away(talk):
            ends = self.engine.still_playing(talk.conversation)
            if ends is not None and ends > now:
                self._follow(talk, ends)
            else:
                self._speak(talk, talk.queued.popleft())
        if talk.writing is not None and talk.writing.done():
            task, talk.writing = talk.writing, None
            self._replied(talk, task)
        if talk.writing is not None or talk.queued:
            return
        if talk.closing:
            if talk.ends is None or now >= talk.ends:
                self._end(talk)
        elif talk.speaker == PLAYER_ID and now >= talk.free_at + timedelta(
            seconds=self.config.silence
        ):
            self.engine._log("%s gave up waiting in %s", talk.npc, talk.conversation.id)
            if any(line.speaker == PLAYER_ID for line in talk.conversation.lines):
                self._write(talk, Cue.GOODBYE)
            else:
                self._end(talk)

    def _replied(self, talk: PlayerTalk, task: asyncio.Task[Draft]) -> None:
        engine = self.engine
        error = None if task.cancelled() else task.exception()
        if error:
            logger.warning(
                "Couldn't write %s's reply in %s: %r", talk.npc, talk.conversation.id, error
            )
        if not talk.said:
            logger.warning("%s said nothing in %s, so it ends", talk.npc, talk.conversation.id)
            talk.closing, talk.ends = True, talk.free_at
            return
        party = talk.parties[talk.npc]
        if not task.cancelled() and not error:
            talk.topics = task.result().values
        party.engagement = engage(
            party.engagement, party.npc.values, party.like, talk.topics, engine.config
        )
        talk.turns += 1
        if talk.cue in (Cue.GOODBYE, Cue.FAREWELL):
            wait = self.config.farewell_wait if talk.cue is Cue.GOODBYE else 0
            talk.closing, talk.ends = True, talk.free_at + timedelta(seconds=wait)
        else:
            talk.speaker = PLAYER_ID
            engine.llm().warm(system=party.system, model=self.config.model)

    def _pulled_away(self, talk: PlayerTalk) -> bool:
        """Whether the NPC is still saying goodbye in the conversation they were pulled out of,
        or its audio is still playing. Once they're done, their sentences follow."""
        engine, now = self.engine, self.engine.clock.now
        if talk.pulled_from is None:
            return False
        if talk.pulled_from in engine._talks:
            return True
        left = engine.conversation(talk.pulled_from)
        if left is not None and (ends := engine.still_playing(left)) is not None and ends > now:
            return True
        talk.pulled_from = None
        if talk.queued and talk.queued[0].timestamp < now:
            self._follow(talk, now)
        return False

    def _end(self, talk: PlayerTalk) -> None:
        self._interrupt(talk)
        self.engine._end(talk)

    def _turned_away(self, talk: PlayerTalk, to: Id) -> datetime:
        """A quick goodbye, unless they said one or haven't spoken yet. Returns when they finish."""
        if not talk.closing:
            self._interrupt(talk)
            if talk.quiet_until <= self.engine.clock.now:
                name = first_name(self.engine.behaviour.npcs[to])
                goodbye = self.rng.choice(TURNED_AWAY).format(name=name)
                self._sentence(talk, goodbye, at_once=True)
        ends = talk.queued[0].timestamp if talk.queued else talk.free_at
        self._end(talk)
        return ends

    def _look_around(self) -> None:
        engine, now = self.engine, self.engine.clock.now
        if not self._player_free():
            return
        nearby = sorted(
            (distance, npc)
            for npc in engine.behaviour.npcs
            if (distance := self._distance(npc)) is not None
            and distance <= self.config.near
            and self._free(npc)
        )
        for _, npc in nearby:
            if self._greets(npc, now):
                self.start(npc, opener=npc)
                return
        if nearby:
            npc = engine.behaviour.npcs[nearby[0][1]]
            engine.llm().warm(system=system_prompt(npc, engine.config), model=self.config.model)

    def _greets(self, npc: Id, now: datetime) -> bool:
        engine, behaviour = self.engine, self.engine.behaviour
        mind = behaviour.minds[npc]
        if npc in behaviour.leave_player_alone:
            return False
        if behaviour.at_home(npc):
            return False
        if max(self._considered.get(npc, now), mind.cooldowns.get(PLAYER_ID, now)) > now:
            return False
        self._considered[npc] = now + timedelta(minutes=self.config.greet_cooldown)
        score = acceptance(
            mind.npc.values,
            engine._relationship(npc, PLAYER_ID),
            mind.goal,
            mind.needs[Need.SOCIAL],
            engine.config,
        )
        greets = accepts(score - self.config.greet_bar, self.rng, engine.config)
        engine._log("%s %s the player (score %.2f)", npc, "greets" if greets else "ignores", score)
        return greets

    def _player_free(self) -> bool:
        return self.connected() and self._distance_known() and not self.engine.talking(PLAYER_ID)

    def _free(self, npc: Id, *, interrupting: bool = False) -> bool:
        """Whether `npc` is awake and not talking, or when `interrupting`, talking only to
        another resident."""
        mind = self.engine.behaviour.minds.get(npc)
        if mind is None or (self.engine.talking(npc) and not interrupting):
            return False
        talk = self.engine._talk_of(npc)
        if talk is not None and PLAYER_ID in talk.conversation.participants:
            return False
        return not (mind.goal.activity is Activity.SLEEP and mind.walk is None)

    def _distance_known(self) -> bool:
        return PLAYER_ID in self.engine.behaviour.movement.entities()

    def _distance(self, npc: Id) -> float | None:
        try:
            return self.engine.behaviour.movement.distance(npc, PLAYER_ID)
        except KeyError:
            return None

    def _facing(self, npc: Id) -> Direction:
        movement = self.engine.behaviour.movement
        try:
            return facing(movement.position(npc), movement.position(PLAYER_ID))
        except KeyError:
            return "down"

    def _conversation_id(self, participants: Sequence[Id], now: datetime) -> str:
        base = id = f"{now:%Y%m%dT%H%M%S}-{'-'.join(participants)}"
        taken = {c.id for c in self.engine.finished} | set(self.engine._talks)
        n = 1
        while id in taken:
            n += 1
            id = f"{base}-{n}"
        return id


class Sentences:
    """A reply's sentences as they finish streaming, cleaned like `parse_reply`."""

    def __init__(self, names: Sequence[str] = (), others: Sequence[str] = ()) -> None:
        self.names = names
        self.others = others
        self.text = ""
        self.said = 0
        self._start = 0
        self._over = False

    def feed(self, chunk: str) -> list[str]:
        self.text += chunk
        return self._take(final=False)

    def end(self) -> list[str]:
        sentences = self._take(final=True)
        if not self.said:
            sentences = [s for s in split(self.draft.text) if s]
            self.said = len(sentences)
        return sentences

    @property
    def draft(self) -> Draft:
        return parse_reply(self.text, self.names, self.others)

    def _take(self, *, final: bool) -> list[str]:
        if self._over:
            return []
        speakable, over = self._speakable()
        pieces = []
        for end in _boundaries(speakable, self._start):
            pieces.append(speakable[self._start : end])
            self._start = end
        if not (pieces or self.said or over or final) and (end := self._first_clause(speakable)):
            pieces.append(speakable[self._start : end])
            self._start = end
        if over or final:
            pieces.append(speakable[self._start :])
            self._over = True
        sentences = [s for s in map(self._clean, pieces) if s]
        self.said += len(sentences)
        return sentences

    def _first_clause(self, speakable: str) -> int | None:
        """Where to cut a long first sentence so its voice can start sooner."""
        for match in CLAUSE_END.finditer(speakable, self._start):
            end, comma = match.end(), match["comma"] is not None
            if speakable.count("*", 0, end) % 2:
                continue
            words = self._clean(speakable[self._start : end]).split()
            if len(words) < (COMMA_CLAUSE_WORDS if comma else CLAUSE_WORDS):
                continue
            following = speakable[end:].split()
            if len(following) - (not speakable[-1].isspace()) < FOLLOWING_WORDS:
                return None
            near = words[-FOLLOWING_WORDS - 1 : -1] + following[:FOLLOWING_WORDS]
            if not (comma and any(word.endswith(",") for word in near)):
                return end
        return None

    def _speakable(self) -> tuple[str, bool]:
        """The text up to the values tag or the other person's turn, and whether either began."""
        text, cut, over = self.text, len(self.text), False
        ends = [m.start() for m in [TAG.search(text)] if m]
        ends += [
            m.start()
            for name in self.others
            if (m := re.search(rf"^\s*{re.escape(name)}\s*:", text, re.IGNORECASE | re.MULTILINE))
        ]
        if ends:
            cut, over = min(ends), True
        elif unclosed := UNCLOSED.search(text):
            cut = unclosed.start()
        return text[:cut], over

    def _clean(self, piece: str) -> str:
        text = parse_reply(piece, self.names, self.others).text
        if text.count('"') % 2 or text.count("“") != text.count("”"):
            text = text.strip('"“” ')
        return text


def split(text: str) -> list[str]:
    """`text` in sentences."""
    starts = [0, *_boundaries(text, 0)]
    return [text[a:b].strip() for a, b in zip(starts, [*starts[1:], len(text)], strict=True)]


def _boundaries(text: str, start: int) -> Iterator[int]:
    for match in SENTENCE_END.finditer(text, start):
        if text.count("*", 0, match.end()) % 2 or ABBREVIATION.search(text, 0, match.start() + 1):
            continue
        yield match.end()
