import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import TypeAdapter, ValidationError

from simile.schema import (
    ARIS,
    MODELS,
    Fact,
    HowKnown,
    Incident,
    JournalEntry,
    Knower,
    Lead,
    Memory,
    MemoryKind,
    Source,
    SourceKind,
    export,
)

HERE = Path(__file__).parent
INCIDENTS: list[dict[str, Any]] = json.loads((HERE / "incidents.json").read_text())
JOURNAL: list[dict[str, Any]] = json.loads((HERE / "journal.json").read_text())
ONE_ATTACKER, THREE_ATTACKERS = INCIDENTS
ATTACK, MOTIVE, SHOUTING, LANE, NOTES = ONE_ATTACKER["facts"]
FROM_NOTES, FROM_TOBIAS, FROM_KOFI, FROM_RAYMOND = JOURNAL

type Story = Incident | Fact | Knower | Lead | Source | JournalEntry


def schema(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((export.JSON_DIR / f"{name}.json").read_text()))


def rejects(model: type[Story], data: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        model.model_validate(data)


def changes(model: Story, field: str, value: Any, match: str) -> None:
    before = model.model_dump()
    with pytest.raises(ValidationError, match=match):
        setattr(model, field, value)
    assert model.model_dump() == before


@pytest.mark.parametrize(
    ("model", "data"),
    [
        *[pytest.param(Incident, data, id=f"incidents[{i}]") for i, data in enumerate(INCIDENTS)],
        *[pytest.param(JournalEntry, data, id=f"journal[{i}]") for i, data in enumerate(JOURNAL)],
    ],
)
def test_fixture_round_trips_through_json(model: type[Story], data: dict[str, Any]) -> None:
    parsed = model.model_validate_json(json.dumps(data))
    dumped = parsed.model_dump_json()

    assert json.loads(dumped) == data
    assert model.model_validate_json(dumped) == parsed


def test_they_are_exported_and_the_schema_accepts_the_fixtures() -> None:
    assert {Incident, Fact, JournalEntry} <= set(MODELS)
    for incident in INCIDENTS:
        schema("Incident").validate(incident)
        for fact in incident["facts"]:
            schema("Fact").validate(fact)
    for entry in JOURNAL:
        schema("JournalEntry").validate(entry)
    assert not schema("Incident").is_valid(ONE_ATTACKER | {"attackers": []})
    assert not schema("JournalEntry").is_valid(FROM_KOFI | {"true": True})


def test_the_fixtures_have_one_attacker_and_three() -> None:
    incidents = TypeAdapter(list[Incident]).validate_python(INCIDENTS)

    assert [len(incident.attackers) for incident in incidents] == [1, 3]
    assert {incident.victim for incident in incidents} == {ARIS}


def test_every_attacker_knows_what_they_did_and_lies_about_it() -> None:
    for incident in TypeAdapter(list[Incident]).validate_python(INCIDENTS):
        attack = next(fact for fact in incident.facts if fact.id == "attack")
        did = {knower.id: knower for knower in attack.known_by if knower.how is HowKnown.DID}

        assert did.keys() == set(incident.attackers)
        assert all(knower.cover for knower in did.values())


def test_the_journal_follows_the_trail_of_the_one_attacker_incident() -> None:
    incident = Incident.model_validate(ONE_ATTACKER)
    facts = {fact.id: fact for fact in incident.facts}
    journal = TypeAdapter(list[JournalEntry]).validate_python(JOURNAL)
    learned = [entry.fact_id for entry in journal]

    for entry in journal:
        fact = facts[entry.fact_id]
        if entry.source.kind is SourceKind.CLUE:
            assert entry.source.id == fact.found_in
        else:
            knower = next(knower for knower in fact.known_by if knower.id == entry.source.id)
            assert knower.cover if entry.flushed else knower.tells_from is not None
        assert all(lead in fact.leads for lead in entry.leads)
        for lead in fact.leads:
            assert (lead in entry.leads) is not (lead.fact_id in learned)


def test_a_clue_never_flushes_and_a_resident_without_the_eye_is_unread() -> None:
    assert (FROM_NOTES["source"]["kind"], FROM_NOTES["flushed"]) == ("clue", None)
    assert (FROM_TOBIAS["source"]["kind"], FROM_TOBIAS["flushed"]) == ("resident", None)
    assert [FROM_KOFI["flushed"], FROM_RAYMOND["flushed"]] == [False, True]


def test_the_victim_is_aris_unless_named() -> None:
    data = {key: value for key, value in ONE_ATTACKER.items() if key != "victim"}

    assert Incident.model_validate(data).victim == ARIS == "aris"


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"attackers": []}, "at least 1 item"),
        ({"attackers": ["raymond", "priya", "henrietta", "tobias"]}, "at most 3 items"),
        ({"attackers": ["raymond", "raymond"]}, "each attacker is named once"),
        ({"attackers": ["aris"]}, "the victim isn't one of the attackers"),
        ({"motive": ""}, "at least 1 character"),
        ({"night": "2026-03-06T23:40:00"}, "timezone"),
        ({"facts": [ATTACK, ATTACK]}, "each fact has its own id"),
        ({"facts": [MOTIVE]}, "a lead goes to attack, which isn't one of its facts"),
        ({"victim": "Aris"}, "String should match pattern"),
        ({"witnesses": []}, "Extra inputs are not permitted"),
    ],
)
def test_rejects_invalid_incidents(update: dict[str, Any], match: str) -> None:
    rejects(Incident, ONE_ATTACKER | update, match)


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"what": ""}, "at least 1 character"),
        ({"where": ""}, "at least 1 character"),
        ({"about": ["Raymond"]}, "String should match pattern"),
        ({"known_by": [LANE["known_by"][0]] * 2}, "each resident knows it once"),
        (
            {"leads": [{"fact_id": "lane", "text": "Go round in circles."}]},
            "doesn't lead to itself",
        ),
        ({"leads": [{"fact_id": "attack", "text": ""}]}, "at least 1 character"),
        ({"found_in": "Aris's notes"}, "String should match pattern"),
    ],
)
def test_rejects_invalid_facts(update: dict[str, Any], match: str) -> None:
    rejects(Fact, LANE | update, match)


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"tells_from": 1.1}, "less than or equal to 1"),
        ({"tells_from": -0.1}, "greater than or equal to 0"),
        ({"cover": ""}, "at least 1 character"),
        ({"how": "guessed"}, "how"),
        ({"id": "Kofi"}, "String should match pattern"),
    ],
)
def test_rejects_invalid_knowers(update: dict[str, Any], match: str) -> None:
    rejects(Knower, LANE["known_by"][0] | update, match)


@pytest.mark.parametrize("field", ["tells_from", "cover"])
def test_a_knower_says_outright_whether_they_tell_and_lie(field: str) -> None:
    knower = dict(LANE["known_by"][0])
    del knower[field]

    rejects(Knower, knower, f"{field}\n  Field required")


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"flushed": True}, "only a resident can flush"),
        ({"flushed": False}, "only a resident can flush"),
        ({"leads": [{"fact_id": "notes", "text": "Read them again."}]}, "go to other facts"),
        ({"text": ""}, "at least 1 character"),
        ({"source": {"kind": "rumour", "id": "aris_notes", "name": "Notes"}}, "kind"),
        ({"source": {"kind": "clue", "id": "aris_notes", "name": ""}}, "at least 1 character"),
        ({"learned": "yesterday"}, "learned"),
    ],
)
def test_rejects_invalid_journal_entries(update: dict[str, Any], match: str) -> None:
    rejects(JournalEntry, FROM_NOTES | update, match)


def test_a_journal_entry_says_outright_whether_the_eye_saw_a_flush() -> None:
    entry = {key: value for key, value in FROM_KOFI.items() if key != "flushed"}

    rejects(JournalEntry, entry, "flushed\n  Field required")


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("attackers", [], "at least 1 item"),
        ("attackers", ["raymond", "aris"], "the victim isn't one of the attackers"),
        ("victim", "raymond", "the victim isn't one of the attackers"),
        ("facts", [ATTACK, MOTIVE, ATTACK], "each fact has its own id"),
        ("facts", [LANE], "a lead goes to attack"),
        ("motive", "", "at least 1 character"),
    ],
)
def test_rejects_invalid_changes_to_the_incident(field: str, value: Any, match: str) -> None:
    changes(Incident.model_validate(ONE_ATTACKER), field, value, match)


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("known_by", [Knower.model_validate(LANE["known_by"][0])] * 2, "knows it once"),
        ("id", "attack", "doesn't lead to itself"),
        ("leads", [Lead(fact_id="lane", text="Again.")], "doesn't lead to itself"),
    ],
)
def test_rejects_invalid_changes_to_a_fact(field: str, value: Any, match: str) -> None:
    changes(Fact.model_validate(LANE), field, value, match)


def test_rejects_invalid_changes_to_a_knower() -> None:
    changes(Knower.model_validate(LANE["known_by"][0]), "tells_from", 1.5, "less than or equal")


@pytest.mark.parametrize(
    ("entry", "field", "value", "match"),
    [
        (FROM_NOTES, "flushed", True, "only a resident can flush"),
        (FROM_KOFI, "source", FROM_NOTES["source"], "only a resident can flush"),
        (FROM_NOTES, "fact_id", "motive", "go to other facts"),
        (FROM_KOFI, "text", "", "at least 1 character"),
    ],
)
def test_rejects_invalid_changes_to_a_journal_entry(
    entry: dict[str, Any], field: str, value: Any, match: str
) -> None:
    changes(JournalEntry.model_validate(entry), field, value, match)


def test_a_valid_change_is_kept() -> None:
    entry = JournalEntry.model_validate(FROM_NOTES)
    entry.leads = []
    incident = Incident.model_validate(THREE_ATTACKERS)
    incident.attackers = ["henrietta", "priya"]
    knower = Knower.model_validate(LANE["known_by"][0])
    knower.tells_from = None

    assert (entry.leads, incident.attackers, knower.tells_from) == (
        [],
        ["henrietta", "priya"],
        None,
    )


SEEDED = Memory(
    owner="kofi",
    kind=MemoryKind.OBSERVATION,
    content="I was painting in the lane when a big man in a long coat ran past, holding his arm.",
    salience=0.8,
    valence=-0.6,
    timestamp=datetime(2026, 3, 6, 23, 50, tzinfo=UTC),
    about=["raymond"],
    fact_id="lane",
)


def test_a_memory_seeded_from_a_fact_carries_its_id() -> None:
    dumped = json.loads(SEEDED.model_dump_json())

    assert dumped["fact_id"] == "lane"
    assert Memory.model_validate(dumped) == SEEDED
    schema("Memory").validate(dumped)


def test_any_other_memory_dumps_without_a_fact_id() -> None:
    memory = SEEDED.model_copy(update={"fact_id": None})

    assert "fact_id" not in json.loads(memory.model_dump_json())
    assert "fact_id" not in json.loads((export.JSON_DIR / "Memory.json").read_text())["required"]
