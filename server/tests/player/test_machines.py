import pytest

from simile.player.machines import Machines
from simile.schema import PLAYER_ID, Bionic, Body, Interactable, Player
from simile.sim import EventBus
from simile.street.metro import DEAD_TERMINAL, LIFT
from simile.world import Movement, Point
from simile.world.map import load_maps

MAPS = load_maps()
DATAJACK = Body(vertebra=Bionic.DATAJACK)


def used(body: Body, at: Point) -> list[str]:
    """The jacks E uses at `at`."""
    movement = Movement(MAPS, EventBus())
    movement.track(PLAYER_ID, at)
    found: list[Interactable] = []
    claim = Machines(Player(body=body), movement, found.append).claim(at)
    if claim is not None:
        assert claim.distance == 0
        claim.take()
    return [jack.id for jack in found]


@pytest.mark.parametrize(
    ("at", "jack"),
    [(Point(104, 15, "metro"), DEAD_TERMINAL), (Point(100.2, 15, "metro"), LIFT)],
    ids=["the dead terminal", "the lift"],
)
def test_a_jack_works_only_with_the_datajack(at: Point, jack: str) -> None:
    assert used(DATAJACK, at) == [jack]
    assert used(Body(), at) == []
    assert used(Body(legs=Bionic.HYDRAULIC_LEGS, left_eye=Bionic.INFRARED_EYE), at) == []


@pytest.mark.parametrize(
    "at",
    [Point(103, 15, "metro"), Point(101, 15, "metro"), Point(72, 15, "metro"), Point(2, 15, "x")],
    ids=["beside the terminal", "the lift's far side", "the plug", "an unknown map"],
)
def test_a_jack_works_only_from_its_stand_tile(at: Point) -> None:
    assert used(DATAJACK, at) == []
