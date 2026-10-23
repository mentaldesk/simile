import asyncio
import logging
import re
from collections import deque
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import datetime, timedelta
from enum import StrEnum

from simile.clinic.clinic import Clinic
from simile.clinic.config import DEFAULT_CONFIG, ClinicConfig, Offer
from simile.conversation import duration, parse_reply
from simile.llm import LLMClient, LLMError
from simile.schema import LEGS, PLAYER_ID, SOLD, Bionic, Conversation, CoreValue, Id, Line, Npc
from simile.sim import Clock, ConversationEnded, ConversationStarted, EventBus, LineSpoken
from simile.social.bionics import LOOKS

logger = logging.getLogger(__name__)

PLAYER_NAME = "Visitor"
SENTENCE = re.compile(r"(?<=[.!?…])\s+(?=[A-Z\"“])")
REPLACES: dict[Bionic, str] = {
    **dict.fromkeys(LEGS, "their own legs"),
    Bionic.DATAJACK: "a vertebra",
    Bionic.INFRARED_EYE: "one of their eyes",
}


class Cue(StrEnum):
    GREET = "They've just walked into your clinic. Greet them, in a sentence or two."
    REPLY = f"Reply to {PLAYER_NAME}."


class DoctorTalk:
    """The player talking with the doctor, written through L1. Tick it on the sim loop."""

    def __init__(
        self,
        doctor: Npc,
        clinic: Clinic,
        clock: Clock,
        bus: EventBus,
        llm: Callable[[], LLMClient | None],
        line_ids: Iterator[int],
        salvage: Mapping[Id, float],
        config: ClinicConfig = DEFAULT_CONFIG,
    ) -> None:
        self.doctor = doctor
        self.clinic = clinic
        self.clock = clock
        self.bus = bus
        self.llm = llm
        self.line_ids = line_ids
        self.config = config
        self.system = system_prompt(doctor, salvage, config)
        self.conversation: Conversation | None = None
        self.queued: deque[str] = deque()
        self.writing: asyncio.Task[None] | None = None
        self.free_at = clock.now
        self.heard = clock.now
        self.greeted: datetime | None = None
        self.was_inside = False

    def say(self, text: str, target: Id) -> bool:
        """`player_say` to the doctor, while the player is in the clinic."""
        text = " ".join(text.split())
        if target != self.doctor.id or not text or not self.clinic.inside():
            return False
        if self.conversation is None:
            self._start(PLAYER_ID)
        self._interrupt()
        self._speak(PLAYER_ID, text)
        self._write(Cue.REPLY)
        return True

    def tick(self, dt: float) -> None:
        now, inside = self.clock.now, self.clinic.inside()
        if self.conversation is not None:
            if not inside:
                self._end()
            elif self.queued and now >= self.free_at:
                self._speak(self.doctor.id, self.queued.popleft())
            elif not self.queued and self.writing is None and self._silent(now):
                self._end()
        elif inside and not self.was_inside and (llm := self.llm()) is not None:
            llm.warm(system=self.system, model=self.config.model)
            if self._due(now):
                self.greeted = now
                self._start(self.doctor.id)
                self._write(Cue.GREET)
        self.was_inside = inside

    def live(self) -> list[Conversation]:
        return [] if self.conversation is None else [self.conversation.model_copy(deep=True)]

    async def close(self) -> None:
        writing = self.writing
        self._interrupt()
        if writing is not None:
            await asyncio.gather(writing, return_exceptions=True)

    def _due(self, now: datetime) -> bool:
        return self.greeted is None or now - self.greeted >= timedelta(
            hours=self.config.greet_every
        )

    def _silent(self, now: datetime) -> bool:
        return now - self.heard >= timedelta(seconds=self.config.silence)

    def _start(self, opener: Id) -> None:
        now = self.clock.now
        participants = [opener, PLAYER_ID if opener == self.doctor.id else self.doctor.id]
        self.conversation = Conversation(
            id=f"{now:%Y%m%dT%H%M%S}-{'-'.join(participants)}",
            participants=participants,
            started=now,
        )
        self.free_at = self.heard = now
        self.bus.publish(ConversationStarted(self.conversation.model_copy(deep=True)))

    def _speak(self, speaker: Id, text: str) -> None:
        assert self.conversation is not None
        now = self.clock.now
        line = Line(
            id=next(self.line_ids),
            conversation_id=self.conversation.id,
            speaker=speaker,
            text=text,
            timestamp=now,
            duration=round(duration(text), 2),
        )
        self.conversation.lines.append(line)
        self.heard = now
        self.free_at = now + timedelta(seconds=line.duration + self.config.gap)
        self.bus.publish(LineSpoken(line))

    def _write(self, cue: Cue) -> None:
        assert self.conversation is not None
        lines = list(self.conversation.lines)
        task = asyncio.get_running_loop().create_task(self._reply(cue, lines))
        self.writing = task

    async def _reply(self, cue: Cue, lines: Sequence[Line]) -> None:
        conversation = self.conversation
        try:
            llm = self.llm()
            if llm is None:
                return
            prompt = turn_prompt(self.doctor, self.clinic, lines, cue)
            async with asyncio.timeout(self.config.timeout):
                text = await llm.complete(
                    prompt,
                    system=self.system,
                    model=self.config.model,
                    purpose="doctor",
                    priority=1,
                )
        except (LLMError, TimeoutError) as error:
            logger.warning("The doctor couldn't reply: %s", error)
            return
        finally:
            if self.writing is asyncio.current_task():
                self.writing = None
        if conversation is self.conversation:
            self.queued.extend(sentences(text, self.doctor.name))

    def _interrupt(self) -> None:
        if self.writing is not None:
            self.writing.cancel()
            self.writing = None
        self.queued.clear()

    def _end(self) -> None:
        self._interrupt()
        if self.conversation is None:
            return
        ended = self.conversation.model_copy(update={"ended": self.clock.now}, deep=True)
        self.conversation = None
        self.bus.publish(ConversationEnded(ended))


def sentences(text: str, name: str) -> list[str]:
    """The doctor's reply, cleaned, one sentence a line."""
    spoken = parse_reply(text, [name, name.split()[0]], [PLAYER_NAME]).text
    return [sentence for sentence in SENTENCE.split(spoken) if sentence.strip()]


def system_prompt(doctor: Npc, salvage: Mapping[Id, float], config: ClinicConfig) -> str:
    """Who the doctor is and the clinic's fixed prices, the same for every call."""
    ranked = sorted(doctor.values.items(), key=lambda item: item[1], reverse=True)
    most, least = _values(ranked[:3]), _values(ranked[-3:])
    habits = f"Your habits: {_listed(doctor.mannerisms)}." if doctor.mannerisms else ""
    fits = [
        f"- {offer.name}, {_money(offer.price)}, in place of {_in_place_of(bionic, offer, config)}:"
        f" they {offer.does}."
        for bionic, offer in config.offers.items()
    ]
    bought = ", ".join(f"{id.replace('_', ' ')} {_money(price)}" for id, price in salvage.items())
    return "\n".join(
        [
            f"You are {doctor.name}, {doctor.age}, a {doctor.occupation.lower()}. {doctor.persona}",
            doctor.backstory,
            f"How you talk: {doctor.speaking_style} {habits}".strip(),
            f"You care most about {most}, and least about {least}.",
            "",
            "You run a back-alley clinic in the depot office of the old metro, under the village. "
            "You aren't a villager and never go up there: you don't know the villagers or their "
            "business, and you don't gossip about anyone.",
            "",
            "Your prices are fixed and you say them as facts. You never haggle, discount, give "
            "credit or offer anything else:",
            f"- You buy a healthy kidney for {_money(config.kidney)}, one from each customer, "
            "never the last.",
            *fits,
            f"- You buy salvage: {bought}.",
            "Up in the village people notice bionics, and some think less of anyone who has them. "
            "The eye shows the most.",
            "You never take money or operate while talking: the customer does that at your "
            "counter, by pressing E.",
            "",
            f"The customer is {PLAYER_NAME}. Reply with only what you say aloud, in one to three "
            "short sentences, with no name label and no stage directions.",
        ]
    )


def _in_place_of(bionic: Bionic, offer: Offer, config: ClinicConfig) -> str:
    if not offer.after:
        return REPLACES[bionic]
    legs = " or ".join(config.offers[before].name.lower() for before in offer.after)
    brought = f", and only with an {offer.needs.name} they bring" if offer.needs else ""
    return f"their {legs}, which you take back{brought}"


def turn_prompt(doctor: Npc, clinic: Clinic, lines: Sequence[Line], cue: Cue) -> str:
    """What the doctor sees of the player and could do for them now, and what's been said."""
    first = doctor.name.split()[0]
    said = [f"{first if line.speaker == doctor.id else PLAYER_NAME}: {line.text}" for line in lines]
    return "\n".join(
        [
            f"What you can see of {PLAYER_NAME}: {_looks(clinic)}",
            f"What you'd do for them now: {_now(clinic)}",
            "",
            *(["The conversation so far:", *said, ""] if said else []),
            cue.value,
        ]
    )


def _looks(clinic: Clinic) -> str:
    body = clinic.player.body
    seen = [LOOKS[bionic] for bionic in body.bionics]
    if any(getattr(body, kidney) == SOLD for kidney in ("left_kidney", "right_kidney")):
        seen.append("the scar where you took a kidney")
    return f"{_listed(seen)}." if seen else "a whole, ordinary body, nothing fitted."


def _now(clinic: Clinic) -> str:
    deals = [f"buy a kidney for {_money(price)}" for price in clinic.parts().values()]
    deals += [f"fit {f.name.lower()} for {_money(f.price)}" for f in clinic.fittings()]
    return f"{_listed(deals)}." if deals else "nothing more: they've everything you stock."


def _values(pairs: Sequence[tuple[CoreValue, float]]) -> str:
    return _listed([value.replace("_", " ") for value, _ in pairs])


def _money(amount: float) -> str:
    return f"{amount:g}"


def _listed(parts: Sequence[str]) -> str:
    return parts[0] if len(parts) < 2 else f"{', '.join(parts[:-1])} and {parts[-1]}"
