from datetime import time, timedelta

from pydantic import BaseModel, ConfigDict, Field

from simile.schema import CoreValue, HowKnown, Unit


class StoryConfig(BaseModel):
    """Every tunable constant of the disappearance and the lens."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    gone_before: timedelta = Field(
        default=timedelta(hours=26),
        description="How long before the world starts her workshop was found open.",
    )
    seen_between: tuple[time, time] = Field(
        default=(time(21, 20), time(22, 0)),
        description="When, the evening before, she was last seen: on the five minutes between "
        "these.",
    )
    distrusts_from: int = Field(
        default=-1,
        ge=-2,
        le=2,
        description="The S11 bionics `level` at or below which a resident distrusted her: -1 "
        "against, -2 strongly. If nobody is that far, the least tolerant distrusts her alone.",
    )
    distruster_lies_below: Unit = Field(
        default=0.6,
        description="A distruster less honest than this denies it to those they don't trust "
        "enough, rather than keeping quiet.",
    )
    admits_from: Unit = Field(
        default=0.75,
        description="The trust a distruster needs in whoever asks to tell what they know of her, "
        "unless they're strongly against bionics and honest, when they tell anyone.",
    )
    tells_from: dict[CoreValue, float] = Field(
        default={
            CoreValue.SECURITY: 0.3,
            CoreValue.PEACE_OF_MIND: 0.2,
            CoreValue.JUSTICE: -0.3,
            CoreValue.HONESTY: -0.2,
        },
        description="How wary a witness is: the trust they need in whoever asks is 0.5 plus "
        "each weight times (value - 0.5), from 0 to `most_wary`.",
    )
    most_wary: Unit = 0.9
    witness_lies_below: Unit = Field(
        default=0.4,
        description="A witness less honest than this lies to those they don't trust enough, "
        "rather than keeping quiet.",
    )
    salience: dict[HowKnown, Unit] = Field(
        default={HowKnown.DID: 0.9, HowKnown.WITNESSED: 0.7, HowKnown.TOLD: 0.5},
        description="How much a seeded memory matters to its owner, by how they know the fact.",
    )
    valence: dict[HowKnown, float] = Field(
        default={HowKnown.DID: -0.4, HowKnown.WITNESSED: -0.5, HowKnown.TOLD: -0.3},
        description="How its owner felt about it. A distruster is glad she's gone.",
    )
    relieved: float = Field(default=0.2, description="How a distruster feels she's gone.")
    tolerates_from: int = Field(
        default=0,
        ge=-2,
        le=2,
        description="The least S11 bionics `level` the lens's keeper is drawn from: 0 barely "
        "minds, 1 for. If nobody has it, whoever takes to bionics best keeps it.",
    )
    mentions_from: Unit = Field(
        default=0.58,
        description="The trust the keeper needs in the player to remember, and so say, that they "
        "have the lens.",
    )
    gives_from: Unit = Field(
        default=0.62, description="The trust the keeper needs in the player to give them the lens."
    )
    lens_every: float = Field(
        default=60.0,
        gt=0,
        description="Sim seconds between checks of whether the keeper trusts the player enough "
        "to speak of the lens.",
    )
    clue_reach: float = Field(
        default=0.5,
        gt=0,
        description="How far from a clue's cell, in tiles, `pick_up` finds it: the client's "
        "reach, so both take the same of a clue and a nearer pile.",
    )


DEFAULT_CONFIG = StoryConfig()
