import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.conversation.player import (
    DEFAULT_PLAYER_CONFIG,
    SUSPECT_ENV,
    PlayerConfig,
    PlayerConversations,
)
from simile.llm import Model

from .test_player import Village
from .test_player_lifespan import MODULES, MakePackage, make_app
from .test_telling import LONG_AGO, investigating

pytestmark = pytest.mark.anyio

LOCAL = "ollama:gemma4:26b"


def models(village: Village) -> list[str]:
    return [record.model for record in village.records if record.purpose == "player-reply"]


async def test_a_reply_set_up_to_lie_is_written_by_the_suspect_model_from_then_on() -> None:
    village = investigating(config=LONG_AGO, player=PlayerConfig(suspect_model=LOCAL))
    village.walk_to("ben", 1)

    for said in ("Lovely morning, isn't it?", "How did you get on with Aris?", "Ok."):
        village.players.say(said, "ben")
        await village.run()

    assert models(village) == [Model.HAIKU_4_5, LOCAL, LOCAL]


async def test_a_resident_with_nothing_to_lie_about_keeps_the_usual_model() -> None:
    village = investigating(player=PlayerConfig(suspect_model=LOCAL))

    village.players.say("Did you see Aris the evening before she went missing?", "ana")
    await village.run()

    assert models(village) == [Model.HAIKU_4_5]


async def test_by_default_suspects_are_voiced_by_the_same_haiku() -> None:
    village = investigating()
    village.walk_to("ben", 1)

    village.players.say("How did you get on with Aris?", "ben")
    await village.run()

    assert DEFAULT_PLAYER_CONFIG.suspect_model == DEFAULT_PLAYER_CONFIG.model == Model.HAIKU_4_5
    assert models(village) == [Model.HAIKU_4_5]


@pytest.mark.parametrize("chosen", [None, LOCAL])
def test_the_environment_chooses_the_suspect_model(
    make_package: MakePackage, monkeypatch: pytest.MonkeyPatch, chosen: str | None
) -> None:
    if chosen:
        monkeypatch.setenv(SUSPECT_ENV, chosen)
    else:
        monkeypatch.delenv(SUSPECT_ENV, raising=False)
    app: Starlette = make_app(make_package, *MODULES)

    with TestClient(app):
        players = app.state.players
        assert isinstance(players, PlayerConversations)
        assert players.config.suspect_model == (chosen or Model.HAIKU_4_5)
        assert players.config.model == Model.HAIKU_4_5
