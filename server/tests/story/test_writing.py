import random

import pytest

from simile.llm import CallRecord, FakeProvider, LLMClient, LLMError, Model
from simile.npc import load_npcs
from simile.story import load_story
from simile.story.suspects import Suspect, suspect
from simile.story.writing import PURPOSE, Backstory, Written, drafted, write

pytestmark = pytest.mark.anyio

STORY = load_story()
NPCS = {npc.id: npc for npc in load_npcs()}


def suspects(*ids: str) -> list[Suspect]:
    rng = random.Random(0)
    return [suspect(NPCS[npc], STORY.grievances, rng) for npc in ids]


def side(npc: str, alibi: str = "I was at the lodge till late.") -> Written:
    return Written(
        id=npc,
        grievance=f"{npc.title()} lost a contract.",
        resents="She cost me that contract.",
        remembers="I went round to make her listen, and it got out of hand.",
        alibi=alibi,
        deflection="Kids from the city, I'd say.",
        denial="We were on good terms.",
        note=f"{npc[0].upper()}. came about the contract again.",
    )


async def test_sonnet_writes_the_motive_and_each_attackers_side_once() -> None:
    found = suspects("henrietta", "raymond")
    written = Backstory(
        motive="They wanted her gone.", attackers=[side("henrietta"), side("raymond")]
    )
    provider, records = FakeProvider([written]), list[CallRecord]()

    llm = LLMClient(provider, listeners=[records.append])

    residents = ["Henrietta Okonkwo-Bell", "Raymond Tay", "Kofi Lindqvist-Mensah"]

    backstory, wrote = await write(
        llm, found, STORY, met=STORY.meeting_places[0], residents=residents
    )

    assert wrote and backstory == written
    [request], [record] = provider.requests, records
    assert (request.model, record.purpose) == (Model.SONNET, PURPOSE)
    prompt = request.messages[-1].content
    for attacker in found:
        assert attacker.npc.name in prompt
        assert STORY.grievances[attacker.grievance].told in prompt
    assert "The 2 of them went together. They met at the noodle bar the evening before" in prompt
    assert "Their initial: H. What Aris did:" in prompt
    assert '"motive"' in request.system
    assert "The village's residents: " + ", ".join(residents) in prompt
    assert "Never strangers, outsiders, people from out of town" in request.system
    assert "never at strangers or outsiders" in request.system


async def test_an_attacker_the_reply_leaves_out_is_written_from_templates() -> None:
    found = suspects("henrietta", "raymond")
    provider = FakeProvider([Backstory(motive="Spite.", attackers=[side("raymond")])])

    backstory, wrote = await write(LLMClient(provider), found, STORY)

    templates = drafted(found, STORY)
    assert wrote and backstory.motive == "Spite."
    assert backstory.attackers == [templates.attackers[0], side("raymond")]


@pytest.mark.parametrize(
    "replies",
    [[LLMError("usage limit reached")], ["Morning!", "Still not JSON."], [TimeoutError()]],
)
async def test_without_a_reply_it_falls_back_to_the_templates(replies: list[object]) -> None:
    found = suspects("raymond")

    backstory, wrote = await write(LLMClient(FakeProvider(replies)), found, STORY)

    assert not wrote and backstory == drafted(found, STORY)


async def test_without_an_llm_it_never_asks() -> None:
    found = suspects("priya")

    assert await write(None, found, STORY) == (drafted(found, STORY), False)


def test_the_templates_name_each_attacker_and_bring_them_together() -> None:
    found = suspects("henrietta", "raymond", "priya")

    backstory = drafted(found, STORY)

    for attacker, written in zip(found, backstory.attackers, strict=True):
        name = attacker.npc.name.split()[0]
        assert written.id == attacker.npc.id
        assert name in written.grievance and written.grievance in backstory.motive
        assert written.note.startswith(f"{name[0]}.")
        assert "{" not in written.remembers + written.note
    assert backstory.motive.endswith(STORY.texts.together)
    assert "with Raymond and Priya" in backstory.attackers[0].remembers
