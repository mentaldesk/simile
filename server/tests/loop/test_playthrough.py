import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from simile.economy import Kind
from simile.loop.playthrough import QUESTION, Result, play
from simile.loop.serve import create_loop_app
from simile.npc import load_npcs
from simile.schema import Bionic
from simile.social.bionics import tolerance
from simile.social.config import DEFAULT_BIONICS
from simile.story import says
from simile.story.incident import GONE, HATCH_LOG, LIFT_LOG, NOTED, there
from simile.world.paths import Spot

BEATS = ("kidney", "datajack", "hatch", "eye")
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


def test_a_kidney_and_what_the_tunnels_pay_buy_every_bionic(result: Result) -> None:
    body = result.player.body

    assert (body.left_kidney, body.right_kidney) == ("sold", "present")
    assert (body.legs, body.vertebra, body.left_eye) == (
        Bionic.HYDRAULIC_LEGS,
        Bionic.DATAJACK,
        Bionic.INFRARED_EYE,
    )
    assert set(result.earned) == {Kind.SALVAGE, Kind.FOUND, Kind.PURCHASE}
    assert result.earned[Kind.PURCHASE] == -(80 + 150 + 200)
    assert result.earned[Kind.FOUND] >= 25 + 40 + 60
    assert sum(result.earned.values()) == pytest.approx(result.player.money)


def test_the_eye_waits_for_days_of_salvage_rounds(result: Result) -> None:
    assert 1 < result.days < 7
    assert result.played < result.end - result.start
    assert sum("Came back to the game" in note for note in result.notes) >= 1


def test_an_attackers_alibi_flushes_and_the_journal_records_it(result: Result) -> None:
    lie = next(entry for entry in result.journal if entry.fact_id == there(result.attacker))

    assert result.lie.flushed and result.lie.line.speaker == result.attacker
    assert lie.flushed is True
    assert says(lie.text, result.lie.line.text)


def test_the_journal_fills_in_with_what_was_found_and_told(result: Result) -> None:
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
    eye = json.loads((saves / "eye.json").read_text())
    assert eye["attacker"]["id"] == result.attacker
    assert says(result.lie.line.text, eye["alibi"])


def test_the_eye_beats_server_starts_the_player_there_and_flushes_the_alibi(
    saves: Path, result: Result, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    eye = json.loads((saves / "eye.json").read_text())
    monkeypatch.setenv("SIMILE_DB", str(shutil.copy(saves / "eye.db", tmp_path)))
    at, attacker = eye["at"], eye["attacker"]["id"]

    app = create_loop_app(Spot(at["map"], at["x"], at["y"]))
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        snapshot = ws.receive_json()
        [player] = [entity for entity in snapshot["entities"] if entity["kind"] == "player"]
        ws.send_json({"type": "player_move", "position": player["position"]})
        ws.send_json({"type": "player_say", "text": QUESTION, "target": attacker})
        line = next_line(ws, attacker)

    assert player["position"] == {"x": at["x"], "y": at["y"], "map": at["map"]}
    assert line["flushed"] is True
    assert says(line["line"]["text"], eye["alibi"])


def next_line(ws: Any, speaker: str) -> dict[str, Any]:
    for _ in range(5000):
        message = ws.receive_json()
        if message["type"] == "line" and message["line"]["speaker"] == speaker:
            return message
    raise AssertionError(f"no line from {speaker}")
