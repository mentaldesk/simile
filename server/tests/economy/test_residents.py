from simile.behaviour.scoring import bedtime
from simile.cafe.cafe import barista
from simile.npc import load_npcs
from simile.npc.content import NPCS_DIR
from simile.schema import LocationKind, PayKind, Weekday
from simile.world.map import load_maps

NPCS = {npc.id: npc for npc in load_npcs(NPCS_DIR)}
LOCATIONS = {loc.id: loc for town in load_maps().values() for loc in town.locations}


def test_the_residents_work_where_the_issue_says() -> None:
    mirela, tobias = NPCS["mirela"], NPCS["tobias"]

    assert mirela.workplace == "coffee_shop"
    assert mirela.pay is not None and mirela.pay.kind is PayKind.TAKINGS
    assert [(s.days, s.start, s.end) for s in mirela.shifts] == [(list(Weekday), 7, 17)]
    assert NPCS["odalys"].workplace == "noodle_bar"
    assert NPCS["ingrid"].workplace == "maker_space"
    assert NPCS["lachlan"].workplace == "park"
    assert NPCS["marguerite"].workplace == NPCS["marguerite"].home
    assert (tobias.workplace, tobias.shifts) == (None, [])
    assert tobias.pay is not None and tobias.pay.kind is PayKind.PENSION


def test_everyone_has_an_income_some_money_and_somewhere_real_to_work() -> None:
    for npc in NPCS.values():
        assert npc.pay is not None and npc.money > 0, npc.id
        if npc.workplace is not None:
            assert npc.workplace in LOCATIONS, npc.id
            kind = LOCATIONS[npc.workplace].kind
            assert npc.workplace == npc.home or kind is not LocationKind.HOUSE, npc.id


def test_every_shift_ends_before_bedtime() -> None:
    for npc in NPCS.values():
        for shift in npc.shifts:
            assert shift.end <= bedtime(npc.values), npc.id


def test_mirela_is_still_the_cafes_barista_and_the_shops_have_keepers() -> None:
    keepers = {
        npc.workplace: npc.id
        for npc in NPCS.values()
        if npc.pay is not None and npc.pay.kind is PayKind.TAKINGS
    }

    assert barista(NPCS.values(), "coffee_shop") == "mirela"
    assert keepers == {"coffee_shop": "mirela", "noodle_bar": "odalys"}
