from simile.story import NOTES, load_story
from simile.story.disappearance import LAST_SEEN
from simile.world.map import load_maps, with_every_location

STORY = load_story()
MAPS = load_maps()


def test_the_clues_lie_on_cells_you_can_stand_on_in_her_workshop() -> None:
    workshop = with_every_location(MAPS).location(STORY.aris.workshop)

    assert {clue.id for clue in STORY.clues} == {NOTES}
    for clue in STORY.clues:
        floor = MAPS[clue.map]
        assert floor.building == workshop.id and floor.floor == 0, clue.id
        assert floor.walkable(clue.x, clue.y), clue.id
    assert STORY.clue(NOTES).pages


def test_the_streets_named_are_on_the_maps() -> None:
    assert STORY.aris.street in MAPS
    assert STORY.aris.last_seen in MAPS


def test_every_witness_who_might_lie_has_a_cover_story() -> None:
    assert set(STORY.texts.covers) == {"distrust", LAST_SEEN}


def test_each_note_names_a_distruster_by_their_initial_alone() -> None:
    notes = STORY.texts.notes

    assert len(set(notes)) == len(notes)
    assert all(note.startswith("{initial}. ") and note.count("{") == 1 for note in notes)
