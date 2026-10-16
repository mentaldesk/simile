from datetime import UTC, datetime
from pathlib import Path

import pytest

from simile.news.config import DEFAULT_CONFIG
from simile.news.interest import interest, matching_tags, pulls, words
from simile.schema import CoreValue, NewsItem, Npc

V = CoreValue
MEI = Npc.model_validate_json(
    (Path(__file__).parents[1] / "fixtures" / "npcs" / "mei.json").read_text()
)


def npc(interests: list[str] | None = None, **values: float) -> Npc:
    scores = {value: values.get(value.value, 0.5) for value in CoreValue}
    return MEI.model_copy(update={"values": scores, "interests": interests or ["knitting"]})


def article(
    tags: list[str] | None = None, sentiment: float | None = None, **related: float
) -> NewsItem:
    return NewsItem.model_validate(
        {
            "id": "a",
            "title": "A",
            "url": "https://example.com/a",
            "summary": "",
            "published": datetime(2026, 3, 14, tzinfo=UTC),
            "values": {value: related.get(value.value, 0.0) for value in CoreValue},
            "tags": tags or [],
            "sentiment": sentiment,
        }
    )


def test_interest_follows_what_they_value() -> None:
    courts = article(justice=0.9, equality=0.5)
    festival = article(pleasure=0.9, connection=0.6)
    fair, fun = npc(justice=0.95, equality=0.8), npc(pleasure=0.95, connection=0.8)

    assert interest(fair, courts) > DEFAULT_CONFIG.min_interest > interest(fair, festival)
    assert interest(fun, festival) > DEFAULT_CONFIG.min_interest > interest(fun, courts)


def test_an_article_against_a_value_interests_those_who_hold_it() -> None:
    rules_are_for_breaking = article(obedience=0.9, freedom=0.7)
    stickler, shrug = npc(obedience=0.95), npc(obedience=0.5, freedom=0.5)

    assert interest(stickler, rules_are_for_breaking) > DEFAULT_CONFIG.min_interest
    assert interest(shrug, rules_are_for_breaking) == 0.0


def test_only_values_held_above_average_pull() -> None:
    reader = npc(knowledge=0.75, tradition=0.2)

    strongest, *rest = pulls(reader, article(knowledge=0.8, tradition=1.0))

    assert strongest == pytest.approx(0.4)
    assert set(rest) == {0.0}


def test_the_strongest_pull_counts_most() -> None:
    one = article(justice=0.8)
    two = article(justice=0.8, honesty=0.8)
    reader = npc(justice=1.0, honesty=1.0)

    assert interest(reader, two) == pytest.approx(interest(reader, one) * 1.5)


def test_a_tag_that_touches_their_interests_adds_a_little() -> None:
    reader = npc(["drone landing pad regulations", "neat filing"], security=0.9)
    plain = article(security=0.6, tags=["airspace"])
    tagged = article(security=0.6, tags=["airspace", "delivery drones"])

    assert matching_tags(reader, tagged) == ["delivery drones"]
    assert interest(reader, tagged) - interest(reader, plain) == pytest.approx(
        DEFAULT_CONFIG.tag_weight
    )


def test_tags_match_whole_words_give_or_take_a_plural() -> None:
    assert words("Bin and recycling rota, the art of it") == {"recycling", "rota"}
    assert words("Drones") == {"drone"}
    assert matching_tags(npc(["bin and recycling rota"]), article(tags=["earth rotation"])) == []


def test_optimists_lean_to_good_news_and_pessimists_to_bad() -> None:
    good, bad = article(knowledge=0.8, sentiment=0.8), article(knowledge=0.8, sentiment=-0.8)
    optimist = npc(knowledge=0.9, optimism=0.95)
    pessimist = npc(knowledge=0.9, optimism=0.05)

    assert interest(optimist, good) > interest(optimist, bad)
    assert interest(pessimist, bad) > interest(pessimist, good)
    assert interest(optimist, good) - interest(optimist, bad) < DEFAULT_CONFIG.tag_weight
