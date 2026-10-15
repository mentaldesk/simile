from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from simile.schema import Flag, FlagKind, Relationship
from simile.social import RelationshipConfig, describe

FIXTURES = Path(__file__).parents[1] / "fixtures"
NOW = datetime(2026, 3, 14, 9, tzinfo=UTC)


def relationship(*flags: Flag, **scores: Any) -> Relationship:
    return Relationship.model_validate(
        {
            "owner": "viktor",
            "about": "mei",
            "like": 0.5,
            "trust": 0.5,
            "respect": 0.5,
            "familiarity": 0.4,
            "baseline": {"like": 0.5, "trust": 0.5, "respect": 0.5},
            "flags": flags,
        }
        | scores
    )


def flag(kind: FlagKind, description: str, **changes: Any) -> Flag:
    return Flag.model_validate(
        {
            "id": f"flag_{kind}",
            "kind": kind,
            "owner": "viktor",
            "about": "mei",
            "description": description,
            "created": NOW,
        }
        | changes
    )


def test_the_issue_example() -> None:
    rel = relationship(
        flag(FlagKind.DEBT, "the bridge incident"), like=0.85, trust=0.35, familiarity=0.7
    )

    assert describe(rel, "Mei") == (
        "You like Mei a lot but don't trust them. You know them well. "
        "Mei still owes you for the bridge incident."
    )


@pytest.mark.parametrize(
    ("like", "phrase"),
    [
        (0.95, "You like Mei a lot."),
        (0.7, "You like Mei."),
        (0.5, "You have no strong feelings about Mei."),
        (0.35, "You dislike Mei."),
        (0.05, "You can't stand Mei."),
    ],
)
def test_like_bands(like: float, phrase: str) -> None:
    assert describe(relationship(like=like), "Mei").startswith(phrase)


@pytest.mark.parametrize(
    ("scores", "phrase"),
    [
        ({"trust": 0.9}, "You trust Mei completely."),
        ({"trust": 0.1}, "You don't trust Mei at all."),
        ({"respect": 0.9}, "You have great respect for Mei."),
        ({"respect": 0.3}, "You don't think much of Mei."),
        ({"respect": 0.1}, "You have no respect for Mei."),
        (
            {"like": 0.7, "trust": 0.7, "respect": 0.7},
            "You like Mei, trust them and respect them.",
        ),
        (
            {"like": 0.3, "trust": 0.7, "respect": 0.9},
            "You dislike Mei but trust them and have great respect for them.",
        ),
        (
            {"like": 0.8, "trust": 0.2, "respect": 0.7},
            "You like Mei a lot and respect them but don't trust them at all.",
        ),
    ],
)
def test_feelings_combine_into_one_sentence(scores: dict[str, float], phrase: str) -> None:
    assert describe(relationship(**scores), "Mei").startswith(phrase)


@pytest.mark.parametrize(
    ("familiarity", "phrase"),
    [
        (0.05, "You barely know them."),
        (0.4, "You know them a little."),
        (0.9, "You know them well."),
    ],
)
def test_familiarity_bands(familiarity: float, phrase: str) -> None:
    assert describe(relationship(familiarity=familiarity), "Mei").endswith(phrase)


@pytest.mark.parametrize(
    ("kind", "description", "sentence"),
    [
        (FlagKind.DEBT, "the bridge incident", "Mei still owes you for the bridge incident."),
        (FlagKind.GRUDGE, "the drones", "You hold a grudge against Mei over the drones."),
        (
            FlagKind.PROMISE,
            "fixing the espresso machine",
            "Mei made you a promise they haven't kept yet: fixing the espresso machine.",
        ),
        (
            FlagKind.BROKEN_PROMISE,
            "keeping quiet about the shop",
            "Mei broke a promise to you: keeping quiet about the shop.",
        ),
        (
            FlagKind.SAVED_LIFE,
            "pulling you out of the river",
            "Mei once saved your life: pulling you out of the river.",
        ),
        (
            FlagKind.SECRET,
            "she is selling the shop",
            "Mei trusted you with a secret: she is selling the shop.",
        ),
    ],
)
def test_every_flag_kind_is_described(kind: FlagKind, description: str, sentence: str) -> None:
    assert describe(relationship(flag(kind, description)), "Mei").endswith(sentence)


def test_open_flags_are_listed_oldest_first_and_resolved_ones_left_out() -> None:
    rel = relationship(
        flag(FlagKind.GRUDGE, "the drones", created=NOW + timedelta(days=1)),
        flag(FlagKind.PROMISE, "a new sign", resolved=NOW + timedelta(days=2)),
        flag(FlagKind.DEBT, "the bridge incident"),
    )

    assert describe(rel, "Mei") == (
        "You have no strong feelings about Mei. You know them a little. "
        "Mei still owes you for the bridge incident. "
        "You hold a grudge against Mei over the drones."
    )


def test_the_config_sets_the_bands() -> None:
    config = RelationshipConfig(mild_feeling=0.25, strong_feeling=0.45, well_known=0.3)

    assert describe(relationship(like=0.7, familiarity=0.4), "Mei", config=config) == (
        "You have no strong feelings about Mei. You know them well."
    )


def test_the_fixture_relationships() -> None:
    rels = TypeAdapter(list[Relationship]).validate_json(
        (FIXTURES / "relationships.json").read_bytes()
    )

    assert describe(rels[0], "Viktor") == (
        "You like Viktor, trust them and respect them. You know them well. "
        "Viktor still owes you for covering his coffees after the bridge incident."
    )
    assert describe(rels[4], "the newcomer") == (
        "You have no strong feelings about the newcomer. You barely know them."
    )


@pytest.mark.parametrize(
    ("description", "ending"),
    [
        ("the bridge incident.", "the bridge incident."),
        ("the bridge incident!", "the bridge incident!"),
        (" the bridge incident ", "the bridge incident."),
    ],
)
def test_a_flag_description_keeps_its_own_punctuation(description: str, ending: str) -> None:
    assert describe(relationship(flag(FlagKind.DEBT, description)), "Mei") == (
        "You have no strong feelings about Mei. You know them a little. "
        f"Mei still owes you for {ending}"
    )
