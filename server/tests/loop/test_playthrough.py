import asyncio
import json
import shutil
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from simile.economy import Kind
from simile.loop.playthrough import FEET, LEGS, Result, play
from simile.loop.serve import create_loop_app
from simile.npc import load_npcs
from simile.schema import Bionic
from simile.social.bionics import tolerance
from simile.social.config import DEFAULT_BIONICS
from simile.story.disappearance import GONE, HATCH_LOG, LIFT_LOG, NOTED
from simile.world.paths import Spot

BEATS = ("kidney", "cell", "datajack", "legs", "gate", "hatch", "feet")
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
