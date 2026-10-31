import asyncio
import logging
import re
from collections import deque
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import datetime, timedelta
from enum import StrEnum

from simile.clinic.clinic import Clinic
from simile.clinic.config import DEFAULT_CONFIG, ClinicConfig, Procedure
from simile.conversation import duration, parse_reply
from simile.llm import LLMClient, LLMError
from simile.schema import (
    PLAYER_ID,
    SOLD,
    Bionic,
    Body,
    Conversation,
    CoreValue,
    Id,
    Line,
    Npc,
)
from simile.sim import Clock, ConversationEnded, ConversationStarted, EventBus, LineSpoken
from simile.social.bionics import LOOKS

logger = logging.getLogger(__name__)

PLAYER_NAME = "Visitor"
SENTENCE = re.compile(r"(?<=[.!?…])\s+(?=[A-Z\"“])")
REPLACES: dict[str, str] = {
    "legs": "their own legs",
    "vertebra": "a vertebra",
    "left_eye": "one of their eyes",
    "right_eye": "one of their eyes",
    "stomach": "their stomach",
    "feet": "their own feet",
}
HINTS = 2
"""The most bionics they don't know the recipe for that the doctor might hint at."""


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
    cell = config.procedures[Bionic.POWER_CELL].recipe.name.lower()
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
            f"- You buy salvage: {bought}.",
            "- You build bionics from a recipe the customer knows: they pay your fee "
            "and bring the parts it lists, which the fitting uses up. Without the recipe you "
            f"can't build it. Nothing you build runs without a {cell} in place of the stomach, "
            "so the cell goes in first.",
            "- You buy each recipe a customer knows once, at your price, and they still know it.",
            f"- You patch up the hurt, for up to {_money(config.patch_up)} by how hurt they are, "
            f"and you {_cures(config)}: a rat bite left untreated can turn infected.",
            "Up in the village people notice bionics, and some think less of anyone who has them. "
            "The eye shows the most.",
            "You never take money or operate while talking: the customer does that at your "
            "counter, by pressing E.",
            "",
            f"The customer is {PLAYER_NAME}. Reply with only what you say aloud, in one to three "
            "short sentences, with no name label and no stage directions.",
        ]
    )


def _cures(config: ClinicConfig) -> str:
    return _listed(
        [f"{cure.name.lower()} for {_money(cure.price)}" for cure in config.cures.values()]
    )


def turn_prompt(doctor: Npc, clinic: Clinic, lines: Sequence[Line], cue: Cue) -> str:
    """What the doctor sees of the player and could do for them now, and what's been said."""
    first = doctor.name.split()[0]
    said = [f"{first if line.speaker == doctor.id else PLAYER_NAME}: {line.text}" for line in lines]
    return "\n".join(
        [
            f"What you can see of {PLAYER_NAME}: {_looks(clinic)}",
            f"What you'd do for them now: {_now(clinic)}",
            *_waiting(clinic),
            *_hints(clinic),
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
    recipes = clinic.config.recipes
    deals = [f"buy a kidney for {_money(price)}" for price in clinic.parts().values()]
    deals += [
        _fitting(clinic, f.bionic, f.name, f.price) for f in clinic.fittings() if not f.blocked
    ]
    deals += [
        f"buy their recipe for the {recipes[bionic].name.lower()} for a one-off {_money(price)}"
        for bionic, price in clinic.recipes().items()
    ]
    deals += [f"{t.name.lower()} for {_money(t.price)}" for t in clinic.treatments()]
    return f"{_listed(deals)}." if deals else "nothing, until they know how to build something."


def _fitting(clinic: Clinic, bionic: Bionic, name: str, price: float) -> str:
    recipe = clinic.config.recipes.get(bionic)
    if recipe is None:
        return f"fit {name.lower()} for {_money(price)}"
    said = f"build the {name.lower()} for {_money(price)}, using up {_parts(recipe.parts)}"
    if missing := clinic.missing(bionic):
        said += f", though they're short of {_parts(missing)}"
    return said


def _waiting(clinic: Clinic) -> list[str]:
    """The recipes they know that the doctor can't fit yet, and why."""
    waiting: dict[str, list[str]] = {}
    for fitting in clinic.fittings():
        if fitting.blocked:
            waiting.setdefault(fitting.blocked, []).append(fitting.name.lower())
    return [
        f"They know how to build the {_listed(names)}, but you can't fit "
        f"{'it' if len(names) == 1 else 'them'} yet: {reason[0].lower()}{reason[1:]}"
        for reason, names in waiting.items()
    ]


def _hints(clinic: Clinic) -> list[str]:
    """A bionic or two they don't know the recipe for, for the doctor to hint at."""
    body, known = clinic.player.body, clinic.player.mind.recipes
    unknown = [
        procedure
        for bionic, procedure in clinic.config.procedures.items()
        if bionic not in known and not body.has(bionic) and _next_grade(body, bionic)
    ][:HINTS]
    if not unknown:
        return []
    hints = "; or ".join(_hint(procedure) for procedure in unknown)
    return [
        "If it suits the talk, you might hint at what else you could do for them, but never with "
        f"a price, a list or how to build it: {hints}."
    ]


def _next_grade(body: Body, bionic: Bionic) -> bool:
    line = bionic.line
    return all(body.has(lower) for lower in line[: line.index(bionic)])


def _hint(procedure: Procedure) -> str:
    recipe = procedure.recipe
    where = REPLACES[recipe.replaces[0]]
    return f"the {recipe.name.lower()}, in place of {where}, to {procedure.does}"


def _parts(parts: dict[str, int]) -> str:
    return _listed([f"{n} {id.replace('_', ' ')}" for id, n in parts.items()])


def _values(pairs: Sequence[tuple[CoreValue, float]]) -> str:
    return _listed([value.replace("_", " ") for value, _ in pairs])


def _money(amount: float) -> str:
    return f"{amount:g}"


def _listed(parts: Sequence[str]) -> str:
    return parts[0] if len(parts) < 2 else f"{', '.join(parts[:-1])} and {parts[-1]}"
