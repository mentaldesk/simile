import pytest

from simile.conversation.prompt import JOKE, PLAIN
from simile.schema import Humour, HumourStyle, Npc

from .test_lies import Scenes
from .test_player import Village, make_npc

pytestmark = pytest.mark.anyio

ALWAYS = Humour(style=HumourStyle.SILLY, seriousness=0)
NEVER = Humour(style=HumourStyle.NONE, seriousness=1)


def with_humour(humour: Humour | None, id: str = "ana", home: str = "house_1") -> Npc:
    return make_npc(id, home).model_copy(update={"humour": humour})


@pytest.mark.parametrize(("humour", "told"), [(ALWAYS, JOKE), (NEVER, PLAIN)])
async def test_a_reply_to_the_player_is_told_whether_to_joke(humour: Humour, told: str) -> None:
    village = Village(["Hello there. [values: connection]"], npcs=(with_humour(humour),))

    village.players.say("Morning!", "ana")
    await village.run()

    assert told in village.script.prompts[-1]


async def test_a_reply_without_a_humour_has_no_joke_direction() -> None:
    village = Village(["Hello there. [values: connection]"], npcs=(with_humour(None),))

    village.players.say("Morning!", "ana")
    await village.run()

    assert JOKE not in village.script.prompts[-1]
    assert PLAIN not in village.script.prompts[-1]


async def test_a_scene_says_how_many_lines_each_humour_jokes_in() -> None:
    prompt, _ = await Scenes(with_humour(NEVER)).scene()

    direction = prompt.split("## Direction\n", 1)[1]
    assert "- Ana doesn't joke this time." in direction.splitlines()
