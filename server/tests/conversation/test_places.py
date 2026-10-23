import pytest

from simile.conversation.places import ABOUT, ONLY
from simile.schema import Npc
from simile.story.town import FACTS, METRO, Knowing, known

from ..story.test_town import NEWCOMER, OLD_HAND
from .test_player import BEN, Village

pytestmark = pytest.mark.anyio

METRO_ABOUT = ABOUT.format(place="the old metro", other="Visitor")


def talking_to(npc: Npc, seed: int) -> Village:
    village = Village(npcs=(npc, BEN))
    village.players.town_seed = seed
    return village


@pytest.mark.parametrize("npc", [NEWCOMER, OLD_HAND], ids=lambda npc: npc.id)
@pytest.mark.parametrize("seed", range(10))
async def test_asked_about_the_metro_a_resident_has_only_what_they_know(
    npc: Npc, seed: int
) -> None:
    village = talking_to(npc, seed)

    village.players.say("Do you know how to get down to the old metro?", npc.id)
    await village.run()

    prompt = village.script.prompts[-1]
    assert METRO_ABOUT in prompt and ONLY in prompt
    knows = known(npc, seed)
    for id in METRO:
        fact, knowing = FACTS[id], knows.get(id)
        assert (fact.what in prompt) == (knowing is Knowing.KNOWS), id
        assert (fact.rumour in prompt) == (knowing is Knowing.HEARD), id
        assert (fact.unknown in prompt) == (knowing is None), id
    assert FACTS["town_cafe"].what not in prompt


async def test_nothing_about_places_until_the_player_names_one_and_then_it_stays() -> None:
    village = talking_to(OLD_HAND, 0)

    for said in ("Lovely morning, isn't it?", "Is there a café nearby?", "What do you do?"):
        village.players.say(said, OLD_HAND.id)
        await village.run()

    first, second, third = village.script.prompts
    cafe = FACTS["town_cafe"].what
    assert "What you know of" not in first
    assert cafe in second and cafe in third
    assert METRO_ABOUT not in third


async def test_a_resident_who_never_heard_of_the_metro_says_so() -> None:
    seed = next(s for s in range(1000) if not any(id in known(NEWCOMER, s) for id in METRO))
    village = talking_to(NEWCOMER, seed)

    village.players.say("Where's the metro?", NEWCOMER.id)
    await village.run()

    prompt = village.script.prompts[-1]
    assert "You've never heard of an old metro under the village." in prompt
    assert not any(FACTS[id].what in prompt or FACTS[id].rumour in prompt for id in METRO)
