import json
from datetime import UTC, datetime, timedelta
from email.message import Message
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

import pytest
from typer.testing import CliRunner

from simile.cli import create_cli
from simile.llm import FakeProvider, LLMClient, LLMError
from simile.news import NewsStore, article, parse
from simile.schema import CoreValue, NewsItem

FeedServer = Any

FIXTURES = Path(__file__).parent / "fixtures"

runner = CliRunner()
NOW = datetime(2026, 10, 18, 9, tzinfo=UTC)


def story(n: int, source: str) -> NewsItem:
    return NewsItem(
        id=f"item-{n}",
        title=f"Story {n}",
        url=f"https://example.com/{n}",
        summary=f"What happened in story {n}.",
        published=NOW - timedelta(hours=n),
        source=source,
    )


def analysed(item: NewsItem, **fields: object) -> NewsItem:
    values = {value: 0.0 for value in CoreValue}
    return NewsItem.model_validate(
        {**item.model_dump(), "values": values, "tags": ["x"], "sentiment": 0, **fields}
    )


@pytest.fixture
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "simile.db"
    monkeypatch.setenv("SIMILE_DB", str(path))
    return path


@pytest.fixture
def feed_url(feed_server: FeedServer, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("SIMILE_NEWS_FEED", feed_server.url)
    return feed_server.url


def test_lists_stored_news_newest_first(database: Path, feed_xml: bytes) -> None:
    with NewsStore(database) as store:
        store.add(parse(feed_xml))

    result = runner.invoke(create_cli(), ["news", "-n", "2"])

    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [
        "2021-09-15 16:00  A new window to the early universe (and aliens?) (Big Think)",
        "                  https://bigthink.com/13-8/james-webb-telescope",
        "2021-09-15 15:00  The cruelest people in Russian history (Big Think)",
        "                  https://bigthink.com/politics-current-affairs/worst-cruelest-people-russian-history",
    ]


def test_says_when_nothing_is_stored() -> None:
    result = runner.invoke(create_cli(), ["news"])

    assert result.exit_code == 0, result.output
    assert "simile news --refresh" in result.output


def test_refresh_pulls_the_feed_once_and_then_only_changes(
    database: Path, feed_url: str, feed_server: FeedServer
) -> None:
    first = runner.invoke(create_cli(), ["news", "--refresh"])
    second = runner.invoke(create_cli(), ["news", "--refresh"])

    assert first.exit_code == 0, first.output
    assert f"5 new items from {feed_url}" in first.output
    assert "A new window to the early universe" in first.output
    assert second.exit_code == 0, second.output
    assert f"0 new items from {feed_url}" in second.output
    assert "A new window to the early universe" in second.output
    assert feed_server.requests[1]["If-None-Match"] == feed_server.etag


def test_refresh_reports_a_feed_it_cant_fetch(
    database: Path, feed_url: str, feed_server: FeedServer
) -> None:
    feed_server.errors["/feed"] = 503

    result = runner.invoke(create_cli(), ["news", "--refresh"])

    assert result.exit_code == 1
    assert f"Couldn't fetch {feed_url}" in result.output


def test_refresh_reads_every_feed_and_lists_their_sources(
    database: Path, feed_server: FeedServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    openai = feed_server.add("/openai", (FIXTURES / "openai.xml").read_bytes())
    rnz = feed_server.add("/rnz", (FIXTURES / "rnz.xml").read_bytes())
    monkeypatch.setenv("SIMILE_NEWS_FEED", f"{openai},{rnz}")

    result = runner.invoke(create_cli(), ["news", "--refresh", "-n", "20"])

    assert result.exit_code == 0, result.output
    assert f"10 new items from {openai}" in result.output
    assert f"10 new items from {rnz}" in result.output
    assert "(OpenAI News)" in result.output
    assert "(RNZ Sport Headlines)" in result.output


def test_refresh_says_how_many_items_each_feed_had_too_short_to_react_to(
    database: Path, feed_server: FeedServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    economist = feed_server.add("/economist", (FIXTURES / "economist.xml").read_bytes())
    rnz = feed_server.add("/rnz", (FIXTURES / "rnz.xml").read_bytes())
    monkeypatch.setenv("SIMILE_NEWS_FEED", f"{economist},{rnz}")

    result = runner.invoke(create_cli(), ["news", "--refresh", "-n", "20"])

    assert result.exit_code == 0, result.output
    assert f"5 new items from {economist}, 8 skipped as too short to react to" in result.output
    assert f"10 new items from {rnz}, 0 skipped as too short to react to" in result.output
    assert "  Politics" not in result.output
    assert "Cartoon: AI tsunami (The world this week)" in result.output


def test_refresh_lists_the_news_despite_a_feed_it_cant_fetch(
    database: Path, feed_server: FeedServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    rnz = feed_server.add("/rnz", (FIXTURES / "rnz.xml").read_bytes())
    broken = feed_server.add("/broken", b"")
    feed_server.errors["/broken"] = 503
    monkeypatch.setenv("SIMILE_NEWS_FEED", f"{broken},{rnz}")

    result = runner.invoke(create_cli(), ["news", "--refresh"])

    assert result.exit_code == 1
    assert f"Couldn't fetch {broken}: HTTP Error 503" in result.output
    assert f"10 new items from {rnz}" in result.output
    assert "(RNZ Sport Headlines)" in result.output


def test_lists_what_an_article_was_analysed_as(database: Path, feed_xml: bytes) -> None:
    newest = parse(feed_xml)[0]
    related = {CoreValue.KNOWLEDGE: 0.9, CoreValue.ADVENTURE: 0.6, CoreValue.OPEN_MINDEDNESS: 0.4}
    values = {value: related.get(value, 0.0) for value in CoreValue}
    with NewsStore(database) as store:
        store.add(parse(feed_xml))
        analysis = {"values": values, "tags": ["space", "aliens"], "sentiment": 0.4}
        store.update(NewsItem.model_validate({**newest.model_dump(), **analysis}))

    result = runner.invoke(create_cli(), ["news", "-n", "2"])

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[2] == (
        "                  knowledge 0.9, adventure 0.6, open_mindedness 0.4; tone +0.4; "
        "space, aliens"
    )
    assert lines[3] == "                  Feed's summary only"
    assert len(lines) == 8


def test_lists_which_articles_have_long_summaries_by_feed(database: Path) -> None:
    long = "The council voted for a barrier.\n\nWork starts in spring."
    items = [
        analysed(story(0, "OpenAI"), long_summary=long),
        analysed(story(1, "OpenAI")),
        analysed(story(2, "The Economist")),
        story(3, "The Economist"),
    ]
    with NewsStore(database) as store:
        store.add(items)
        store.no_text("item-1", "The site answered 403 Forbidden")

    result = runner.invoke(create_cli(), ["news"])

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert [lines[3], lines[7], lines[11]] == [
        "                  Long summary, 10 words",
        "                  Feed's summary only. The site answered 403 Forbidden",
        "                  Feed's summary only",
    ]
    assert lines[-1] == (
        "Long summaries of the analysed articles listed: OpenAI 1 of 2, The Economist 0 of 1"
    )


def test_summarise_writes_long_summaries_for_the_newest_articles(
    database: Path, monkeypatch: pytest.MonkeyPatch, pages: Any
) -> None:
    with NewsStore(database) as store:
        store.add([analysed(story(n, "OpenAI")) for n in range(3)])
    reply = {"tags": ["x"], "sentiment": 5, "long_summary": "Written from the page."}
    scores = {value.value: 0 for value in CoreValue}
    monkeypatch.setattr(
        "simile.news.cli.client",
        lambda: LLMClient(FakeProvider(default=json.dumps(reply | scores))),
    )
    forbidden = HTTPError("https://example.com/1", 403, "Forbidden", Message(), None)
    monkeypatch.setattr(article, "page", pages("word " * 200, {"https://example.com/1": forbidden}))

    result = runner.invoke(create_cli(), ["news", "--summarise", "2", "-n", "3"])

    assert result.exit_code == 0, result.output
    assert result.output.startswith(
        "Long summaries written: 1.\n"
        "Kept the feed's summary of 'Story 1': The site answered 403 Forbidden\n\n"
    )
    assert result.output.endswith("Long summaries of the analysed articles listed: OpenAI 1 of 3\n")


def test_summarise_says_when_a_call_fails(
    database: Path, monkeypatch: pytest.MonkeyPatch, pages: Any
) -> None:
    with NewsStore(database) as store:
        store.add([analysed(story(0, "OpenAI"))])
    monkeypatch.setattr(
        "simile.news.cli.client", lambda: LLMClient(FakeProvider([LLMError("usage limit")]))
    )
    monkeypatch.setattr(article, "page", pages("word " * 200))

    result = runner.invoke(create_cli(), ["news", "--summarise", "1"])

    assert result.exit_code == 1
    assert "Stopped, as a call failed: usage limit" in result.output


def test_analyse_says_what_it_couldnt(database: Path, feed_xml: bytes) -> None:
    with NewsStore(database) as store:
        store.add(parse(feed_xml))

    first = runner.invoke(create_cli(), ["news", "--analyse"])
    second = runner.invoke(create_cli(), ["news", "--analyse"])

    assert first.exit_code == 1
    assert first.output.startswith("Analysed 0 of 5 articles waiting, 0 with a long summary.\n")
    assert second.exit_code == 0, second.output
    assert second.output.startswith("Analysed 0 of 0 articles waiting, 0 with a long summary.\n")
