from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from simile.cli import create_cli
from simile.llm import CallRecord, Usage
from simile.llm.provider import RateLimit
from simile.memory import MemoryStore
from simile.news import NewsStore
from simile.schema import (
    Baseline,
    Conversation,
    Flag,
    FlagKind,
    InteractionEvent,
    Line,
    Memory,
    MemoryKind,
    NewsItem,
    Relationship,
)
from simile.tools import NoRun, RecordStore, load_run

START = datetime(2026, 1, 1, 9, tzinfo=UTC)
runner = CliRunner()


def at(minutes: float) -> datetime:
    return START + timedelta(minutes=minutes)


def memory(minutes: float, kind: MemoryKind = MemoryKind.CONVERSATION, **fields: object) -> Memory:
    return Memory.model_validate(
        {
            "owner": "ada",
            "kind": kind,
            "content": f"At {minutes}.",
            "salience": 0.5,
            "valence": 0.0,
            "timestamp": at(minutes),
        }
        | fields
    )


def flag(id: str, created: float, resolved: float | None = None) -> Flag:
    return Flag(
        id=id,
        kind=FlagKind.DEBT,
        owner="ada",
        about="bo",
        description="a fiver",
        created=at(created),
        resolved=None if resolved is None else at(resolved),
    )


def event(minutes: float) -> InteractionEvent:
    return InteractionEvent(
        actor="bo",
        target="ada",
        action="lent a fiver",
        aspects=["like"],
        valence=0.5,
        magnitude=0.5,
        timestamp=at(minutes),
    )


def record(**fields: object) -> CallRecord:
    defaults: dict[str, object] = {
        "purpose": "conversation",
        "model": "haiku",
        "provider": "claude-code",
        "started_at": 0.0,
        "queued_ms": 5.0,
        "latency_ms": 900.0,
        "ttft_ms": 600.0,
        "usage": Usage(
            input_tokens=10,
            output_tokens=20,
            thinking_tokens=12,
            cache_read_tokens=300,
            model="claude-haiku-4-5",
            rate_limit=RateLimit(
                "allowed", "five_hour", 0.25, windows={"five_hour": 0.25, "seven_day": 0.6}
            ),
        ),
        "error": None,
    }
    return CallRecord(**(defaults | fields))


def relationship(like: float) -> Relationship:
    return Relationship(
        owner="ada",
        about="bo",
        like=like,
        trust=0.5,
        respect=0.5,
        familiarity=0.1,
        baseline=Baseline(like=0.5, trust=0.5, respect=0.5),
    )


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = tmp_path / "simile.db"
    line = Line(id=1, conversation_id="c1", speaker="ada", text="Hi.", timestamp=at(3), duration=1)
    talk = Conversation(
        id="c1", participants=["ada", "bo"], started=at(3), ended=at(4), lines=[line]
    )
    item = NewsItem(
        id="n1", title="Bees", url="https://example.com/n1", summary="", published=at(-90)
    )
    with MemoryStore(path) as memories, NewsStore(path) as news, RecordStore(path) as store:
        news.add([item, item.model_copy(update={"id": "n2"})])
        memories.add(
            memory(-5),
            memory(5, topics=["bees"]),
            memory(6, MemoryKind.NEWS, news_id="n1"),
            memory(70),
            flag("old", -100, resolved=10),
            flag("new", 20),
            flag("later", 90),
            event(-1),
            event(7),
        )
        run = store.begin(START, 10, ["bo", "ada"])
        store.add(
            run,
            samples=[(at(m), "ada", "park", "park", "idle") for m in range(61)],
            conversations=[talk],
            calls=[(at(4), record()), (at(5), record(purpose="", error="LLMError: nope"))],
            relationships=("start", [relationship(0.5)]),
        )
        store.add(run, relationships=("end", [relationship(0.6)]))
        store.end(run, at(60))
    return path


def test_loads_the_recording_and_what_r2_stored_during_the_run(database: Path) -> None:
    run = load_run(database)

    assert (run.id, run.npcs, run.speed) == (1, ["ada", "bo"], 10)
    assert (run.started, run.ended) == (START, at(60))
    assert run.real_seconds is not None and run.real_seconds >= 0
    assert len(run.samples) == 60
    assert [c.id for c in run.conversations] == ["c1"]
    assert run.start["ada", "bo"].like == 0.5
    assert run.end["ada", "bo"].like == 0.6
    assert [m.content for m in run.memories] == ["At 5.", "At 6."]
    assert [f.id for f in run.flags_opened] == ["new"]
    assert [f.id for f in run.flags_resolved] == ["old"]
    assert [e.timestamp for e in run.events] == [at(7)]
    assert list(run.news) == ["n1"]
    assert run.news_items == 2


def test_reads_each_llm_call(database: Path) -> None:
    first, failed = load_run(database).calls

    assert first.time == at(4)
    assert (first.purpose, first.model, first.provider) == (
        "conversation",
        "claude-haiku-4-5",
        "claude-code",
    )
    assert (first.tokens_in, first.tokens_out, first.thinking_tokens) == (310, 20, 12)
    assert (first.latency_ms, first.ttft_ms, first.queued_ms) == (900.0, 600.0, 5.0)
    assert first.rate_limit == {
        "status": "allowed",
        "window": "five_hour",
        "utilization": 0.25,
        "resets_at": None,
        "windows": {"five_hour": 0.25, "seven_day": 0.6},
    }
    assert (failed.purpose, failed.error) == ("call", "LLMError: nope")


def test_a_run_that_never_finished_ends_at_its_last_sample(tmp_path: Path) -> None:
    path = tmp_path / "simile.db"
    with RecordStore(path) as store:
        run = store.begin(START, 1, ["ada"])
        store.add(run, samples=[(at(m), "ada", "home", "house_1", "home") for m in range(30)])

    recorded = load_run(path)

    assert recorded.ended == at(29)
    assert recorded.real_seconds is None
    assert len(recorded.samples) == 30


def test_says_when_there_is_no_such_run(tmp_path: Path, database: Path) -> None:
    empty = tmp_path / "empty.db"
    MemoryStore(empty).close()

    with pytest.raises(NoRun, match="No runs recorded in .*SIMILE_RECORD=1"):
        load_run(empty)
    with pytest.raises(NoRun, match="No run 7 in .*Recorded runs: 1."):
        load_run(database, 7)


def test_the_report_command_prints_the_latest_run(database: Path) -> None:
    result = runner.invoke(create_cli(), ["report", "--db", str(database)])

    assert result.exit_code == 0, result.output
    assert result.output.startswith("# Soak report: run 1\n")
    assert "| ada–bo | 1 | 1 |" in result.output


def test_the_report_command_reads_simile_db(
    database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SIMILE_DB", str(database))

    result = runner.invoke(create_cli(), ["report", "--run", "1"])

    assert result.exit_code == 0, result.output
    assert "# Soak report: run 1" in result.output


def test_the_report_command_fails_without_a_recording(tmp_path: Path) -> None:
    missing = runner.invoke(create_cli(), ["report", "--db", str(tmp_path / "nope.db")])
    empty = tmp_path / "empty.db"
    MemoryStore(empty).close()
    unrecorded = runner.invoke(create_cli(), ["report", "--db", str(empty)])

    assert missing.exit_code == 1
    assert "No database at" in missing.output
    assert not (tmp_path / "nope.db").exists()
    assert unrecorded.exit_code == 1
    assert "No runs recorded" in unrecorded.output
