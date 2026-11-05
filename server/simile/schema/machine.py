from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from simile.schema.common import Id, Key, Model
from simile.schema.player import Item, Material


class MachineKind(StrEnum):
    """What a machine in the maker space is: Aris's 3D `printer`, or the `recycler`."""

    PRINTER = "printer"
    RECYCLER = "recycler"


class MachineState(StrEnum):
    """Whether it needs repairing first."""

    BROKEN = "broken"
    WORKING = "working"


class Product(Model):
    """Something a working machine makes: the `item` that comes out, stack and all, such as 6
    rounds, and what it takes."""

    item: Item
    uses: Material | Literal["scrap"] = Field(
        description="What it's made from: a material they carry, or scrap, by weight."
    )
    cost: float = Field(
        gt=0,
        allow_inf_nan=False,
        description="How much of it: a material's amount, or kilos of scrap.",
    )


class Machine(Model):
    """The state of a machine you repair and then use. Where it stands and what it's called are
    on the map, in the `Interactable` with the same `id`."""

    id: Id = Field(description='Its interactable\'s id, e.g. "printer_3d".')
    kind: MachineKind
    state: MachineState
    parts: dict[Key, Annotated[int, Field(ge=1)]] = Field(
        default={},
        description="What repairing it uses up while it's broken, how many of each by item `id`, "
        'e.g. `{"copper_wire": 2}`. Empty once it works.',
    )
    makes: list[Product] = Field(
        default=[],
        description="What it can make while it works, whether or not they have what it takes, "
        "each item once. Empty while it's broken, and it can be empty while it works.",
    )

    @model_validator(mode="after")
    def _parts_while_broken_products_once_it_works(self) -> Self:
        if self.state is MachineState.BROKEN and (not self.parts or self.makes):
            raise ValueError("a broken machine needs parts and makes nothing")
        if self.state is MachineState.WORKING and self.parts:
            raise ValueError("a working machine needs no parts")
        items = [product.item.id for product in self.makes]
        if len(set(items)) != len(items):
            raise ValueError("a machine makes each item once")
        return self
