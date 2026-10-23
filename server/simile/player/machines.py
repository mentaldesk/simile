from collections.abc import Callable, Collection

from simile.player.pickups import Claim
from simile.schema import Bionic, Id, Interactable, InteractableKind, Player
from simile.world.movement import Movement, Point, cell_of


class Machines:
    """The jacks holding a clue, which `pick_up` finds only with the datajack fitted."""

    def __init__(
        self,
        player: Player,
        movement: Movement,
        found: Callable[[Interactable], object],
        clues: Callable[[], Collection[Id]],
    ) -> None:
        self.player = player
        self.movement = movement
        self.found = found
        self.clues = clues

    def claim(self, here: Point) -> Claim | None:
        if Bionic.DATAJACK not in self.player.body.bionics:
            return None
        jack = self.jack(here)
        if jack is None or jack.id not in self.clues():
            return None
        return Claim(0.0, lambda: self.found(jack))

    def jack(self, here: Point) -> Interactable | None:
        """The jack whose stand tile `here` is on."""
        town = self.movement.maps.get(here.map)
        cell = cell_of(here)
        items = town.interactables if town is not None else []
        jacks = (item for item in items if item.kind is InteractableKind.JACK)
        return next((j for j in jacks if any((t.x, t.y) == cell for t in j.stand)), None)
