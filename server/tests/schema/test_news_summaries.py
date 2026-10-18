import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import TypeAdapter, ValidationError

from simile.news.bundled import BUNDLED, bundled
from simile.schema import Memory, NewsItem, export

FIXTURES = Path(__file__).parents[1] / "fixtures"
NEWS_ITEMS = json.loads((FIXTURES / "news_items.json").read_text())
MEMORIES = json.loads((FIXTURES / "memories.json").read_text())
READ = MEMORIES[3]

LONG_SUMMARY = (
    "Towns along the coast are drawing up rules for the delivery drones that now cross them "
    "dozens of times a day.\n\n"
    "Residents under the busiest routes want quiet hours and a say over where the drones fly. "
    "The couriers say fixed corridors would slow deliveries and push prices up.\n\n"
    "The first council to vote meets in May, and others are waiting to copy whatever it decides."
)
POINTS = [
    "the first council votes on the drone rules in May",
    "residents under the busiest routes want quiet hours",
]


def schema(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((export.JSON_DIR / f"{name}.json").read_text()))


@pytest.fixture(params=range(len(NEWS_ITEMS)), ids=lambda index: f"news_items[{index}]")
def item(request: pytest.FixtureRequest) -> dict[str, Any]:
    return NEWS_ITEMS[request.param]


def test_without_a_long_summary_it_is_unset_and_left_out(item: dict[str, Any]) -> None:
    parsed = NewsItem.model_validate(item)

    assert parsed.long_summary is None
    assert "long_summary" not in json.loads(parsed.model_dump_json())
    assert "long_summary" not in parsed.model_dump()


def test_a_long_summary_round_trips_after_the_summary(item: dict[str, Any]) -> None:
    parsed = NewsItem.model_validate(item | {"long_summary": LONG_SUMMARY})

    dumped = json.loads(parsed.model_dump_json())
    keys = list(dumped)

    assert dumped["long_summary"] == LONG_SUMMARY
    assert keys[keys.index("summary") + 1] == "long_summary"
    assert NewsItem.model_validate_json(parsed.model_dump_json()) == parsed


def test_a_long_summary_of_4000_characters_fits(item: dict[str, Any]) -> None:
    longest = "x" * 4000

    assert NewsItem.model_validate(item | {"long_summary": longest}).long_summary == longest


@pytest.mark.parametrize(
    ("long_summary", "match"),
    [("", "at least 1 character"), ("x" * 4001, "at most 4000 characters")],
)
def test_a_long_summary_is_not_empty_or_too_long(
    item: dict[str, Any], long_summary: str, match: str
) -> None:
    with pytest.raises(ValidationError, match=match):
        NewsItem.model_validate(item | {"long_summary": long_summary})


def test_the_exported_schema_allows_but_does_not_require_a_long_summary(
    item: dict[str, Any],
) -> None:
    validator = schema("NewsItem")

    assert validator.is_valid(item)
    assert validator.is_valid(item | {"long_summary": LONG_SUMMARY})
    assert not validator.is_valid(item | {"long_summary": ""})
    assert not validator.is_valid(item | {"long_summary": "x" * 4001})


def test_the_bundled_articles_rewrite_byte_for_byte() -> None:
    written = TypeAdapter(list[NewsItem]).dump_json(bundled(), indent=2) + b"\n"

    assert written == BUNDLED.read_bytes()


def test_without_points_a_memory_leaves_them_out() -> None:
    for data in MEMORIES:
        parsed = Memory.model_validate(data)

        assert parsed.points == []
        assert "points" not in json.loads(parsed.model_dump_json())


def test_points_round_trip_after_the_content() -> None:
    parsed = Memory.model_validate(READ | {"points": POINTS})

    dumped = json.loads(parsed.model_dump_json())
    keys = list(dumped)

    assert dumped["points"] == POINTS
    assert keys[keys.index("content") + 1] == "points"
    assert Memory.model_validate_json(parsed.model_dump_json()) == parsed


def test_up_to_three_points_of_240_characters_fit() -> None:
    longest = ["x" * 240] * 3

    assert Memory.model_validate(READ | {"points": longest}).points == longest


@pytest.mark.parametrize(
    ("points", "match"),
    [
        (POINTS * 2, "at most 3 items"),
        ([""], "at least 1 character"),
        (["x" * 241], "at most 240 characters"),
    ],
)
def test_points_are_few_and_short(points: list[str], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        Memory.model_validate(READ | {"points": points})


def test_the_exported_schema_allows_but_does_not_require_points() -> None:
    validator = schema("Memory")

    assert validator.is_valid(READ)
    assert validator.is_valid(READ | {"points": POINTS})
    assert not validator.is_valid(READ | {"points": POINTS * 2})
    assert not validator.is_valid(READ | {"points": ["x" * 241]})
