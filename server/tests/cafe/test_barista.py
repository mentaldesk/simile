import asyncio
import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from simile.cafe.barista import HOME, JOB, OCCUPATION, BaristaDraft, brief, generate_barista
from simile.cli import create_cli
from simile.llm import FakeProvider, LLMClient
from simile.npc import NPCS_DIR, load_npcs
from simile.schema import Medium

REPO = Path(__file__).resolve().parents[3]
NPCS = load_npcs(NPCS_DIR)
VILLAGE = [npc for npc in NPCS if npc.home != HOME]


def draft(**changes: Any) -> BaristaDraft:
    fields: dict[str, Any] = {
        "name": "Ana Folau",
        "occupation": "Coffee person",
        "backstory": "Ana grew up by the sea. She moved here for the quiet.",
        "persona": "Ana is steady and kind. She notices who is missing.",
        "speaking_style": "Measured and warm.",
        "interests": ["tides", "bread", "local history"],
        "craft": {"medium": "writing", "form": "short notes on the counter"},
        "voice_description": "A woman in her forties. Low, warm voice, speaks slowly and evenly.",
        "reference_line": "I open the bakery at six and close when the bread runs out, most days.",
        "appearance": {
            "skin": "#c28569",
            "hair_style": "bun",
            "hair_colour": "#3e2731",
            "top_colour": "#265c42",
            "bottom_colour": "#3a4466",
            "shoe_colour": "#733e39",
            "build": "average",
            "accessories": ["apron"],
        },
    }
    return BaristaDraft.model_validate(fields | changes)


def test_the_brief_lives_above_the_cafe_with_values_unlike_the_village() -> None:
    first, again = brief(VILLAGE, seed=0), brief(VILLAGE, seed=0)

    assert first == again
    assert first.home == HOME
    assert 19 <= first.age <= 60
    assert first.values != brief(VILLAGE, seed=1).values


def test_the_barista_is_written_with_n1s_prompt_and_their_job() -> None:
    provider = FakeProvider([draft()])

    npc = asyncio.run(generate_barista(LLMClient(provider), VILLAGE, seed=0))

    assert (npc.home, npc.occupation, npc.id) == (HOME, OCCUPATION, "ana")
    prompt = provider.requests[0].messages[-1].content
    assert prompt.endswith(JOB) and f"Create resident {len(VILLAGE) + 1}" in prompt


def test_a_barista_who_paints_murals_is_asked_for_again() -> None:
    mural = draft().model_dump(mode="json") | {"craft": {"medium": "mural", "form": "big murals"}}
    provider = FakeProvider([json.dumps(mural), draft()])

    npc = asyncio.run(generate_barista(LLMClient(provider), VILLAGE, seed=0))

    assert npc.craft is not None and npc.craft.medium is Medium.WRITING
    assert len(provider.requests) == 2


def test_the_command_refuses_a_second_barista(tmp_path: Path) -> None:
    (tmp_path / "bea.json").write_text(
        NPCS[0].model_copy(update={"id": "bea", "home": HOME}).model_dump_json()
    )

    result = CliRunner().invoke(create_cli(), ["cafe", "barista", "--dir", str(tmp_path)])

    assert result.exit_code != 0
    assert "already lives above the café" in result.output


def test_the_committed_barista_lives_above_the_cafe_with_their_own_voice_and_doll() -> None:
    [barista] = [npc for npc in NPCS if npc.home == HOME]

    assert barista.occupation == OCCUPATION
    assert barista.craft is None or barista.craft.medium is Medium.WRITING
    assert barista.voice.reference_clip == f"content/voices/{barista.id}.wav"
    assert (REPO / barista.voice.reference_clip).exists()
    assert (REPO / "content" / "voices" / f"{barista.id}.txt").read_text().strip() == (
        barista.voice.reference_line
    )
    assert (REPO / "content" / "dolls" / f"{barista.id}.json").exists()
