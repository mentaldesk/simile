import asyncio
import json
import math
import shutil
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from simile.clinic.config import DEFAULT_CONFIG as CLINIC
from simile.economy import Kind
from simile.loop.maker import SHEET, SPOOL, Made
from simile.loop.playthrough import FEET, LEGS, Result, play
from simile.loop.serve import create_loop_app
from simile.npc import load_npcs
from simile.schema import Bionic, CreatureKind, ItemKind
from simile.social.bionics import tolerance
from simile.social.config import DEFAULT_BIONICS
from simile.story.disappearance import GONE, HATCH_LOG, LIFT_LOG, NOTED
from simile.street.sewers import DEN_BEDROLL, PRINTER_CRATES
from simile.world.paths import Spot

BEATS = (
    "kidney",
    "cell",
    "datajack",
    "legs",
    "gate",
    "hatch",
    "feet",
    "printer",
    "dog",
    "bot",
    "stash",
    "death",
    "salvage",
    "refit",
    "recycle",
)
NPCS = {npc.id: npc for npc in load_npcs()}


@pytest.fixture(scope="module")
def saves(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("saves")


@pytest.fixture(scope="module")
def result(saves: Path) -> Result:
    with pytest.MonkeyPatch.context() as env:
        env.setenv("SIMILE_LLM", "fake")
        env.setenv("SIMILE_NEWS", "0")
        env.setenv("SIMILE_DB", ":memory:")
        return asyncio.run(play(saves=saves))


def test_a_kidney_and_what_the_tunnels_pay_buy_the_cell_datajack_legs_and_feet(
    result: Result,
) -> None:
    body = result.player.body

    assert (body.left_kidney, body.right_kidney) == ("sold", "present")
    assert (body.stomach, body.vertebra, body.legs, body.feet) == (
        Bionic.POWER_CELL,
        Bionic.DATAJACK,
        Bionic.BIONIC_LEGS,
        Bionic.SPRING_FEET,
    )
    assert set(result.earned) == {Kind.SALVAGE, Kind.FOUND, Kind.PURCHASE}
    assert result.earned[Kind.PURCHASE] == -(100 + 100 + 150 + 150)
    assert result.earned[Kind.FOUND] >= 25 + 40 + 60
    assert sum(result.earned.values()) == pytest.approx(result.player.money)


def test_every_recipe_is_learned_and_every_part_found_in_the_world(result: Result) -> None:
    searched = set(result.player.searched)

    assert {Bionic.POWER_CELL, Bionic.DATAJACK, Bionic.BIONIC_LEGS, Bionic.SPRING_FEET} <= set(
        result.player.mind.recipes
    )
    assert {"maker_space_bench", "maker_space_spares", "maker_space_shelf"} <= searched
    assert {"metro_ticket_machine", "metro_fridge", *LEGS, *FEET} <= searched


def test_every_danger_is_met_and_passed_unhurt_with_the_lamp_off_by_the_bats(
    result: Result,
) -> None:
    assert result.stomped >= 3
    assert result.leapt >= 1
    assert result.lamp_off_by_bats >= 1
    assert result.hurt == []
    assert result.roused == set()
    assert result.dark == []


def test_the_journal_fills_in_with_what_was_found(result: Result) -> None:
    found = {entry.fact_id: entry for entry in result.journal}

    assert {LIFT_LOG, HATCH_LOG, NOTED} <= set(found)
    assert all(found[clue].flushed is None for clue in (LIFT_LOG, HATCH_LOG, NOTED))
    assert found.get(GONE) is None or found[GONE].flushed is False


def test_residents_remember_the_bionics_and_one_against_them_turns_the_player_down(
    result: Result,
) -> None:
    assert result.refused_by in result.seen_by
    assert tolerance(NPCS[result.refused_by].values) <= -DEFAULT_BIONICS.mildly
    assert all(sightings for sightings in result.seen_by.values())


def test_each_of_the_browsers_beats_has_a_save(saves: Path, result: Result) -> None:
    for beat in BEATS:
        info = json.loads((saves / f"{beat}.json").read_text())
        assert (saves / f"{beat}.db").stat().st_size > 0
        assert set(info["at"]) == {"map", "x", "y"}
    gap = json.loads((saves / "gate.json").read_text())["gap"]
    assert gap["to"] - gap["from"] >= 5


def made(result: Result) -> Made:
    assert result.made is not None
    return result.made


def test_the_printer_and_the_recycler_are_repaired_from_what_the_world_holds(
    result: Result,
) -> None:
    player = made(result).player

    assert player.repaired == ["printer_3d", "recycler"]
    assert {SHEET, PRINTER_CRATES, SPOOL, DEN_BEDROLL} <= set(player.searched)


def test_the_pistol_puts_down_rats_a_dog_and_a_bot_whose_haul_they_take(result: Result) -> None:
    stage = made(result)

    assert stage.shot[CreatureKind.RAT] >= 2
    assert stage.shot[CreatureKind.DOG] >= 1
    assert stage.shot[CreatureKind.BOT] >= 1
    assert stage.haul


def test_they_die_once_on_purpose_and_salvage_every_bionic_from_their_body(
    result: Result,
) -> None:
    stage = made(result)
    before, after = result.player.body, stage.player.body

    assert len(stage.died) == 1
    assert stage.hurt == []
    assert set(stage.corpse.bionics) == set(before.bionics)
    assert stage.corpse.money == result.player.money
    assert not any(item.kind is ItemKind.WEAPON for item in stage.corpse.items)
    assert stage.player.corpses == []
    assert set(stage.refitted) == set(before.bionics)
    assert set(after.bionics) == set(before.bionics)
    assert (after.left_kidney, after.right_kidney) == ("present", "present")
    assert stage.earned[Kind.RECOVERED] == -stage.earned[Kind.DROPPED] == stage.corpse.money
    fees = sum(math.ceil(CLINIC.recipes[b].credits * CLINIC.refit) for b in stage.refitted)
    assert result.earned[Kind.PURCHASE] - stage.earned[Kind.PURCHASE] == fees


def test_scrap_off_their_body_is_pressed_and_printed_into_rounds_with_the_stashed_pistol(
    result: Result,
) -> None:
    player = made(result).player
    [pistol] = [item for item in player.items if item.kind is ItemKind.WEAPON]

    assert pistol.rounds == pistol.capacity
    assert player.stash.items == []
    assert sum(made(result).earned.values()) == pytest.approx(player.money)


def test_a_beats_server_starts_the_player_where_it_was_saved_among_the_creatures(
    saves: Path, result: Result, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    at = json.loads((saves / "gate.json").read_text())["at"]
    monkeypatch.setenv("SIMILE_DB", str(shutil.copy(saves / "gate.db", tmp_path)))

    app = create_loop_app(Spot(at["map"], at["x"], at["y"]))
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        snapshot = ws.receive_json()

    [player] = [entity for entity in snapshot["entities"] if entity["kind"] == "player"]
    assert player["position"] == {"x": at["x"], "y": at["y"], "map": at["map"]}
    assert any(creature["position"]["map"] == at["map"] for creature in snapshot["creatures"])
