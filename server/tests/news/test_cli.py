from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from simile.cli import create_cli
from simile.news import NewsStore, parse

FeedServer = Any

FIXTURES = Path(__file__).parent / "fixtures"

runner = CliRunner()


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
