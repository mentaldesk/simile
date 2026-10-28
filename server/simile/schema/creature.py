from enum import StrEnum


class CreatureKind(StrEnum):
    """What a creature is, named as its figure is in `content/creatures/`: a `rat`, a recycler
    `bot`, a wild `dog` or a `bat`."""

    RAT = "rat"
    BOT = "bot"
    DOG = "dog"
    BAT = "bat"


class CreatureState(StrEnum):
    """What a creature is doing, which picks the pose its figure plays. `idle` stands, or for a
    bat flies on the spot. `moving`, `chasing` and `fleeing` play its kind's cycle: walk, run or
    fly. `attacking` plays its attack, and `roosting`, a bat's alone, hangs from the ceiling.
    `hurt` stands, or for a bat flies."""

    IDLE = "idle"
    MOVING = "moving"
    CHASING = "chasing"
    FLEEING = "fleeing"
    ATTACKING = "attacking"
    ROOSTING = "roosting"
    HURT = "hurt"
