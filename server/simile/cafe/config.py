from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from simile.llm import Model
from simile.schema import CoreValue, MapTile

V = CoreValue


class Layout(BaseModel):
    """Where the Daily Grind's fixed tiles are, on one world's maps."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entrance: MapTile = Field(description="Just inside the door, where customers head first.")
    machine: MapTile = Field(description="Where the barista makes drinks.")
    hand_over: MapTile = Field(description="Where the barista hands drinks across the counter.")
    pickup: MapTile = Field(description="Where customers wait for their drink.")
    upstairs: MapTile = Field(
        description="The foot of the stairs to the barista's flat, where they rest and sleep."
    )
    seats: list[MapTile] = Field(description="Beside the tables.")


def _on(map_id: str, *cells: tuple[int, int]) -> list[MapTile]:
    return [MapTile(map=map_id, x=x, y=y) for x, y in cells]


LAYOUTS = {
    "coffee_shop_floor_0": Layout(
        entrance=MapTile(map="coffee_shop_floor_0", x=17, y=2),
        machine=MapTile(map="coffee_shop_floor_0", x=2, y=2),
        hand_over=MapTile(map="coffee_shop_floor_0", x=4, y=2),
        pickup=MapTile(map="coffee_shop_floor_0", x=5, y=2),
        upstairs=MapTile(map="coffee_shop_floor_0", x=15, y=2),
        seats=_on(
            "coffee_shop_floor_1", *((x, 2) for x in (*range(5, 11), *range(12, 18), 1, 2, 3, 4))
        ),
    ),
}
"""By the map the café's location is on: its ground floor, whose tables are upstairs."""


class Nudge(BaseModel):
    """An interaction event the café makes in code: how it lands with whoever it's done to."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    valence: float = Field(ge=-1, le=1)
    magnitude: float = Field(ge=0, le=1)


class CafeConfig(BaseModel):
    """Every constant of the Daily Grind. Times are in sim seconds unless they say otherwise."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    home: str = Field(
        default="coffee_shop",
        description="The café's location. Whoever lives there is its barista.",
    )
    staff: str = Field(
        default="coffee_shop_staff", description="Behind the counter. Its entry is the till."
    )
    queue: str = Field(
        default="coffee_shop_queue",
        description="The lane in front of the till. The queue starts at its entry and runs on "
        "down it.",
    )
    counter: str = Field(
        default="coffee_shop_counter",
        description="The interactable whose stand tile is the front of the queue.",
    )
    opens: float = Field(
        default=7.0,
        ge=0,
        description="When the barista's shift starts. 07:00, half an hour after residents start "
        "wanting coffee and before most of them are up.",
    )
    closes: float = Field(
        default=17.0,
        le=24,
        description="Last orders, when residents stop wanting coffee. The queue is still served.",
    )
    layouts: dict[str, Layout] = Field(
        default=LAYOUTS,
        description="Where its fixed tiles are, by the map its location is on.",
    )
    model: str = Field(
        default=Model.HAIKU_4_5,
        description="Writes the barista's side of an order. Haiku 4.5, which doesn't think first, "
        "as for B5's replies.",
    )
    usual: float = Field(
        default=0.75, ge=0, le=1, description="Chance a resident orders the drink they lean to."
    )
    regular: float = Field(
        default=0.3,
        ge=0,
        le=1,
        description="Familiarity from which the barista offers a resident their usual.",
    )
    again: float = Field(
        default=90,
        ge=0,
        description="Minutes after being served before a resident queues again. Until then a "
        "visit is a sit down.",
    )
    sit: float = Field(
        default=0.5, description="Chance of sitting down with the drink, before values."
    )
    sit_values: dict[CoreValue, float] = Field(
        default={V.CONNECTION: 0.6, V.PLEASURE: 0.4, V.PEACE_OF_MIND: 0.3, V.AMBITION: -0.4},
        description="Added to `sit` per unit of `value - 0.5`.",
    )
    stay: tuple[float, float] = Field(
        default=(10, 30), description="Minutes sitting at a table, sampled uniformly."
    )
    mistake: float = Field(
        default=0.06, ge=0, le=1, description="Chance the barista makes the wrong drink."
    )
    slow: float = Field(
        default=300, gt=0, description="A wait from joining the queue longer than this is slow."
    )
    patience: float = Field(
        default=600, gt=0, description="How long a resident queues before giving up."
    )
    turn_gap: float = Field(default=0.6, ge=0, description="Between two lines of an order.")
    served: Nudge = Field(
        default=Nudge(valence=0.5, magnitude=0.15),
        description="How being served lands with the customer.",
    )
    serving: Nudge = Field(
        default=Nudge(valence=0.3, magnitude=0.1),
        description="How serving a resident lands with the barista.",
    )
    waited: Nudge = Field(
        default=Nudge(valence=-0.4, magnitude=0.15), description="A slow wait, for the customer."
    )
    wrong: Nudge = Field(
        default=Nudge(valence=-0.5, magnitude=0.2), description="The wrong drink, for the customer."
    )
    gave_up: Nudge = Field(
        default=Nudge(valence=-0.6, magnitude=0.25),
        description="Giving up on the queue, for the customer.",
    )
    salience: float = Field(
        default=0.15, ge=0, le=1, description="Of the customer's memory of an ordinary order."
    )

    @model_validator(mode="after")
    def _open_before_closing(self) -> Self:
        if self.opens >= self.closes:
            raise ValueError("the café must open before it closes")
        return self


DEFAULT_CONFIG = CafeConfig()
