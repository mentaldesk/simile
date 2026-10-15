from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from simile.schema import CoreValue

V = CoreValue


class Need(StrEnum):
    SOCIAL = "social"
    CURIOSITY = "curiosity"
    REST = "rest"


class Activity(StrEnum):
    """What an NPC is up to. The amenities' values are their location ids."""

    HOME = "home"
    COFFEE_SHOP = "coffee_shop"
    SQUARE = "square"
    NEWS = "news"
    PARK = "park"
    NOODLE_BAR = "noodle_bar"
    MAKER_SPACE = "maker_space"
    WANDER = "wander"
    SEEK = "seek"
    IDLE = "idle"
    SLEEP = "sleep"
    TALK = "talk"


A = Activity

type Curve = tuple[tuple[float, float], ...]

VALUE_WEIGHTS: dict[Activity, dict[CoreValue, float]] = {
    A.HOME: {V.PEACE_OF_MIND: 0.6, V.SECURITY: 0.4, V.TRADITION: 0.2, V.ADVENTURE: -0.3},
    A.COFFEE_SHOP: {V.CONNECTION: 0.5, V.PLEASURE: 0.4, V.SUCCESS: 0.1},
    A.SQUARE: {V.CONNECTION: 0.4, V.FREEDOM: 0.2, V.EQUALITY: 0.1},
    A.NEWS: {V.KNOWLEDGE: 0.8, V.OPEN_MINDEDNESS: 0.6, V.JUSTICE: 0.2},
    A.PARK: {V.PEACE_OF_MIND: 0.7, V.FREEDOM: 0.2, V.ADVENTURE: 0.1},
    A.NOODLE_BAR: {V.PLEASURE: 0.6, V.CONNECTION: 0.3},
    A.MAKER_SPACE: {
        V.CREATIVITY: 0.8,
        V.SELF_ACTUALIZATION: 0.4,
        V.KNOWLEDGE: 0.2,
        V.AMBITION: 0.2,
    },
    A.WANDER: {V.ADVENTURE: 0.8, V.FREEDOM: 0.4, V.OPEN_MINDEDNESS: 0.2, V.SECURITY: -0.3},
    A.SEEK: {V.CONNECTION: 1.0, V.COMPASSION: 0.2, V.INDEPENDENCE: -0.3},
    A.IDLE: {V.PEACE_OF_MIND: 0.1},
}

NEED_WEIGHTS: dict[Activity, dict[Need, float]] = {
    A.HOME: {Need.REST: 0.8},
    A.COFFEE_SHOP: {Need.SOCIAL: 0.5, Need.REST: 0.2},
    A.SQUARE: {Need.SOCIAL: 0.4, Need.CURIOSITY: 0.1},
    A.NEWS: {Need.CURIOSITY: 0.9},
    A.PARK: {Need.REST: 0.4, Need.CURIOSITY: 0.1},
    A.NOODLE_BAR: {Need.SOCIAL: 0.4, Need.REST: 0.2},
    A.MAKER_SPACE: {Need.CURIOSITY: 0.6},
    A.WANDER: {Need.CURIOSITY: 0.4},
    A.SEEK: {Need.SOCIAL: 1.0},
    A.IDLE: {Need.REST: 0.2},
}

BASE: dict[Activity, float] = {A.COFFEE_SHOP: 0.1, A.SQUARE: 0.05, A.IDLE: -0.1}

DAILY: dict[Activity, Curve] = {
    A.COFFEE_SHOP: ((6.5, 0.0), (8.0, 0.3), (10.0, 0.1), (13.0, 0.0), (15.0, 0.15), (17.0, 0.0)),
    A.NOODLE_BAR: ((11.0, 0.0), (12.5, 0.35), (14.0, 0.0), (17.5, 0.0), (19.0, 0.35), (21.0, 0.0)),
    A.SQUARE: ((9.0, 0.0), (12.0, 0.1), (17.0, 0.15), (20.0, 0.0)),
    A.PARK: ((9.0, 0.0), (15.0, 0.15), (19.0, 0.0)),
}

RISE: dict[Need, float] = {Need.SOCIAL: 0.04, Need.CURIOSITY: 0.03, Need.REST: 0.04}

RISE_VALUES: dict[Need, dict[CoreValue, float]] = {
    Need.SOCIAL: {V.CONNECTION: 0.1},
    Need.CURIOSITY: {V.KNOWLEDGE: 0.05, V.OPEN_MINDEDNESS: 0.05},
    Need.REST: {V.PEACE_OF_MIND: 0.03},
}

EFFECTS: dict[Activity, dict[Need, float]] = {
    A.HOME: {Need.REST: -0.3},
    A.SLEEP: {Need.REST: -0.25},
    A.COFFEE_SHOP: {Need.SOCIAL: -0.15, Need.REST: -0.1},
    A.SQUARE: {Need.SOCIAL: -0.1, Need.CURIOSITY: -0.05},
    A.NEWS: {Need.CURIOSITY: -3.0},
    A.PARK: {Need.REST: -0.2, Need.CURIOSITY: -0.05},
    A.NOODLE_BAR: {Need.SOCIAL: -0.15, Need.REST: -0.1},
    A.MAKER_SPACE: {Need.CURIOSITY: -1.2},
    A.WANDER: {Need.CURIOSITY: -0.3},
    A.SEEK: {Need.SOCIAL: -0.3},
    A.IDLE: {Need.REST: -0.1},
    A.TALK: {Need.SOCIAL: -1.2},
}

DWELL: dict[Activity, tuple[float, float]] = {
    A.HOME: (15, 60),
    A.COFFEE_SHOP: (15, 45),
    A.SQUARE: (10, 30),
    A.NEWS: (5, 15),
    A.PARK: (15, 50),
    A.NOODLE_BAR: (20, 45),
    A.MAKER_SPACE: (20, 60),
    A.WANDER: (1, 5),
    A.SEEK: (3, 10),
    A.IDLE: (2, 8),
}

BEDTIME_VALUES: dict[CoreValue, float] = {
    V.DISCIPLINE: -1.0,
    V.RESPONSIBILITY: -0.5,
    V.ADVENTURE: 0.8,
    V.PLEASURE: 0.8,
    V.FREEDOM: 0.4,
}

WAKE_VALUES: dict[CoreValue, float] = {
    V.DISCIPLINE: -1.2,
    V.RESPONSIBILITY: -0.4,
    V.PLEASURE: 0.6,
    V.PEACE_OF_MIND: 0.3,
}


class BehaviourConfig(BaseModel):
    """Every weight and constant of the decision loop. Values are 0-1 and enter scores centred,
    as `value - 0.5`. Needs are 0 (satisfied) to 1 (urgent). Rates are per sim hour."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    base: dict[Activity, float] = Field(default=BASE, description="Each activity's base score.")
    value_weights: dict[Activity, dict[CoreValue, float]] = Field(
        default=VALUE_WEIGHTS, description="Score per unit of `value - 0.5`, by activity."
    )
    need_weights: dict[Activity, dict[Need, float]] = Field(
        default=NEED_WEIGHTS, description="Score per unit of need, by activity."
    )
    daily: dict[Activity, Curve] = Field(
        default=DAILY,
        description="Score by time of day: (hour, bonus) points, linear between them and 0 "
        "outside them.",
    )
    evening_weight: float = Field(
        default=0.6, description="Bonus for going home, reached at the NPC's bedtime."
    )
    evening_hours: float = Field(
        default=2.0, gt=0, description="How long before bedtime the pull home starts."
    )
    repeat_penalty: float = Field(
        default=0.2, ge=0, description="Taken off the activity the NPC has just finished."
    )
    travel_weight: float = Field(default=0.05, ge=0, description="Taken off per minute of walk.")

    affinity_weights: dict[str, float] = Field(
        default={"like": 1.0, "trust": 0.4, "respect": 0.2, "familiarity": 0.3},
        description="How a relationship becomes affinity: weight * (score - 0.5) for like, trust "
        "and respect, weight * familiarity.",
    )
    sociability: float = Field(
        default=1.0,
        ge=0,
        description="How much Connection scales the pull of people they like: "
        "1 + sociability * (connection - 0.5).",
    )
    seek_weight: float = Field(default=0.6, description="Seek score per unit of affinity.")
    company_weight: float = Field(
        default=0.3, description="Score per unit of positive affinity for each person at a place."
    )
    avoid_weight: float = Field(
        default=1.0,
        ge=0,
        description="Score per unit of negative affinity for each person at a place.",
    )
    crowd_weight: float = Field(
        default=0.2, description="Score per person at a place, per unit of `connection - 0.5`."
    )
    crowd_cap: int = Field(default=4, ge=0, description="People beyond this don't add to a crowd.")
    temperature: float = Field(
        default=0.1,
        ge=0,
        description="Randomness of the choice between activities: softmax temperature over their "
        "scores. 0 always picks the best.",
    )

    rise: dict[Need, float] = Field(default=RISE, description="How fast each need rises awake.")
    rise_values: dict[Need, dict[CoreValue, float]] = Field(
        default=RISE_VALUES, description="Extra rise per unit of each value."
    )
    effects: dict[Activity, dict[Need, float]] = Field(
        default=EFFECTS,
        description="How each activity changes needs once there. Negative satisfies.",
    )
    walking: dict[Need, float] = Field(
        default={Need.REST: 0.1}, description="How walking changes needs."
    )
    company: float = Field(
        default=0.2, ge=0, description="How fast having someone near satisfies social need."
    )
    near: float = Field(
        default=4.0, gt=0, description="Tiles within which someone counts as company."
    )
    talk_range: float = Field(
        default=2.5, gt=0, description="Tiles within which a seeker asks for a conversation."
    )
    chases: int = Field(
        default=3, ge=0, description="Times a seeker follows someone who moved before giving up."
    )
    seek_cooldown: float = Field(
        default=45, ge=0, description="Minutes before seeking someone who declined again."
    )
    wander_radius: int = Field(default=12, ge=1, description="How far a wander goes, in tiles.")
    dwell: dict[Activity, tuple[float, float]] = Field(
        default=DWELL, description="Minutes spent at an activity once there, sampled uniformly."
    )
    start_dwell: tuple[float, float] = Field(
        default=(2, 30), description="Minutes awake at home before the first decision."
    )
    start_needs: dict[Need, tuple[float, float]] = Field(
        default={Need.SOCIAL: (0.2, 0.5), Need.CURIOSITY: (0.2, 0.5), Need.REST: (0.0, 0.15)},
        description="Needs on start, sampled uniformly.",
    )

    bedtime: float = Field(default=22.5, description="Hour an average NPC goes home to sleep.")
    bedtime_values: dict[CoreValue, float] = Field(
        default=BEDTIME_VALUES, description="Hours later per unit of `value - 0.5`."
    )
    bedtime_range: tuple[float, float] = Field(
        default=(21.0, 23.75), description="Earliest and latest bedtime."
    )
    wake: float = Field(default=7.0, description="Hour an average NPC wakes up.")
    wake_values: dict[CoreValue, float] = Field(
        default=WAKE_VALUES, description="Hours later per unit of `value - 0.5`."
    )
    wake_range: tuple[float, float] = Field(
        default=(5.5, 9.0), description="Earliest and latest wake time."
    )
    lie_in: float = Field(
        default=20, ge=0, description="Up to this many minutes after waking before getting up."
    )

    think_every: float = Field(
        default=5.0,
        gt=0,
        description="Sim seconds between updating needs and checking whose turn it is to decide.",
    )

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if not 0 < self.wake_range[0] <= self.wake_range[1] < self.bedtime_range[0]:
            raise ValueError("wake_range must come before bedtime_range")
        if not self.bedtime_range[0] <= self.bedtime_range[1] < 24:
            raise ValueError("bedtime_range must be before midnight")
        return self


DEFAULT_CONFIG = BehaviourConfig()
