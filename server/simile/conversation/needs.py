from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from simile.behaviour import DEFAULT_CONFIG as BEHAVIOUR
from simile.behaviour import Need
from simile.behaviour.config import Urgency
from simile.conversation.config import DEFAULT_CONFIG, ConversationConfig

MOODS: dict[Need, tuple[tuple[float, str], ...]] = {
    Need.HUNGER: ((0.9, "starving"), (0.75, "hungry")),
    Need.BLADDER: ((0.9, "bursting for the loo"), (0.75, "needing the loo")),
    Need.REST: ((0.9, "exhausted"), (0.6, "tired")),
    Need.HYGIENE: ((0.9, "badly in need of a shower"), (0.75, "feeling grubby")),
}
"""How each need feels from each level, as words that follow "you're" or "Kofi is"."""

ERRANDS: dict[Need, str] = {
    Need.HUNGER: "get something to eat",
    Need.BLADDER: "find a loo",
}
"""What a pressing need sends them off to do."""


@dataclass(frozen=True)
class Pressing:
    """What someone's needs bring to a conversation."""

    mood: tuple[str, ...] = ()
    errand: str | None = None
    """What their most pressing need sends them off to do, once it presses at all."""
    pressure: float = 0.0
    """0 up to `drain_from`, rising to 1 at the need's critical level."""
    urgent: bool = False
    """A need is at or past its critical level."""

    def drain(self, config: ConversationConfig = DEFAULT_CONFIG) -> float:
        """How many times faster than usual their engagement drains."""
        return 1 + config.need_drain * self.pressure


def critical(urgency: Mapping[Need, Urgency]) -> dict[Need, float]:
    """B1's critical level for each need that has one."""
    return {need: curve.critical for need, curve in urgency.items() if curve.critical is not None}


CRITICAL = critical(BEHAVIOUR.urgency)


def pressing(
    needs: Mapping[Need, float],
    levels: Mapping[Need, float] = CRITICAL,
    config: ConversationConfig = DEFAULT_CONFIG,
) -> Pressing:
    """What `needs` bring to a conversation, given B1's critical `levels`."""
    shares = {need: share(needs.get(need, 0.0), level, config) for need, level in levels.items()}
    worst = max(shares, key=lambda need: shares[need], default=None)
    pressure = shares[worst] if worst else 0.0
    return Pressing(
        mood=mood(needs),
        errand=ERRANDS.get(worst) if worst and pressure > 0 else None,
        pressure=round(pressure, 3),
        urgent=any(needs.get(need, 0.0) >= level for need, level in levels.items()),
    )


def share(found: float, level: float, config: ConversationConfig = DEFAULT_CONFIG) -> float:
    if found >= level:
        return 1.0
    span = level - config.drain_from
    return max(found - config.drain_from, 0.0) / span if span > 0 else 0.0


def mood(needs: Mapping[Need, float]) -> tuple[str, ...]:
    found = []
    for need, steps in MOODS.items():
        words = next((words for level, words in steps if needs.get(need, 0.0) >= level), None)
        if words:
            found.append(words)
    return tuple(found)


def feels(subject: str, mood: Sequence[str]) -> str:
    """`mood` said of `subject`, "you" or a name, or nothing for no mood."""
    if not mood:
        return ""
    words = mood[0] if len(mood) == 1 else f"{', '.join(mood[:-1])} and {mood[-1]}"
    who = "you're" if subject == "you" else f"{subject} is"
    return f"Right now {who} {words}."
