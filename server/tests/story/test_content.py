import json

from simile.story import NOTES, load_story
from simile.story.disappearance import LAST_SEEN, street_name
from simile.world.map import STREET_DIR, load_maps, with_every_location

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


def test_the_street_she_was_last_seen_on_is_called_what_its_map_calls_it() -> None:
    street = json.loads((STREET_DIR / f"{STORY.aris.last_seen}.tmj").read_text())
    label = next(p["value"] for p in street["properties"] if p["name"] == "label")

    assert street_name(STORY.aris.last_seen) == label


def test_every_witness_who_might_lie_has_a_cover_story() -> None:
    assert set(STORY.texts.covers) == {"distrust", LAST_SEEN}


def test_each_note_names_a_distruster_by_their_initial_alone() -> None:
    notes = STORY.texts.notes

    assert len(set(notes)) == len(notes)
    assert all(note.startswith("{initial}. ") and note.count("{") == 1 for note in notes)
