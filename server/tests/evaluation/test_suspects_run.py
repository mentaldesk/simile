import json
from pathlib import Path

import pytest

from simile.conversation.prompt import first_name
from simile.evaluation.fake import Stock
from simile.evaluation.suspects import cases, incident
from simile.evaluation.suspects_report import report
from simile.evaluation.suspects_run import BACKSTORIES, REPLIES, Comparison, compare
from simile.llm import FakeProvider, LLMClient, Provider, Request
from simile.llm.claude_code import ClaudeCodeProvider
from simile.llm.ollama import OllamaProvider
from simile.npc import load_npcs
from simile.npc.content import NPCS_DIR
from simile.schema import Npc
from simile.story.writing import SYSTEM as STORY
from simile.story.writing import Backstory, Written

pytestmark = pytest.mark.anyio

HAIKU, GEMMA, JUDGE = "claude-haiku-4-5", "ollama:gemma4:26b", "claude-haiku-5-5"
ALIBI = "I was in for the night, going over my figures."


class StandIn(FakeProvider):
    name = ClaudeCodeProvider.name


class Local(FakeProvider):
    name = OllamaProvider.name


class Split(LLMClient):
    def __init__(self, local: FakeProvider, claude: FakeProvider) -> None:
        super().__init__(claude)
        self.local = local

    def provider_for(self, model: str) -> Provider:
        return self.local if model.startswith("ollama:") else super().provider_for(model)


@pytest.fixture(scope="module")
def npcs() -> list[Npc]:
    return load_npcs(NPCS_DIR)


def written(request: Request) -> str:
    if request.system.startswith(STORY):
        side = Written(
            id="raymond",
            grievance="Raymond blamed Aris for a deal.",
            resents="She cost me a deal.",
            remembers="I went round to have it out with her.",
            alibi=ALIBI,
            deflection="I couldn't say.",
            denial="We got on fine.",
            note="R. again.",
        )
        return Backstory(motive="A deal.", attackers=[side]).model_dump_json()
    return Stock()(request)


def split() -> tuple[Split, FakeProvider, FakeProvider]:
    local, claude = Local(default=Stock()), StandIn(default=written)
    return Split(local, claude), local, claude


async def run(npcs: list[Npc], out: Path | None = None, *, write: bool = False) -> Comparison:
    llm, _, _ = split()
    return await compare(
        llm, npcs, models=[HAIKU, GEMMA], judge=JUDGE, seeds=[7], out=out, write=write
    )


async def test_each_model_voices_every_case_and_one_call_judges_each_way(
    npcs: list[Npc],
) -> None:
    llm, local, claude = split()

    result = await compare(llm, npcs, models=[HAIKU, GEMMA], judge=JUDGE, seeds=[7])

    every = cases(incident(npcs, 7), npcs, 7)
    assert [c.id for c in result.cases] == [c.id for c in every]
    assert len(result.replies) == 2 * len(every) and not result.missing
    assert {r.model for r in result.replies} == {HAIKU, GEMMA}
    assert len(local.requests) == len(every)
    assert result.calls == {HAIKU: len(every), JUDGE: 2}
    assert all(r.first_word is not None and r.seconds is not None for r in result.replies)
    assert all(r.tokens for r in result.replies)
    assert all(r.stance and r.breaks is not None for r in result.replies)
    assert all(r.in_character in (1, 2, 3, 4, 5) for r in result.replies)
    asked = [r.messages[-1].content for r in claude.requests if r.model == JUDGE]
    assert len(asked) == 2
    assert all(f"## {case.id}" in text for case in every for text in asked)


async def test_a_rerun_reuses_everything_and_calls_nothing(npcs: list[Npc], tmp_path: Path) -> None:
    first = await run(npcs, tmp_path)
    llm, local, claude = split()

    again = await compare(llm, npcs, models=[HAIKU, GEMMA], judge=JUDGE, seeds=[7], out=tmp_path)

    assert not local.requests and not claude.requests
    assert again.calls == first.calls
    assert {r.key for r in again.replies} == {r.key for r in first.replies}
    saved = json.loads((tmp_path / REPLIES).read_text(encoding="utf-8"))
    assert saved["calls"] == first.calls


async def test_replies_short_of_a_full_set_are_saved_but_not_judged(
    npcs: list[Npc], tmp_path: Path
) -> None:
    llm, local, claude = split()

    result = await compare(
        llm, npcs, models=[HAIKU, GEMMA], judge=JUDGE, seeds=[7], out=tmp_path, max_calls=3
    )

    assert result.missing == 2 * len(result.cases) - 3
    assert not local.requests
    assert all(r.model == HAIKU for r in claude.requests)
    assert all(r.stance is None for r in result.replies)
    saved = json.loads((tmp_path / REPLIES).read_text(encoding="utf-8"))
    assert len(saved["replies"]) == 3


async def test_with_write_sonnet_writes_the_covers_once(npcs: list[Npc], tmp_path: Path) -> None:
    result = await run(npcs, tmp_path, write=True)

    assert result.written == [7]
    assert result.calls["sonnet"] == 1
    assert any(case.cover == ALIBI for case in result.cases)
    assert (tmp_path / BACKSTORIES).exists()
    again = await run(npcs, tmp_path, write=True)
    assert again.calls["sonnet"] == 1


async def test_the_report_compares_the_models_and_lists_every_reply(npcs: list[Npc]) -> None:
    result = await run(npcs)

    text = report(result, [HAIKU, GEMMA], JUDGE, [first_name(npc) for npc in npcs])

    assert text.startswith("# Who voices the suspects\n")
    assert f"| | {HAIKU} | {GEMMA} |" in text
    for section in ("## Keeping to the cover", "## In character", "## Tone", "## Speed and cost"):
        assert section in text
    assert "with covers from the content's templates" in text
    assert f"Claude calls, this run and earlier ones into the same folder: {HAIKU} " in text
    for case in result.cases:
        assert f"### {case.id}" in text
    assert text.count(f"- **{GEMMA}**") == len(result.cases)
