from simile.npc import load_npcs
from simile.schema import Accessory, HairStyle
from simile.story import DOOR, NOTES, load_story
from simile.story.looks import figure
from simile.world.map import load_maps, with_every_location

STORY = load_story()
MAPS = load_maps()
NPCS = {npc.id: npc for npc in load_npcs()}


def test_the_clues_lie_on_cells_you_can_stand_on_in_her_workshop() -> None:
    workshop = with_every_location(MAPS).location(STORY.aris.workshop)

    assert {clue.id for clue in STORY.clues} == {NOTES, DOOR}
    for clue in STORY.clues:
        floor = MAPS[clue.map]
        assert floor.building == workshop.id and floor.floor == 0, clue.id
        assert floor.walkable(clue.x, clue.y), clue.id
    assert STORY.clue(NOTES).pages


def test_the_places_named_are_on_the_maps() -> None:
    town = with_every_location(MAPS)

    assert STORY.aris.street in MAPS
    for place in STORY.meeting_places:
        assert town.location(place.id)


def test_every_witness_who_might_lie_has_a_cover_story() -> None:
    assert set(STORY.texts.covers) == {"shouting", "seen", "grudge", "meeting"}


def test_a_figure_is_what_you_could_make_out_in_a_dark_lane() -> None:
    raymond = NPCS["raymond"].appearance
    capped = raymond.model_copy(update={"accessories": [Accessory.CAP]})
    bald = raymond.model_copy(update={"hair_style": HairStyle.BALD, "accessories": []})
    packed = raymond.model_copy(update={"accessories": [Accessory.APRON, Accessory.BACKPACK]})

    assert figure(raymond) == "a grey-haired figure in a red top and sunglasses"
    assert figure(capped) == "a figure in a red top and a cap"
    assert figure(bald) == "a bald figure in a red top"
    assert figure(packed) == "a grey-haired figure in a red top, with a backpack"
    assert figure(NPCS["kofi"].appearance) == "a dark-haired figure in an amber top and headphones"
