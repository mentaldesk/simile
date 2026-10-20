from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from simile.schema import CoreValue, Medium, MemoryKind

V = CoreValue


class Need(StrEnum):
    SOCIAL = "social"
    CURIOSITY = "curiosity"
    REST = "rest"
    NEWS = "news"
    INSPIRATION = "inspiration"
    HUNGER = "hunger"
    FINANCES = "finances"
    BOREDOM = "boredom"
    RELAXATION = "relaxation"
    EXERCISE = "exercise"


class Activity(StrEnum):
    """What an NPC is up to. The amenities' values are their location ids."""

    HOME = "home"
    COFFEE_SHOP = "coffee_shop"
    SQUARE = "square"
    NEWS = "news"
    PARK = "park"
    NOODLE_BAR = "noodle_bar"
    MAKER_SPACE = "maker_space"
    GALLERY = "gallery"
    WANDER = "wander"
    SEEK = "seek"
    IDLE = "idle"
    CREATE = "create"
    WORK = "work"
    EXERCISE = "exercise"
    SLEEP = "sleep"
    TALK = "talk"


A = Activity

type Curve = tuple[tuple[float, float], ...]

VALUE_WEIGHTS: dict[Activity, dict[CoreValue, float]] = {
    A.HOME: {V.PEACE_OF_MIND: 0.6, V.SECURITY: 0.4, V.TRADITION: 0.2, V.ADVENTURE: -0.3},
    A.COFFEE_SHOP: {V.CONNECTION: 0.5, V.PLEASURE: 0.4, V.SUCCESS: 0.1},
    A.SQUARE: {V.CONNECTION: 0.4, V.FREEDOM: 0.2, V.EQUALITY: 0.1},
    A.PARK: {V.PEACE_OF_MIND: 0.7, V.FREEDOM: 0.2, V.ADVENTURE: 0.1},
    A.NOODLE_BAR: {V.PLEASURE: 0.6, V.CONNECTION: 0.3},
    A.MAKER_SPACE: {
        V.CREATIVITY: 0.3,
        V.SELF_ACTUALIZATION: 0.2,
        V.KNOWLEDGE: 0.2,
        V.AMBITION: 0.2,
    },
    A.GALLERY: {
        V.OPEN_MINDEDNESS: 0.4,
        V.KNOWLEDGE: 0.3,
        V.CREATIVITY: 0.2,
        V.PEACE_OF_MIND: 0.2,
    },
    A.WANDER: {V.ADVENTURE: 0.8, V.FREEDOM: 0.4, V.OPEN_MINDEDNESS: 0.2, V.SECURITY: -0.3},
    A.SEEK: {V.CONNECTION: 1.0, V.COMPASSION: 0.2, V.INDEPENDENCE: -0.3, V.PEACE_OF_MIND: -0.5},
    A.IDLE: {V.PEACE_OF_MIND: 0.1},
}

BASE: dict[Activity, float] = {
    A.HOME: -0.05,
    A.COFFEE_SHOP: 0.075,
    A.NOODLE_BAR: 0.025,
    A.SQUARE: 0.05,
    A.NEWS: -0.3,
    A.GALLERY: -0.1,
    A.IDLE: -0.4,
    A.CREATE: -1.0,
    A.WORK: -0.1,
}

WRITING_PLACES: dict[Activity, dict[CoreValue, float]] = {
    A.HOME: {V.PEACE_OF_MIND: 0.5, V.INDEPENDENCE: 0.4, V.SECURITY: 0.2, V.TRADITION: 0.2},
    A.COFFEE_SHOP: {V.CONNECTION: 0.6, V.PLEASURE: 0.3, V.OPEN_MINDEDNESS: 0.3},
    A.MAKER_SPACE: {V.AMBITION: 0.4, V.SUCCESS: 0.2},
}

DAILY: dict[Activity, Curve] = {
    A.COFFEE_SHOP: ((6.5, 0.0), (8.0, 0.3), (10.0, 0.1), (13.0, 0.0), (15.0, 0.15), (17.0, 0.0)),
    A.SQUARE: ((9.0, 0.0), (12.0, 0.1), (17.0, 0.15), (20.0, 0.0)),
    A.PARK: ((9.0, 0.0), (15.0, 0.15), (19.0, 0.0)),
}

RISE: dict[Need, float] = {
    Need.SOCIAL: 0.02,
    Need.CURIOSITY: 0.03,
    Need.REST: 0.04,
    Need.NEWS: -0.1,
    Need.INSPIRATION: 0.06,
    Need.HUNGER: 0.16,
    Need.BOREDOM: 0.4,
    Need.RELAXATION: 0.02,
    Need.EXERCISE: 0.03,
}

RISE_VALUES: dict[Need, dict[CoreValue, float]] = {
    Need.SOCIAL: {V.CONNECTION: 0.65, V.PEACE_OF_MIND: -0.1},
    Need.CURIOSITY: {V.KNOWLEDGE: 0.05, V.OPEN_MINDEDNESS: 0.05},
    Need.REST: {V.PEACE_OF_MIND: 0.03},
    Need.NEWS: {V.KNOWLEDGE: 0.4, V.OPEN_MINDEDNESS: 0.15},
    Need.INSPIRATION: {V.CREATIVITY: 0.22, V.SELF_ACTUALIZATION: 0.05},
    Need.HUNGER: {V.PLEASURE: 0.06},
    Need.BOREDOM: {
        V.ADVENTURE: 0.3,
        V.FREEDOM: 0.15,
        V.OPEN_MINDEDNESS: 0.15,
        V.PEACE_OF_MIND: -0.2,
        V.TRADITION: -0.15,
    },
    Need.RELAXATION: {V.PEACE_OF_MIND: 0.04, V.PLEASURE: 0.03},
    Need.EXERCISE: {V.DISCIPLINE: 0.05, V.ADVENTURE: 0.03},
}

RISE_ASLEEP: dict[Need, float] = {Need.HUNGER: 0.3}

EFFECTS: dict[Activity, dict[Need, float]] = {
    A.HOME: {Need.REST: -0.3, Need.HUNGER: -1.2, Need.RELAXATION: -0.4},
    A.SLEEP: {Need.REST: -0.25, Need.BOREDOM: -1.0, Need.RELAXATION: -0.2},
    A.COFFEE_SHOP: {
        Need.SOCIAL: -0.15,
        Need.REST: -0.1,
        Need.CURIOSITY: -0.3,
        Need.HUNGER: -2.0,
        Need.RELAXATION: -0.6,
    },
    A.SQUARE: {Need.SOCIAL: -0.1, Need.CURIOSITY: -0.4},
    A.NEWS: {Need.CURIOSITY: -3.0, Need.NEWS: -3.6, Need.BOREDOM: -3.0, Need.RELAXATION: -0.8},
    A.PARK: {Need.REST: -0.2, Need.CURIOSITY: -0.2, Need.RELAXATION: -1.5},
    A.NOODLE_BAR: {Need.SOCIAL: -0.15, Need.REST: -0.1, Need.HUNGER: -3.0},
    A.MAKER_SPACE: {Need.CURIOSITY: -0.9, Need.RELAXATION: 0.05},
    A.GALLERY: {
        Need.CURIOSITY: -0.5,
        Need.REST: -0.1,
        Need.RELAXATION: -0.8,
    },
    A.WANDER: {Need.CURIOSITY: -4.0, Need.BOREDOM: -2.0, Need.EXERCISE: -0.8},
    A.SEEK: {Need.SOCIAL: -0.3},
    A.IDLE: {Need.REST: -0.1},
    A.CREATE: {Need.CURIOSITY: -0.6, Need.BOREDOM: -1.0, Need.RELAXATION: 0.1},
    A.WORK: {Need.BOREDOM: -0.5, Need.RELAXATION: 0.1},
    A.TALK: {Need.SOCIAL: -6.0, Need.BOREDOM: -3.0},
    A.EXERCISE: {Need.EXERCISE: -2.5, Need.BOREDOM: -1.0},
}

FINISHING: dict[Activity, dict[Need, float]] = {A.CREATE: {Need.INSPIRATION: -1.0}}

DWELL: dict[Activity, tuple[float, float]] = {
    A.HOME: (15, 60),
    A.COFFEE_SHOP: (15, 45),
    A.SQUARE: (10, 30),
    A.NEWS: (5, 15),
    A.PARK: (15, 50),
    A.NOODLE_BAR: (20, 45),
    A.MAKER_SPACE: (20, 60),
    A.GALLERY: (15, 40),
    A.WANDER: (3, 10),
    A.SEEK: (3, 10),
    A.IDLE: (1, 3),
    A.CREATE: (20, 45),
    A.WORK: (30, 75),
    A.EXERCISE: (15, 40),
}

LOOPS: dict[str, tuple[tuple[int, int], ...]] = {
    "lotus_lake": ((47, 14), (62, 14), (62, 17), (52, 18), (51, 29), (62, 30), (62, 33), (47, 33)),
    "village": ((1, 12), (44, 12), (45, 35), (1, 35)),
}

STREET_LOOPS: dict[str, dict[str, tuple[tuple[int, int], ...]]] = {
    "lychee_lane": {"lotus_lake": ((36, 15), (59, 15), (48, 12))},
    "high_street": {"village": ((1, 15), (82, 15))},
}


CRAFT_WORDS: dict[Medium, tuple[str, ...]] = {
    Medium.WRITING: ("writ", "poem", "poet", "verse", "story", "stories", "book", "essay", "words"),
    Medium.MURAL: ("mural", "wall", "paint", "street art", "graffiti", "art"),
    Medium.PAINTING: ("paint", "canvas", "gallery", "portrait", "landscape", "art"),
}

VALUE_WORDS: dict[CoreValue, tuple[str, ...]] = {
    V.FREEDOM: ("freedom", "liberty", "rights", "privacy", "surveillance", "choice"),
    V.INDEPENDENCE: ("independen", "self-reliance", "self-sufficien", "diy", "own business"),
    V.SELF_RESPECT: ("pride", "dignity", "respect"),
    V.SELF_ACTUALIZATION: ("growth", "potential", "dream", "purpose", "calling"),
    V.CREATIVITY: ("art", "creativ", "idea", "invent", "design", "music", "craft", "making"),
    V.HONESTY: ("honest", "truth", "lie", "lies", "transparen", "corruption", "scandal"),
    V.COMPASSION: ("kindness", "care", "caring", "charity", "lonel", "wellbeing", "struggling"),
    V.LOYALTY: ("loyal", "friendship", "family", "promise", "commitment"),
    V.JUSTICE: ("justice", "fair", "unfair", "rights", "court", "tenant", "rent"),
    V.RESPONSIBILITY: ("responsib", "duty", "accountab", "obligation"),
    V.SECURITY: ("security", "safety", "safe", "crime", "savings", "pension", "insurance"),
    V.EQUALITY: ("equal", "inequality", "discriminat", "inclusion", "fair pay", "pay gap"),
    V.TRADITION: ("tradition", "heritage", "history", "custom", "festival", "folk", "parish"),
    V.OBEDIENCE: ("rules", "regulation", "law", "authority", "council", "order", "rota"),
    V.SUCCESS: ("success", "business", "profit", "achievement", "award", "winning", "results"),
    V.AMBITION: ("ambition", "career", "start-up", "startup", "promotion", "expansion", "growth"),
    V.DISCIPLINE: ("discipline", "routine", "training", "habit", "practice"),
    V.KNOWLEDGE: ("knowledge", "science", "research", "study", "learning", "education", "book"),
    V.OPEN_MINDEDNESS: ("culture", "perspective", "debate", "different", "diversity", "travel"),
    V.PEACE_OF_MIND: ("calm", "quiet", "peace", "rest", "nature", "garden", "stress", "anxiety"),
    V.PLEASURE: ("food", "drink", "cocktail", "party", "fun", "holiday", "coffee", "dancing"),
    V.CONNECTION: ("community", "neighbour", "together", "lonel", "belonging", "friends"),
    V.ADVENTURE: ("adventure", "travel", "explor", "trek", "journey", "trip"),
    V.OPTIMISM: ("hope", "future", "optimis", "progress", "bright"),
}


class Urgency(BaseModel):
    """How pressing a need feels: `need ** power`, so with a power above 1 a little barely
    registers and a lot crowds out everything else."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    power: float = Field(default=3.0, gt=0, description="The urgency curve's exponent.")
    weight: float = Field(ge=0, description="Score per unit of relief.")
    critical: float | None = Field(
        default=0.9,
        gt=0,
        le=1,
        description="Above this they stop what they're doing and decide again, unless what "
        "they're doing meets the need. None never interrupts.",
    )
    appetite: float = Field(
        default=0.0,
        ge=0,
        le=1,
        description="A place starts meeting the need only once it's this high, and then carries "
        "on until it's met or they leave: they eat when they're hungry, not every time they "
        "pass the fridge.",
    )


URGENCY: dict[Need, Urgency] = {
    Need.SOCIAL: Urgency(weight=6.0, critical=None),
    Need.CURIOSITY: Urgency(power=1.0, weight=1.6, critical=None),
    Need.REST: Urgency(power=1.0, weight=4.0, critical=None),
    Need.NEWS: Urgency(power=2.0, weight=10.0, critical=None),
    Need.INSPIRATION: Urgency(power=2.0, weight=20.0, critical=None),
    Need.HUNGER: Urgency(weight=16.0, appetite=0.75),
    Need.FINANCES: Urgency(power=1.0, weight=100.0, critical=None),
    Need.BOREDOM: Urgency(power=1.0, weight=4.0, critical=None),
    Need.RELAXATION: Urgency(power=2.0, weight=6.0, critical=None),
    Need.EXERCISE: Urgency(power=2.0, weight=6.0, critical=None),
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
    urgency: dict[Need, Urgency] = Field(
        default=URGENCY,
        description="Each need's urgency curve. An option scores the relief it brings over a "
        "typical stay: for each need, weight times the area under need ** power between the "
        "need now and after the stay's `effects`, so the same relief is worth much more to "
        "someone desperate. A terminal's relief is scaled by how interesting the best unread "
        "article is, and a place's by how much of it the `supply` hook says is there.",
    )
    talk_minutes: float = Field(
        default=3.0, gt=0, description="How long seeking someone out promises to talk for."
    )
    player_relief: float = Field(
        default=0.5,
        ge=0,
        description="How much of a talk's social relief talking with the player brings, and "
        "seeking them out promises, so residents still look for each other.",
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
        default=0.2,
        ge=0,
        description="Taken off the activity the NPC has just finished, except work, where staying "
        "on carries on.",
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
        default=RISE_VALUES,
        description="Extra rise per unit of each value. Inspiration rises only for NPCs with a "
        "craft.",
    )
    rise_asleep: dict[Need, float] = Field(
        default=RISE_ASLEEP,
        description="How fast each need rises asleep, as a share of how fast it rises awake. "
        "Needs left out don't rise, so they wake hungry but not lonely.",
    )
    sociability_spread: float = Field(
        default=2.0,
        ge=1,
        description="How far the sociability trait moves social: at 1 it rises this many times "
        "faster and talking meets it this many times more slowly, and the other way round at 0. "
        "A sociable resident gets lonely sooner and takes longer to have had enough, so they "
        "look for company more often and come to a conversation keener.",
    )
    effects: dict[Activity, dict[Need, float]] = Field(
        default=EFFECTS,
        description="How each activity changes needs each hour once there, and so the relief it "
        "offers. Negative satisfies.",
    )
    finishing: dict[Activity, dict[Need, float]] = Field(
        default=FINISHING,
        description="How finishing a stay changes needs, all at once as they leave. A stay cut "
        "short brings none of it.",
    )
    writing_places: dict[Activity, dict[CoreValue, float]] = Field(
        default=WRITING_PLACES,
        description="Where writers go to write, by the activity whose place it is, with the score "
        "per unit of `value - 0.5` for writing there.",
    )
    writing_base: dict[Activity, float] = Field(
        default={A.MAKER_SPACE: -0.1},
        description="Score for writing at each of the writing_places before values. The maker "
        "space starts behind, since its regulars already crowd it.",
    )
    walking: dict[Need, float] = Field(
        default={Need.REST: 0.1}, description="How walking changes needs."
    )
    company: float = Field(
        default=0.1, ge=0, description="How fast having someone near satisfies social need."
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
        default=DWELL,
        description="The shortest and longest stay at an activity once there, in minutes. From "
        "the shortest on they look again every `reconsider` minutes, and leave once something "
        "else is worth more. A stay in `seen_through` lasts a draw between them.",
    )
    seen_through: tuple[Activity, ...] = Field(
        default=(A.CREATE,),
        description="Stays that last their drawn dwell, as their worth comes at the end.",
    )
    reconsider: float = Field(
        default=2.0, gt=0, description="Minutes between looks at whether a stay still pays."
    )
    switch: float = Field(
        default=0.15,
        ge=0,
        description="What leaving a stay early costs: the best other option must beat staying "
        "by this much.",
    )
    novelty: float = Field(
        default=0.3,
        ge=0,
        le=1,
        description="How far boredom falls on arriving somewhere other than their last stay, "
        "unless it's `familiar`.",
    )
    familiar: tuple[Activity, ...] = Field(
        default=(A.HOME, A.SLEEP, A.IDLE, A.WORK),
        description="Where arriving is nothing new.",
    )
    new_spot: float = Field(
        default=0.15,
        ge=0,
        le=1,
        description="How far boredom falls on moving to another spot in the same place, such as "
        "another painting or a bench with a friend on it.",
    )
    spot_switch: float = Field(
        default=0.04,
        ge=0,
        description="What moving to another spot costs: it must beat staying put by this much.",
    )
    relieved: float = Field(
        default=0.5,
        ge=0,
        description="What a stay must relieve an hour, as score, to keep boredom from rising. "
        "Boredom rises at its full rate where nothing is relieved, and more slowly the more is.",
    )
    busy: float = Field(
        default=0.03,
        ge=0,
        description="How much faster relaxation rises an hour for each other person near them "
        "out of home, up to `crowd_cap`. Sociability divides it, by up to "
        "`sociability_spread`.",
    )
    loops: dict[str, tuple[tuple[int, int], ...]] = Field(
        default=LOOPS,
        description="Walks round the village map for exercise, as the tiles they pass in order, "
        "back to the first.",
    )
    loops_on: dict[str, dict[str, tuple[tuple[int, int], ...]]] = Field(
        default=STREET_LOOPS,
        description="Walks for exercise on other maps, by map id, as `loops` are on the village. "
        "Only the walks on the world's maps are options.",
    )
    start_dwell: tuple[float, float] = Field(
        default=(0.5, 5), description="Minutes awake at home before the first decision."
    )
    head_starts: int = Field(
        default=2,
        ge=0,
        description="On a fresh start, how many of the residents keenest to make something are "
        "already partway through, at home, so the first new work comes soon. Muralists need a "
        "wall, so they're left out.",
    )
    head_start: tuple[float, float] = Field(
        default=(4, 12), description="Minutes left of a head start's stay, sampled uniformly."
    )
    inspiring: tuple[MemoryKind, ...] = Field(
        default=(MemoryKind.CONVERSATION, MemoryKind.NEWS, MemoryKind.WORK),
        description="Kinds of new memory that raise a crafter's inspiration: a conversation, an "
        "article read, someone else's work read or seen. Making their own doesn't.",
    )
    inspiration_weight: float = Field(
        default=0.15,
        ge=0,
        description="Inspiration from a new memory of salience 1 felt as strongly as can be, "
        "before `inspiration_craft` and `inspiration_values`.",
    )
    calm: float = Field(
        default=0.3,
        ge=0,
        le=1,
        description="How much a memory felt neither way counts, as a share of one felt as "
        "strongly as can be. A memory's intensity is calm + (1 - calm) * |valence|.",
    )
    inspiration_craft: float = Field(
        default=1.5,
        ge=0,
        description="Extra inspiration, as a share, from a memory whose topics touch their craft: "
        "its medium (`craft_words`) or the words of its form.",
    )
    inspiration_values: float = Field(
        default=0.5,
        ge=0,
        description="Extra inspiration, as a share, from a memory whose topics touch one of their "
        "`strongest` values (`value_words`).",
    )
    strongest: int = Field(
        default=3, ge=0, description="How many of their strongest values a memory can touch."
    )
    craft_words: dict[Medium, tuple[str, ...]] = Field(
        default=CRAFT_WORDS,
        description="Words a topic touching each medium has, or begins with.",
    )
    value_words: dict[CoreValue, tuple[str, ...]] = Field(
        default=VALUE_WORDS,
        description="Words a topic touching each value has, or begins with.",
    )
    inspiration_cap: float = Field(
        default=0.35, ge=0, description="The most inspiration one memory adds."
    )
    inspiration_hourly: float = Field(
        default=0.4,
        ge=0,
        description="The most inspiration new memories add in any sim hour, so a busy day "
        "doesn't flood the village with works.",
    )
    start_needs: dict[Need, tuple[float, float]] = Field(
        default={
            Need.SOCIAL: (0.3, 0.8),
            Need.CURIOSITY: (0.2, 0.5),
            Need.REST: (0.0, 0.15),
            Need.NEWS: (0.1, 0.6),
            Need.INSPIRATION: (0.0, 0.8),
            Need.HUNGER: (0.2, 0.6),
            Need.BOREDOM: (0.0, 0.2),
            Need.RELAXATION: (0.1, 0.5),
            Need.EXERCISE: (0.1, 0.5),
        },
        description="Needs on start, sampled uniformly. Inspiration starts at 0 without a craft, "
        "and finances follow from their money.",
    )

    savings: float = Field(
        default=300.0,
        gt=0,
        description="An average resident's savings target, in money. `finances` is how far "
        "below it they are, as a share of it.",
    )
    savings_values: dict[CoreValue, float] = Field(
        default={V.SECURITY: 1.0},
        description="The target grows by this share per unit of `value - 0.5`.",
    )
    thrift_values: dict[CoreValue, float] = Field(
        default={V.PLEASURE: -1.0},
        description="A price feels this much bigger per unit of `value - 0.5`, so Pleasure "
        "spends more freely.",
    )
    shift_weight: float = Field(
        default=2.0,
        ge=0,
        description="Bonus for work from when they set off for a shift until it ends. Less than "
        "an urgent meal is worth, so an urgent need still wins.",
    )
    overtime_values: dict[CoreValue, float] = Field(
        default={V.AMBITION: 1.5, V.SUCCESS: 1.0},
        description="Score for staying on at work after a shift, per unit of `value - 0.5`.",
    )
    punctuality: float = Field(
        default=15.0,
        ge=0,
        description="Minutes early they set off for a shift at Discipline 1, and late at 0.",
    )
    set_off_jitter: float = Field(
        default=5.0, ge=0, description="Minutes either way they set off, at random."
    )
    ready: float = Field(
        default=45.0,
        ge=0,
        description="Minutes before they set off for a shift that it gets them up, so there's "
        "time for breakfast.",
    )
    skip: float = Field(
        default=0.3,
        ge=0,
        le=1,
        description="Chance of skipping a working day's shifts at Responsibility 0, falling to "
        "nothing at `skip_below`, and less the shorter of money they are.",
    )
    skip_below: float = Field(
        default=0.5, gt=0, le=1, description="Responsibility from which nobody skips."
    )
    overtime: float = Field(
        default=2.0,
        ge=0,
        description="Hours after a shift a wage earner still at work can stay on, a stay of "
        "`dwell` at a time.",
    )

    promise_weight: float = Field(
        default=2.0,
        ge=0,
        description="Bonus for an option a resident said they'd take, from when it's due until "
        "it's done or expires, as for a shift. None while a need is past its critical level, so "
        "an urgent need still wins.",
    )
    reliability_values: dict[CoreValue, float] = Field(
        default={V.RESPONSIBILITY: 0.6, V.DISCIPLINE: 0.4},
        description="How reliable a resident is, 0 to 1: the mean of these values, so weighted.",
    )
    lapse: float = Field(
        default=0.3,
        ge=0,
        le=1,
        description="Chance a resident lets an intention slide when it falls due, at a "
        "reliability of 0, falling to nothing at `reliable_from`.",
    )
    reliable_from: float = Field(
        default=0.5, gt=0, le=1, description="Reliability from which nobody lets one slide."
    )
    inspiration_start: float = Field(
        default=0.65,
        ge=0,
        le=1,
        description="The inspiration an intention to make something lifts them to once it's due, "
        "about where a crafter sets off to make something.",
    )
    keep_early: float = Field(
        default=60,
        ge=0,
        description="Minutes before it's due that doing what they said still keeps an intention.",
    )
    intentions: int = Field(
        default=3, ge=0, description="The most open intentions a resident takes on at once."
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

    @model_validator(mode="after")
    def _every_need_curved(self) -> Self:
        if missing := sorted(set(Need) - set(self.urgency)):
            raise ValueError(f"{', '.join(missing)} need an urgency curve")
        return self


DEFAULT_CONFIG = BehaviourConfig()
