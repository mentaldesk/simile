from simile.clinic.config import DEFAULT_CONFIG as CLINIC
from simile.player.config import SALVAGE
from simile.schema import CARRY_LIMIT, Item, lamp
from simile.story.lens import LENS
from simile.street.sewers import levels
from simile.street.village import village


def weights() -> dict[str, float]:
    """Every item the world holds, by id: in its maps, at the metro's salvage, and the lens."""
    items: list[Item] = [LENS, *(salvage.item for salvage in SALVAGE.values())]
    for plan in [*village(), *levels()]:
        items += [pickup.item for pickup in plan.pickups if pickup.item is not None]
        items += [item for thing in plan.interactables for item in thing.items]
    found: dict[str, float] = {}
    for item in items:
        assert found.setdefault(item.id, item.weight) == item.weight, f"{item.id} weighs two ways"
    return found


def test_every_recipes_parts_and_the_lamp_fit_within_the_carry_limit() -> None:
    weight = weights()
    loads = {
        bionic: sum(weight[part] * count for part, count in recipe.parts.items()) + lamp().weight
        for bionic, recipe in CLINIC.recipes.items()
    }
    assert {bionic: kg for bionic, kg in loads.items() if kg > CARRY_LIMIT} == {}
