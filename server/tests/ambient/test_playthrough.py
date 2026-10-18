import asyncio
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from simile.ambient.playthrough import LINE, REFLECTION, WORDS, Delays, Padded, playthrough
from simile.cli import create_cli
from simile.conversation import parse_reply, system_prompt
from simile.conversation.player import DEFAULT_PLAYER_CONFIG, split
from simile.llm import LLMClient, Model
from simile.npc import load_npcs
from simile.reflection import Extraction
from simile.reflection.extraction import SYSTEM as REFLECTING
from simile.sim import Clock, FakeWallClock, World

pytestmark = pytest.mark.anyio

NPCS = load_npcs()
runner = CliRunner()


class Writer:
    """The padded fake LLM on a world whose loop runs only while a test waits for a reply."""

    def __init__(self) -> None:
        self.world = World(Clock(datetime(2026, 1, 1, 10, tzinfo=UTC)), FakeWallClock())
        self.delays = Delays(self.world.clock)
        self.world.loop.register(self.delays)
        self.llm = LLMClient(Padded(NPCS, self.delays, random.Random(0)))

    async def ask(self, system: str, model: str = Model.HAIKU_5_5) -> tuple[str, float]:
        """The reply, and the sim seconds it took."""
        start = self.world.clock.now
        task = asyncio.create_task(self.llm.complete("Hello", system=system, model=model))
        while not task.done():
            await self.world.loop.run(timedelta(seconds=0.1))
        return task.result(), (self.world.clock.now - start).total_seconds()


async def test_lines_are_as_long_as_claudes_take_as_long_and_touch_the_speakers_values() -> None:
    writer, npc = Writer(), NPCS[0]
    top = sorted(npc.values, key=lambda value: -npc.values[value])[:5]

    drafts = []
    for _ in range(40):
        text, seconds = await writer.ask(system_prompt(npc))
        drafts.append(parse_reply(text, [npc.name], []))
        assert seconds == pytest.approx(LINE, abs=0.11)

    assert all(len(draft.text.split()) == WORDS for draft in drafts)
    values = [value for draft in drafts for value in draft.values]
    assert len(values) == 80
    assert 0.4 < sum(value in top for value in values) / len(values) < 0.85


async def test_replies_to_the_player_come_in_two_sentences() -> None:
    writer, npc = Writer(), NPCS[1]

    text, _ = await writer.ask(system_prompt(npc), DEFAULT_PLAYER_CONFIG.model)

    assert len(split(parse_reply(text, [npc.name], []).text)) == 2


async def test_reflections_are_valid_and_store_nothing() -> None:
    writer = Writer()
    start = writer.world.clock.now
    task = asyncio.create_task(
        writer.llm.structured("A conversation", Extraction, system=REFLECTING)
    )
    while not task.done():
        await writer.world.loop.run(timedelta(seconds=0.1))

    assert task.result() == Extraction(reflections=[])
    assert (writer.world.clock.now - start).total_seconds() == pytest.approx(REFLECTION, abs=0.11)


async def test_short_playthroughs_chat_and_overhear() -> None:
    results = [await playthrough(minutes=20, warmup=5, seed=seed) for seed in range(3)]

    assert all(r.minutes == 20 and r.player_conversations for r in results)
    assert all(r.calls["player-reply"] for r in results)
    assert sum(r.nudges for r in results) and sum(r.calls["conversation"] for r in results)
    assert sum(len(r.overheard) for r in results) >= 2
    assert sum(r.heard for r in results) > 0
    assert all(r.heard < 600 for r in results)
    assert all(r.inside and r.seen_inside for r in results)


async def test_the_village_is_kept_in_memory_whatever_simile_db_says(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "simile.db"
    monkeypatch.setenv("SIMILE_DB", str(db))
    databases: list[Path] = []

    await playthrough(
        minutes=1, warmup=1, prepare=lambda app: databases.append(app.state.memory.path)
    )

    assert databases == [Path(":memory:")]
    assert not db.exists()


def test_cli_prints_the_table() -> None:
    result = runner.invoke(
        create_cli(), ["ambient", "playthrough", "--runs", "1", "--minutes", "3", "--warmup", "1"]
    )

    assert result.exit_code == 0, result.output
    assert "1 runs of 3 sim minutes after 1 minutes' warm-up." in result.output
    assert "| NPC conversation in earshot, share of the time |" in result.output
    assert "| Residents seen inside |" in result.output
