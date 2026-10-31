import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import TypeAdapter, ValidationError

from simile.protocol.export import SCHEMA_FILE as PROTOCOL_SCHEMA
from simile.schema import (
    ARIS,
    MODELS,
    Disappearance,
    Fact,
    HowKnown,
    Incident,
    Investigation,
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
DISAPPEARANCES: list[dict[str, Any]] = json.loads((HERE / "disappearances.json").read_text())
ONE_ATTACKER, THREE_ATTACKERS = INCIDENTS
VILLAGE, ONE_DISTRUSTER = DISAPPEARANCES
GONE = VILLAGE["facts"][0]
ATTACK, MOTIVE, SHOUTING, LANE, NOTES = ONE_ATTACKER["facts"]
FROM_NOTES, FROM_TOBIAS, FROM_KOFI, FROM_RAYMOND = JOURNAL

type Story = Incident | Disappearance | Fact | Knower | Lead | Source | JournalEntry | Investigation


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
        *[
            pytest.param(Disappearance, data, id=f"disappearances[{i}]")
            for i, data in enumerate(DISAPPEARANCES)
        ],
        *[pytest.param(JournalEntry, data, id=f"journal[{i}]") for i, data in enumerate(JOURNAL)],
    ],
)
def test_fixture_round_trips_through_json(model: type[Story], data: dict[str, Any]) -> None:
    parsed = model.model_validate_json(json.dumps(data))
    dumped = parsed.model_dump_json()

    assert json.loads(dumped) == data
    assert model.model_validate_json(dumped) == parsed


def test_they_are_exported_and_the_schema_accepts_the_fixtures() -> None:
    assert {Incident, Disappearance, Fact, JournalEntry, Investigation} <= set(MODELS)
    schema("Investigation").validate(
        {"incident": ONE_ATTACKER, "disappearance": None, "journal": JOURNAL}
    )
    schema("Investigation").validate({"incident": None, "disappearance": VILLAGE, "journal": []})
    for disappearance in DISAPPEARANCES:
        schema("Disappearance").validate(disappearance)
        for fact in disappearance["facts"]:
            schema("Fact").validate(fact)
    assert not schema("Disappearance").is_valid(VILLAGE | {"distrusted_by": []})
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
        still_open = [lead for lead in fact.leads if lead.fact_id not in learned]
        assert entry.leads == ([] if entry.flushed else still_open)


def test_a_lie_opens_no_leads_but_closes_those_to_its_fact() -> None:
    motive = Fact.model_validate(MOTIVE)

    assert (FROM_RAYMOND["fact_id"], FROM_RAYMOND["flushed"]) == ("motive", True)
    assert motive.leads and FROM_RAYMOND["leads"] == []
    assert [lead["fact_id"] for lead in NOTES["leads"]] == ["motive", "shouting"]
    assert FROM_NOTES["leads"] == []


def test_a_clue_never_flushes_and_a_resident_without_the_eye_is_unread() -> None:
    assert (FROM_NOTES["source"]["kind"], FROM_NOTES["flushed"]) == ("clue", None)
    assert (FROM_TOBIAS["source"]["kind"], FROM_TOBIAS["flushed"]) == ("resident", None)
    assert [FROM_KOFI["flushed"], FROM_RAYMOND["flushed"]] == [False, True]


def test_the_fixtures_follow_the_default_village_and_a_lone_distruster() -> None:
    disappearances = TypeAdapter(list[Disappearance]).validate_python(DISAPPEARANCES)

    assert [d.distrusted_by for d in disappearances] == [
        ["tobias", "henrietta", "mirela", "raymond"],
        ["henrietta"],
    ]


def test_each_distruster_knows_how_they_felt_and_the_passer_was_one_of_them() -> None:
    for disappearance in TypeAdapter(list[Disappearance]).validate_python(DISAPPEARANCES):
        facts = {fact.id: fact for fact in disappearance.facts}
        for npc in disappearance.distrusted_by:
            did = [k.id for k in facts[f"distrust_{npc}"].known_by if k.how is HowKnown.DID]
            assert did == [npc]
        passers = [k.id for k in facts["passed"].known_by if k.how is HowKnown.WITNESSED]
        assert len(passers) == 1 and passers[0] in disappearance.distrusted_by
        assert ARIS not in [k.id for fact in facts.values() for k in fact.known_by]


def test_the_notes_lead_to_the_noted_distrusters_and_the_trail_ends_underground() -> None:
    disappearance = Disappearance.model_validate(VILLAGE)
    facts = {fact.id: fact for fact in disappearance.facts}

    assert [lead.fact_id for lead in facts["gone"].leads] == ["notes", "last_seen"]
    assert [lead.fact_id for lead in facts["notes"].leads] == [
        "distrust_henrietta",
        "distrust_raymond",
    ]
    assert [lead.fact_id for lead in facts["last_seen"].leads] == ["lift_log", "passed"]
    assert [lead.fact_id for lead in facts["lift_log"].leads] == ["hatch_log"]
    assert facts["hatch_log"].leads == []


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
        ({"distrusted_by": []}, "at least 1 item"),
        ({"distrusted_by": ["tobias", "tobias"]}, "each resident distrusted her once"),
        ({"distrusted_by": ["tobias", "aris"]}, "Aris isn't one of those who distrusted her"),
        ({"distrusted_by": ["Tobias"]}, "String should match pattern"),
        ({"facts": [GONE, GONE]}, "each fact has its own id"),
        ({"facts": [GONE]}, "a lead goes to notes, which isn't one of its facts"),
        ({"attackers": ["raymond"]}, "Extra inputs are not permitted"),
    ],
)
def test_rejects_invalid_disappearances(update: dict[str, Any], match: str) -> None:
    rejects(Disappearance, VILLAGE | update, match)


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
        ("distrusted_by", [], "at least 1 item"),
        ("distrusted_by", ["aris"], "Aris isn't one of those who distrusted her"),
        ("distrusted_by", ["mirela", "mirela"], "each resident distrusted her once"),
        ("facts", [GONE], "a lead goes to notes"),
    ],
)
def test_rejects_invalid_changes_to_the_disappearance(field: str, value: Any, match: str) -> None:
    changes(Disappearance.model_validate(VILLAGE), field, value, match)


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


def test_a_resident_told_a_fact_is_added_as_a_knower_of_it() -> None:
    fact = Fact.model_validate(LANE)
    seeded = fact.known_by
    told = Knower(id="mirela", how=HowKnown.TOLD, tells_from=0.6, cover=None)

    fact.learned_by(told)

    assert [knower.id for knower in fact.known_by] == ["kofi", "mirela"]
    assert fact.known_by[-1] == told
    assert fact.known_by is not seeded and len(seeded) == 1


def test_a_resident_who_already_knows_it_is_rejected_and_the_fact_is_unchanged() -> None:
    fact = Fact.model_validate(LANE)
    before = fact.model_dump()

    with pytest.raises(ValidationError, match="each resident knows it once"):
        fact.learned_by(Knower(id="kofi", how=HowKnown.TOLD, tells_from=0, cover=None))

    assert fact.model_dump() == before


def test_rejects_invalid_changes_to_a_knower() -> None:
    changes(Knower.model_validate(LANE["known_by"][0]), "tells_from", 1.5, "less than or equal")


@pytest.mark.parametrize(
    ("entry", "field", "value", "match"),
    [
        (FROM_NOTES, "flushed", True, "only a resident can flush"),
        (FROM_KOFI, "source", FROM_NOTES["source"], "only a resident can flush"),
        (FROM_KOFI, "fact_id", "attack", "go to other facts"),
        (FROM_KOFI, "text", "", "at least 1 character"),
    ],
)
def test_rejects_invalid_changes_to_a_journal_entry(
    entry: dict[str, Any], field: str, value: Any, match: str
) -> None:
    changes(JournalEntry.model_validate(entry), field, value, match)


def test_a_valid_change_is_kept() -> None:
    entry = JournalEntry.model_validate(FROM_KOFI)
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
    content="I was painting in the lane when a man in a red top and sunglasses ran past.",
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


def test_an_investigation_starts_with_no_story_and_an_empty_journal() -> None:
    investigation = Investigation()

    assert (investigation.incident, investigation.disappearance, investigation.journal) == (
        None,
        None,
        [],
    )
    assert json.loads(investigation.model_dump_json()) == {
        "incident": None,
        "disappearance": None,
        "journal": [],
    }
    assert Investigation.model_validate({}) == investigation


def test_a_save_with_an_incident_loads_with_no_disappearance() -> None:
    investigation = Investigation.model_validate_json(
        json.dumps({"incident": ONE_ATTACKER, "journal": JOURNAL})
    )

    assert investigation.incident == Incident.model_validate(ONE_ATTACKER)
    assert investigation.disappearance is None
    assert len(investigation.journal) == len(JOURNAL)


@pytest.mark.parametrize(
    ("incident", "disappearance"),
    [(THREE_ATTACKERS, None), (None, ONE_DISTRUSTER), (ONE_ATTACKER, VILLAGE)],
)
def test_an_investigation_round_trips_through_json(
    incident: dict[str, Any] | None, disappearance: dict[str, Any] | None
) -> None:
    data = {"incident": incident, "disappearance": disappearance, "journal": JOURNAL}
    investigation = Investigation.model_validate(data)

    assert json.loads(investigation.model_dump_json()) == data


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("incident", ONE_ATTACKER | {"attackers": []}, "at least 1 item"),
        ("disappearance", VILLAGE | {"distrusted_by": []}, "at least 1 item"),
        ("journal", [FROM_NOTES | {"flushed": True}], "only a resident can flush"),
    ],
)
def test_rejects_invalid_changes_to_the_investigation(field: str, value: Any, match: str) -> None:
    changes(Investigation(incident=Incident.model_validate(ONE_ATTACKER)), field, value, match)


def test_the_story_and_its_facts_are_never_sent() -> None:
    defs = json.loads(PROTOCOL_SCHEMA.read_text())["$defs"]

    assert "JournalEntry" in defs
    assert not {"Investigation", "Incident", "Disappearance", "Fact", "Knower"} & defs.keys()
