from datetime import UTC, datetime

import pytest

from simile.behaviour import Behaviour
from simile.economy import OUTSIDE, Kind
from simile.economy.economy import Economy
from simile.economy.loans import transfer
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.schema import Npc
from simile.sim import Clock, FakeWallClock, World
from simile.world import Movement
from simile.world.map import load_maps

TEMPLATE = load_npcs()[0]


def resident(id: str, money: float) -> Npc:
    return TEMPLATE.model_copy(
        update={"id": id, "workplace": None, "shifts": [], "pay": None, "money": money}
    )


@pytest.fixture
def economy() -> Economy:
    world = World(Clock(datetime(2026, 1, 1, 12, tzinfo=UTC)), FakeWallClock())
    npcs = [resident("ana", 100.0), resident("ben", 50.0)]
    behaviour = Behaviour(
        world.clock, world.bus, Movement(load_maps(), world.bus), npcs, MemoryStore(":memory:")
    )
    return Economy(world.clock, behaviour)


def test_a_transfer_hands_money_over_through_the_ledger(economy: Economy) -> None:
    assert transfer(economy, "ana", "ben", 60, Kind.LOAN)

    assert economy.money == {"ana": 40, "ben": 110}
    [entry] = economy.ledger.entries
    assert (entry.kind, entry.payer, entry.payee, entry.amount) == (Kind.LOAN, "ana", "ben", 60)
    assert economy.ledger.gap(economy.money) == 0


@pytest.mark.parametrize(
    ("payer", "payee", "amount"),
    [
        pytest.param("ana", "ben", 101, id="more than the payer holds"),
        pytest.param("ana", "ben", 0, id="nothing"),
        pytest.param("ana", "ben", -10, id="a negative amount"),
        pytest.param("ana", "ben", float("nan"), id="not a number"),
        pytest.param("ana", "ben", float("inf"), id="infinite"),
        pytest.param("ana", "ana", 10, id="to themselves"),
        pytest.param("ana", OUTSIDE, 10, id="out of the village"),
        pytest.param(OUTSIDE, "ana", 10, id="into the village"),
        pytest.param("ana", "cal", 10, id="to someone who isn't a resident"),
    ],
)
def test_a_transfer_only_moves_money_a_resident_holds_to_another(
    economy: Economy, payer: str, payee: str, amount: float
) -> None:
    assert not transfer(economy, payer, payee, amount, Kind.LOAN)

    assert economy.money == {"ana": 100, "ben": 50}
    assert economy.ledger.entries == []
