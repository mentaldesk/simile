from datetime import timedelta

from pydantic import BaseModel, ConfigDict, Field

from simile.llm import Model
from simile.schema import CoreValue, HowKnown, Unit


class StoryConfig(BaseModel):
    """Every tunable constant of the incident and the lens."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str = Field(default=Model.SONNET, description="The model that writes the motive.")
    write_for: float = Field(
        default=180,
        gt=0,
        description="Real seconds to wait for the motive before writing it from templates.",
    )
    attackers: dict[int, float] = Field(
        default={1: 0.4, 2: 0.35, 3: 0.25},
        description="How likely each number of attackers is, while enough residents are hostile.",
    )
    hostile_from: float = Field(
        default=0.2,
        description="The least hostility to Aris an attacker has: their grievance's fit plus "
        "`harm`. If nobody has it, the most hostile resident attacks her alone.",
    )
    harm: float = Field(
        default=1.0,
        ge=0,
        description="How much low Compassion adds to hostility: this times (0.5 - compassion).",
    )
    grievance_spread: float = Field(
        default=0.15,
        ge=0,
        description="An attacker's grievance is drawn from those that fit them within this of "
        "their best.",
    )
    night_before: timedelta = Field(
        default=timedelta(days=8), description="How long before the world starts she was attacked."
    )
    night_at: tuple[int, int] = Field(
        default=(23, 20), description="The hour, and the latest minute past it, of the attack."
    )
    gone_before: timedelta = Field(
        default=timedelta(hours=26),
        description="How long before the world starts her workshop was found open.",
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
    owns_up_from: Unit = Field(
        default=0.6,
        description="An attacker at least this honest owns up to someone they trust "
        "`owns_up_to`. Anyone else never does.",
    )
    owns_up_to: Unit = 0.95
    admits_grudge_from: Unit = Field(
        default=0.75,
        description="The trust an attacker needs in whoever asks to own up to their grudge.",
    )
    salience: dict[HowKnown, Unit] = Field(
        default={HowKnown.DID: 0.9, HowKnown.WITNESSED: 0.7, HowKnown.TOLD: 0.5},
        description="How much a seeded memory matters to its owner, by how they know the fact.",
    )
    valence: dict[HowKnown, float] = Field(
        default={HowKnown.DID: -0.4, HowKnown.WITNESSED: -0.5, HowKnown.TOLD: -0.3},
        description="How its owner felt about it. A hostile resident is glad she's gone.",
    )
    relieved: float = Field(default=0.2, description="How a hostile resident feels she's gone.")
    keeps: dict[CoreValue, float] = Field(
        default={
            CoreValue.SECURITY: 0.3,
            CoreValue.TRADITION: 0.3,
            CoreValue.KNOWLEDGE: 0.2,
            CoreValue.ADVENTURE: 0.2,
        },
        description="The values of someone who'd keep an old thermal camera, whose infrared lens "
        "the eye needs, weighed as an attacker's grievance is.",
    )
    keeps_from: float = Field(
        default=0.1,
        description="The least lean to `keeps` the lens's keeper is drawn from. If nobody has "
        "it, whoever leans that way most keeps it.",
    )
    mentions_from: Unit = Field(
        default=0.55,
        description="The trust the keeper needs in the player to remember, and so say, that they "
        "have the lens.",
    )
    gives_from: Unit = Field(
        default=0.7, description="The trust the keeper needs in the player to give them the lens."
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
