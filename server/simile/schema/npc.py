from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Self

from pydantic import AfterValidator, Field, field_validator, model_validator

from simile.schema.common import PLAYER_ID, Colour, Id, Model, Unit


class CoreValue(StrEnum):
    FREEDOM = "freedom"
    INDEPENDENCE = "independence"
    SELF_RESPECT = "self_respect"
    SELF_ACTUALIZATION = "self_actualization"
    CREATIVITY = "creativity"
    HONESTY = "honesty"
    COMPASSION = "compassion"
    LOYALTY = "loyalty"
    JUSTICE = "justice"
    RESPONSIBILITY = "responsibility"
    SECURITY = "security"
    EQUALITY = "equality"
    TRADITION = "tradition"
    OBEDIENCE = "obedience"
    SUCCESS = "success"
    AMBITION = "ambition"
    DISCIPLINE = "discipline"
    KNOWLEDGE = "knowledge"
    OPEN_MINDEDNESS = "open_mindedness"
    PEACE_OF_MIND = "peace_of_mind"
    PLEASURE = "pleasure"
    CONNECTION = "connection"
    ADVENTURE = "adventure"
    OPTIMISM = "optimism"


def _every_value(values: dict[CoreValue, float]) -> dict[CoreValue, float]:
    if missing := [value.value for value in CoreValue if value not in values]:
        raise ValueError(f"missing core values: {', '.join(missing)}")
    return values


EveryValue = Annotated[dict[CoreValue, Unit], AfterValidator(_every_value)]

Mannerism = Annotated[str, Field(min_length=1, max_length=120)]
Mannerisms = Annotated[
    list[Mannerism],
    Field(
        max_length=3,
        exclude_if=lambda mannerisms: not mannerisms,
        description='Up to 3 habits that show in how they talk, e.g. "answers a question with '
        'another question". Left out when empty.',
    ),
]


class HumourStyle(StrEnum):
    DRY = "dry"
    DEADPAN = "deadpan"
    SARCASTIC = "sarcastic"
    CYNICAL = "cynical"
    PUNNING = "punning"
    SILLY = "silly"
    TEASING = "teasing"
    GALLOWS = "gallows"
    NONE = "none"


class Humour(Model):
    """Their sense of humour: its style, and how seldom they joke."""

    style: HumourStyle
    seriousness: Unit = Field(
        description="How seldom they joke, 0-1: at 0 they joke in most lines, at 1 never."
    )

    @model_validator(mode="after")
    def _none_never_jokes(self) -> Self:
        if self.style is HumourStyle.NONE and self.seriousness != 1:
            raise ValueError("someone with no humour never jokes, so their seriousness is 1")
        return self


class HairStyle(StrEnum):
    BALD = "bald"
    BUZZ = "buzz"
    SHORT = "short"
    CURLY = "curly"
    BOB = "bob"
    LONG = "long"
    PONYTAIL = "ponytail"
    BUN = "bun"


class Build(StrEnum):
    SLIM = "slim"
    AVERAGE = "average"
    BROAD = "broad"


class Accessory(StrEnum):
    GLASSES = "glasses"
    SUNGLASSES = "sunglasses"
    CAP = "cap"
    BEANIE = "beanie"
    HEADPHONES = "headphones"
    SCARF = "scarf"
    BACKPACK = "backpack"
    APRON = "apron"


class Appearance(Model):
    """What a character looks like, for the sprite generator. Colours are #rrggbb."""

    skin: Colour
    hair_style: HairStyle
    hair_colour: Colour
    top_colour: Colour
    bottom_colour: Colour
    shoe_colour: Colour
    build: Build
    accessories: list[Accessory] = []


class Voice(Model):
    description: str = Field(description="What the voice sounds like, for the voice design model.")
    reference_line: str = Field(
        description="A neutral line in character, 5-10 seconds of speech. The clip's transcript."
    )
    reference_clip: str | None = Field(
        default=None,
        description="The recorded reference clip, relative to the repository root. "
        "Null until the voice is designed.",
    )


class Medium(StrEnum):
    WRITING = "writing"
    MURAL = "mural"
    PAINTING = "painting"


class Craft(Model):
    """What a resident makes in their own time, which can differ from their job."""

    medium: Medium
    form: str = Field(
        min_length=1,
        description='What they make, in a few words, e.g. "short poems about the river".',
    )


class Weekday(StrEnum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"

    @classmethod
    def of(cls, when: datetime) -> "Weekday":
        return list(cls)[when.weekday()]


class Shift(Model):
    """When a resident works on some days of the week. Times are hours on the sim clock, so 7.5
    is 07:30. A shift that runs past midnight is two shifts: one ending at 24 and one starting at
    0 the next day."""

    days: list[Weekday] = Field(min_length=1)
    start: float = Field(ge=0, description="When it starts, 0-24.")
    end: float = Field(le=24, description="When it ends, after it starts and at most 24.")

    @field_validator("days")
    @classmethod
    def _each_day_once(cls, days: list[Weekday]) -> list[Weekday]:
        if len(set(days)) < len(days):
            raise ValueError("a shift names each day once")
        return days

    @model_validator(mode="after")
    def _ends_after_it_starts(self) -> Self:
        if self.end <= self.start:
            raise ValueError(
                f"a shift from {self.start:g} to {self.end:g} doesn't end after it starts: split "
                "one past midnight into one ending at 24 and one starting at 0 the next day"
            )
        return self

    def covers(self, when: datetime) -> bool:
        hour = (when - when.replace(hour=0, minute=0, second=0, microsecond=0)) / timedelta(hours=1)
        return Weekday.of(when) in self.days and self.start <= hour < self.end


def _apart(shifts: list[Shift]) -> list[Shift]:
    for index, a in enumerate(shifts):
        for b in shifts[index + 1 :]:
            if (days := set(a.days) & set(b.days)) and a.start < b.end and b.start < a.end:
                day = min(days, key=list(Weekday).index)
                raise ValueError(
                    f"shifts overlap on {day}: {a.start:g}-{a.end:g} and {b.start:g}-{b.end:g}"
                )
    return shifts


Shifts = Annotated[list[Shift], AfterValidator(_apart)]


class PayKind(StrEnum):
    """`wage`: `amount` per hour worked, for work done for people outside the village. `takings`:
    what their shop takes minus its supplies, so no `amount`. `pension`: `amount` per week."""

    WAGE = "wage"
    TAKINGS = "takings"
    PENSION = "pension"


class Pay(Model):
    """How a resident is paid, in the same units as their `money`."""

    kind: PayKind
    amount: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
        description="Per hour worked for a `wage`, per week for a `pension`, null for `takings`.",
    )

    @model_validator(mode="after")
    def _amount_fits_kind(self) -> Self:
        if self.kind is PayKind.TAKINGS and self.amount is not None:
            raise ValueError("takings are what the shop takes minus its supplies, so no amount")
        if self.kind is not PayKind.TAKINGS and self.amount is None:
            per = "hour worked" if self.kind is PayKind.WAGE else "week"
            raise ValueError(f"a {self.kind} needs an amount per {per}")
        return self


class Npc(Model):
    id: Id
    name: str
    age: int = Field(ge=0, le=120)
    occupation: str
    home: Id = Field(description="Location id of their house.")
    workplace: Id | None = Field(
        default=None,
        exclude_if=lambda workplace: workplace is None,
        description="Location id of where they work, their `home` for remote work. Null if they "
        "don't work, and left out.",
    )
    shifts: Shifts = Field(
        default=[],
        exclude_if=lambda shifts: not shifts,
        description="When they work, at their workplace. Empty if they don't work, and left out.",
    )
    pay: Pay | None = Field(
        default=None,
        exclude_if=lambda pay: pay is None,
        description="How they're paid. Null with no income, and left out.",
    )
    money: float = Field(
        default=0.0,
        ge=0,
        allow_inf_nan=False,
        exclude_if=lambda money: money == 0,
        description="What they start with. Left out when 0.",
    )
    values: EveryValue = Field(
        description="How much they care about each of the 24 core values, 0-1. All are present."
    )
    backstory: str
    persona: str
    speaking_style: str
    mannerisms: Mannerisms = []
    humour: Humour | None = Field(
        default=None,
        exclude_if=lambda humour: humour is None,
        description="Null when unset, and left out.",
    )
    interests: list[str]
    appearance: Appearance
    voice: Voice
    craft: Craft | None = Field(default=None, description="Null if they don't make anything.")

    @field_validator("id")
    @classmethod
    def _not_player(cls, id: str) -> str:
        if id == PLAYER_ID:
            raise ValueError(f"'{PLAYER_ID}' is reserved for the player")
        return id

    @model_validator(mode="after")
    def _work_fits(self) -> Self:
        if self.workplace is None and self.shifts:
            raise ValueError("shifts need a workplace")
        if self.workplace is not None and not self.shifts:
            raise ValueError("a workplace needs shifts")
        if self.pay and self.pay.kind is not PayKind.PENSION and self.workplace is None:
            raise ValueError(f"{self.pay.kind} pay needs a workplace")
        return self
