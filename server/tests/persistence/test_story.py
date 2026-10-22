import json
from pathlib import Path

from pydantic import TypeAdapter

from simile.persistence import SavedWorld, capture
from simile.schema import Incident, JournalEntry

from .test_player import OLD_SAVE, opened, save_from_before_the_player
from .test_state import Village

SCHEMA_TESTS = Path(__file__).parents[1] / "schema"
INCIDENT = TypeAdapter(list[Incident]).validate_json(
    (SCHEMA_TESTS / "incidents.json").read_bytes()
)[0]
JOURNAL = TypeAdapter(list[JournalEntry]).validate_json(
    (SCHEMA_TESTS / "journal.json").read_bytes()
)


def test_a_save_from_before_the_incident_loads_without_one_and_an_empty_journal(
    tmp_path: Path,
) -> None:
    path = tmp_path / "simile.db"
    save_from_before_the_player(path)

    with opened(path) as store:
        loaded = store.load()

    assert not {"incident", "journal"} & json.loads(OLD_SAVE).keys()
    assert loaded is not None and loaded.npcs.keys() == {"desmond", "henrietta"}
    assert (loaded.incident, loaded.journal) == (None, [])


def test_the_incident_and_the_journal_round_trip_through_save_and_load(tmp_path: Path) -> None:
    path = tmp_path / "simile.db"
    world = SavedWorld.model_validate(
        capture(Village().behaviour).model_dump() | {"incident": INCIDENT, "journal": JOURNAL}
    )
    with opened(path) as store:
        store.save(world)

    with opened(path) as reopened:
        loaded = reopened.load()

    assert loaded is not None
    assert (loaded.incident, loaded.journal) == (INCIDENT, JOURNAL)
