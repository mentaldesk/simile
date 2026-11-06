import importlib
import logging
import pkgutil
from collections import Counter
from collections.abc import Callable
from typing import NamedTuple

from simile.player.where import here
from simile.schema import Id, Interactable, Machine, MachineKind, MachineState, Player, Product
from simile.world.movement import Movement, cell_of

logger = logging.getLogger(__name__)


class Broken(NamedTuple):
    """A machine as it stands until it's repaired, and the parts repairing it uses up."""

    kind: MachineKind
    parts: dict[str, int]


MACHINES: dict[Id, Broken] = {
    "printer_3d": Broken(
        MachineKind.PRINTER, {"metal_sheet": 1, "linear_actuator": 1, "copper_wire": 2}
    ),
    "recycler": Broken(MachineKind.RECYCLER, {"apex_board": 1, "old_battery": 2}),
}
"""Every machine you repair, by its interactable's id."""


class Offer(NamedTuple):
    """Something a working machine offers: the `product` it lists, and `make`, which takes what it
    uses from the player and gives them what comes out, or returns False and changes nothing."""

    product: Product
    make: Callable[[Player], bool]


class Workshop:
    """The machines you repair and then use, each built afresh from `Player.repaired`."""

    def __init__(
        self,
        player: Player,
        movement: Movement,
        changed: Callable[[Machine], object] = lambda machine: None,
        machines: dict[Id, Broken] = MACHINES,
    ) -> None:
        self.player = player
        self.movement = movement
        self.changed = changed
        self.broken = machines
        self.offers: dict[Id, list[Offer]] = {}

    def offer(self, machine: Id, *offers: Offer) -> None:
        """Adds to what `machine` lists once it works. A module's `register` calls this."""
        if machine not in self.broken:
            raise KeyError(machine)
        self.offers[machine] = [*self.offers.get(machine, []), *offers]

    def machine(self, machine: Id) -> Machine:
        broken = self.broken[machine]
        if machine in self.player.repaired:
            makes = [offer.product for offer in self.offers.get(machine, [])]
            return Machine(id=machine, kind=broken.kind, state=MachineState.WORKING, makes=makes)
        return Machine(id=machine, kind=broken.kind, state=MachineState.BROKEN, parts=broken.parts)

    def machines(self) -> list[Machine]:
        return [self.machine(machine) for machine in self.broken]

    def missing(self, machine: Id) -> dict[str, int]:
        """How many of each part repairing it uses up they're short of."""
        carried = Counter(item.id for item in self.player.items)
        parts = self.broken[machine].parts
        return {id: n - carried[id] for id, n in parts.items() if carried[id] < n}

    def repair(self, machine: Id) -> bool:
        """Repairs `machine` where they stand at it, using up its parts, if it's broken and they
        have them all. Whether it did."""
        if machine not in self.broken or machine in self.player.repaired:
            return False
        if not self._at(machine) or self.missing(machine):
            return False
        left = dict(self.broken[machine].parts)
        items = []
        for item in self.player.items:
            if left.get(item.id, 0) > 0:
                left[item.id] -= 1
            else:
                items.append(item)
        self.player.items = items
        self.player.repaired = [*self.player.repaired, machine]
        logger.info("The player repairs %s", machine)
        self.changed(self.machine(machine))
        return True

    def make(self, machine: Id, item: Id) -> bool:
        """Makes what `machine` offers of `item` where they stand at it, if it works. Whether it
        did."""
        if machine not in self.player.repaired or not self._at(machine):
            return False
        offers = self.offers.get(machine, [])
        offer = next((offer for offer in offers if offer.product.item.id == item), None)
        return offer is not None and offer.make(self.player)

    def _at(self, machine: Id) -> bool:
        at, stands = here(self.movement), self._interactable(machine)
        if at is None or stands is None or at.map != stands.map:
            return False
        return cell_of(at) in {(tile.x, tile.y) for tile in stands.stand}

    def _interactable(self, machine: Id) -> Interactable | None:
        items = (item for town in self.movement.maps.values() for item in town.interactables)
        return next((item for item in items if item.id == machine), None)


def register_offers(workshop: Workshop, package: str = __package__) -> None:
    """Calls `register(workshop)` in each module beside this one that has it, so a machine's
    offers are added by a new file here."""
    path = importlib.import_module(package).__path__
    for found in pkgutil.iter_modules(path):
        module = importlib.import_module(f"{package}.{found.name}")
        if (register := getattr(module, "register", None)) is not None:
            register(workshop)
