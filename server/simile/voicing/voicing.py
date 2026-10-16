import asyncio
import logging
import math
from collections import deque
from collections.abc import Callable, Coroutine, Iterable
from contextlib import aclosing
from dataclasses import dataclass, field

from simile.conversation import LineDrafted
from simile.protocol import SAMPLE_RATE, AudioChunk
from simile.schema import PLAYER_ID, Id, Line, Npc
from simile.sim import ConversationEnded, ConversationStarted, LineSpoken
from simile.voice import Priority, VoiceService
from simile.voicing.config import DEFAULT_CONFIG, VoicingConfig

logger = logging.getLogger(__name__)

MIN_LEAD = 0.01
"""C3 counts a chunk arriving closer than this to the end of the audio before it as a gap."""


@dataclass(eq=False)
class ConversationAudio:
    participants: tuple[Id, ...]
    near: bool = False
    ended: bool = False
    drafted: dict[int, Line] = field(default_factory=dict)
    """Lines written and waiting for their turn, by id."""
    lines: dict[int, "LineAudio"] = field(default_factory=dict)
    durations: dict[int, float] = field(default_factory=dict)
    """How long each line's audio plays for, by id, once it's all made."""
    ends: float = 0.0
    """When the client finishes playing the audio sent so far, in event loop time."""

    @property
    def priority(self) -> Priority:
        return Priority.PLAYER if PLAYER_ID in self.participants else Priority.OVERHEARD


@dataclass(eq=False)
class LineAudio:
    line: Line
    conversation: ConversationAudio
    priority: Priority
    chunks: deque[bytes] = field(default_factory=deque)
    generated: bool = False
    failed: bool = False
    spoken: asyncio.Event = field(default_factory=asyncio.Event)
    finished: asyncio.Event = field(default_factory=asyncio.Event)
    more: asyncio.Event = field(default_factory=asyncio.Event)
    sequence: int = 0
    ends: float = 0.0
    closed: bool = False
    generating: asyncio.Task[None] | None = None
    sending: asyncio.Task[None] | None = None


class Voicing:
    """Voices the conversations within the player's earshot. Tick it on the sim loop."""

    def __init__(
        self,
        voice: VoiceService,
        distance: Callable[[Id, Id], float],
        send: Callable[[AudioChunk], None],
        *,
        listening: Callable[[], bool] = lambda: True,
        config: VoicingConfig = DEFAULT_CONFIG,
    ) -> None:
        self.voice = voice
        self.distance = distance
        self.send = send
        self.listening = listening
        self.config = config
        self._conversations: dict[str, ConversationAudio] = {}
        self._lines: dict[int, LineAudio] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def voiced(self, line: Line) -> bool:
        """Whether `audio_chunk`s will follow the line's `line` message. Asked as it's spoken."""
        audio = self._lines.get(line.id)
        return audio is not None and not audio.failed

    def duration(self, line: Line) -> float | None:
        """How long the line's audio plays for on the client, its jitter buffer included. None
        until all of it is made, and for a line that isn't voiced or was cut short."""
        conversation = self._conversations.get(line.conversation_id)
        return None if conversation is None else conversation.durations.get(line.id)

    def on_started(self, event: ConversationStarted) -> None:
        conversation = event.conversation
        audio = ConversationAudio(tuple(conversation.participants))
        self._conversations[conversation.id] = audio
        self._listen(audio)

    def on_drafted(self, event: LineDrafted) -> None:
        conversation = self._conversations.get(event.line.conversation_id)
        if conversation is None or conversation.ended:
            return
        conversation.drafted[event.line.id] = event.line
        self._listen(conversation)

    def on_spoken(self, event: LineSpoken) -> None:
        line = event.line
        conversation = self._conversations.get(line.conversation_id)
        if conversation is None:
            return
        for id in [id for id in conversation.drafted if id <= line.id]:
            del conversation.drafted[id]
        interrupted = line.speaker == PLAYER_ID
        for audio in tuple(conversation.lines.values()):
            if audio.line.id == line.id and not audio.failed:
                audio.spoken.set()
            elif interrupted or (audio.line.id <= line.id and not audio.spoken.is_set()):
                self._stop(audio)

    def on_ended(self, event: ConversationEnded) -> None:
        conversation = self._conversations.get(event.conversation.id)
        if conversation is None:
            return
        conversation.ended = True
        conversation.drafted.clear()
        for audio in tuple(conversation.lines.values()):
            if not audio.spoken.is_set():
                self._stop(audio)

    def tick(self, dt: float) -> None:
        for id, conversation in tuple(self._conversations.items()):
            if conversation.ended and not conversation.lines:
                del self._conversations[id]
            else:
                self._listen(conversation)

    async def close(self) -> None:
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def _listen(self, conversation: ConversationAudio) -> None:
        near = self._near(conversation)
        if near and not conversation.near:
            if conversation.priority is Priority.PLAYER:
                self._make_room_for_player()
            else:
                near = len(self._voiced()) < self.config.max_voiced
        if near:
            conversation.near = True
            for line in conversation.drafted.values():
                if line.id not in conversation.lines:
                    self._start(conversation, line)
        elif conversation.near:
            self._silence(conversation)

    def _near(self, conversation: ConversationAudio) -> bool:
        if not self.listening():
            return False
        reach = self.config.out_of_earshot if conversation.near else self.config.earshot
        return any(self._from_player(npc) <= reach for npc in conversation.participants)

    def _voiced(self) -> list[ConversationAudio]:
        return [c for c in self._conversations.values() if c.near and not c.ended]

    def _make_room_for_player(self) -> None:
        voiced = self._voiced()
        overheard = sorted(
            (c for c in voiced if c.priority is Priority.OVERHEARD), key=self._closest
        )
        while overheard and len(voiced) >= self.config.max_voiced:
            voiced.remove(farthest := overheard.pop())
            self._silence(farthest)

    def _closest(self, conversation: ConversationAudio) -> float:
        return min(self._from_player(npc) for npc in conversation.participants)

    def _silence(self, conversation: ConversationAudio) -> None:
        for audio in tuple(conversation.lines.values()):
            self._stop(audio)
        conversation.near = False

    def _from_player(self, npc: Id) -> float:
        if npc == PLAYER_ID:
            return math.inf
        try:
            return self.distance(npc, PLAYER_ID)
        except KeyError:
            return math.inf

    def _start(self, conversation: ConversationAudio, line: Line) -> None:
        if line.speaker == PLAYER_ID or not self.voice.has_voice(line.speaker):
            return
        audio = LineAudio(line, conversation, conversation.priority)
        earlier = [other.finished for other in conversation.lines.values()]
        conversation.lines[line.id] = self._lines[line.id] = audio
        audio.generating = self._spawn(self._generate(audio))
        audio.sending = self._spawn(self._send(audio, earlier))
        audio.sending.add_done_callback(lambda _: self._finish(audio))
        if audio.priority is Priority.PLAYER:
            self._make_room()

    def _make_room(self) -> None:
        """V1 finishes the sentence it's on first, so overheard ones start again or stop."""
        for audio in tuple(self._lines.values()):
            if audio.priority is Priority.OVERHEARD and not audio.generated:
                if audio.sequence:
                    self._stop(audio)
                else:
                    self._regenerate(audio)

    def _regenerate(self, audio: LineAudio) -> None:
        if audio.generating is not None:
            audio.generating.cancel()
        audio.chunks.clear()
        audio.generating = self._spawn(self._generate(audio))

    async def _generate(self, audio: LineAudio) -> None:
        line = audio.line
        samples = 0
        try:
            speech = self.voice.speak(line.speaker, line.text, audio.priority)
            async with aclosing(speech) as chunks:
                async for pcm in chunks:
                    audio.chunks.append(pcm)
                    samples += len(pcm) // 2
                    audio.more.set()
        except Exception as error:
            logger.warning("Couldn't voice %s's line %d: %r", line.speaker, line.id, error)
            audio.failed = True
        else:
            if self._lines.get(line.id) is audio:
                seconds = self.config.jitter_buffer + samples / SAMPLE_RATE
                audio.conversation.durations[line.id] = seconds
        audio.generated = True
        audio.more.set()

    async def _send(self, audio: LineAudio, earlier: Iterable[asyncio.Event]) -> None:
        await audio.spoken.wait()
        for finished in earlier:
            await finished.wait()
        await self._until(audio.conversation.ends)
        while True:
            while not audio.chunks and not audio.generated:
                audio.more.clear()
                await audio.more.wait()
            if not audio.chunks:
                break
            self._emit(audio, audio.chunks.popleft())
            await self._until(audio.ends - self.config.lead)
        self._emit(audio, b"", last=True)

    def _emit(self, audio: LineAudio, pcm: bytes, *, last: bool = False) -> None:
        if pcm:
            now = asyncio.get_running_loop().time()
            gap = audio.ends < now + MIN_LEAD
            start = now + self.config.jitter_buffer if gap else audio.ends
            audio.ends = start + len(pcm) / 2 / SAMPLE_RATE
            audio.conversation.ends = max(audio.conversation.ends, audio.ends)
        self.send(AudioChunk(audio.line.id, audio.sequence, pcm, last))
        audio.sequence += 1
        audio.closed = last

    def _stop(self, audio: LineAudio) -> None:
        audio.conversation.durations.pop(audio.line.id, None)
        self._forget(audio)
        if audio.sending is not None:
            audio.sending.cancel()

    def _finish(self, audio: LineAudio) -> None:
        self._forget(audio)
        if audio.generating is not None:
            audio.generating.cancel()
        if audio.spoken.is_set() and not audio.closed:
            self._emit(audio, b"", last=True)
        audio.finished.set()

    def _forget(self, audio: LineAudio) -> None:
        audio.conversation.lines.pop(audio.line.id, None)
        self._lines.pop(audio.line.id, None)

    def _spawn(self, coroutine: Coroutine[None, None, None]) -> asyncio.Task[None]:
        task = asyncio.get_running_loop().create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _until(self, when: float) -> None:
        delay = when - asyncio.get_running_loop().time()
        if delay > 0:
            await asyncio.sleep(delay)


async def add_voices(voice: VoiceService, npcs: Iterable[Npc]) -> None:
    added = 0
    for npc in npcs:
        if npc.voice.reference_clip is None:
            continue
        try:
            await voice.add_voice(npc.id, npc.voice)
            added += 1
        except Exception:
            logger.exception("Couldn't load %s's voice", npc.id)
    logger.info("Loaded %d NPC voices", added)
