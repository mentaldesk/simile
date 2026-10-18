import pytest

from simile.behaviour import Activity, Goal
from simile.cafe.cafe import barista
from simile.cafe.config import DEFAULT_CONFIG as CAFE_CONFIG
from simile.casting import bind, cast
from simile.characters.pool import load_pool
from simile.characters.tables import load_tables
from simile.npc import NPCS_DIR, load_npcs
from simile.schema import Shift, Weekday

from .conftest import ANA, BEA, Village, make_npc

SHIFT = Shift(days=list(Weekday), start=CAFE_CONFIG.opens, end=CAFE_CONFIG.closes)
DEE = make_npc("dee", "house_4").model_copy(
    update={"workplace": CAFE_CONFIG.home, "shifts": [SHIFT]}
)


def test_todays_village_keeps_mirela_who_lives_above_the_cafe() -> None:
    assert barista(load_npcs(NPCS_DIR), CAFE_CONFIG.home) == "mirela"


def test_whoever_works_at_the_cafe_is_its_barista_before_whoever_lives_there() -> None:
    assert barista([BEA, DEE], CAFE_CONFIG.home) == "dee"
    assert barista([ANA, BEA], CAFE_CONFIG.home) == "bea"
    assert barista([ANA], CAFE_CONFIG.home) is None


@pytest.mark.anyio
async def test_a_casts_barista_is_the_cafes_barista_and_starts_at_the_till() -> None:
    made = bind(cast(load_pool(), 10, seed=3), seed=3)
    [holder] = [r.character.id for r in made.residents if r.workplace == CAFE_CONFIG.home]

    village = Village(made.npcs())
    await village.run(minutes=1)

    assert village.cafe.barista == holder
    assert village.cafe.on_shift
    assert village.behaviour.goal(holder) == Goal(Activity.COFFEE_SHOP, CAFE_CONFIG.home)


def test_the_barista_role_works_the_cafes_hours() -> None:
    [role] = [role for role in load_tables().roles if role.workplace == CAFE_CONFIG.home]

    assert role.shifts == [SHIFT]
