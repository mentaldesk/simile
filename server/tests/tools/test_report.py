import dataclasses
import itertools
from datetime import UTC, datetime, timedelta
from typing import Any

from simile.schema import (
    Aspect,
    Baseline,
    Conversation,
    Flag,
    FlagKind,
    Line,
    Memory,
    MemoryKind,
    NewsItem,
    Relationship,
)
from simile.tools.report import (
    Call,
    RecordedRun,
    Sample,
    article_mentions,
    conversation_section,
    drift_section,
    llm_section,
    news_section,
    percentile,
    place_section,
    problems,
    reflection_section,
    repetition_section,
    report,
)

START = datetime(2026, 1, 1, 9, tzinfo=UTC)
NPCS = ["ada", "bo", "cy", "di", "ed", "fi"]
ids = itertools.count(1)


def at(minutes: float) -> datetime:
    return START + timedelta(minutes=minutes)


def talk(a: str, b: str, *texts: str, start: float = 0.0) -> Conversation:
    key = f"{a}-{b}-{next(ids)}"
    lines = [
        Line(
            id=next(ids),
            conversation_id=key,
            speaker=(a, b)[i % 2],
            text=text,
            timestamp=at(start + i / 10),
            duration=3,
        )
        for i, text in enumerate(texts)
    ]
    return Conversation(
        id=key, participants=[a, b], started=at(start), ended=at(start + 1), lines=lines
    )


def memory(owner: str, kind: MemoryKind = MemoryKind.CONVERSATION, **fields: Any) -> Memory:
    defaults: dict[str, Any] = {
        "content": "We talked.",
        "salience": 0.5,
        "valence": 0.2,
        "timestamp": at(1),
    }
    return Memory(owner=owner, kind=kind, **(defaults | fields))


def call(purpose: str = "conversation", **fields: Any) -> Call:
    defaults: dict[str, Any] = {
        "time": at(1),
        "model": "claude-haiku-4-5",
        "provider": "claude-code",
        "latency_ms": 900.0,
        "ttft_ms": 700.0,
        "queued_ms": 0.0,
        "tokens_in": 1000,
        "tokens_out": 30,
        "thinking_tokens": 0,
        "cost_usd": None,
        "error": None,
        "rate_limit": None,
    }
    return Call(purpose=purpose, **(defaults | fields))


def spread(minutes: int = 60) -> list[Sample]:
    """Three NPCs at three places and the rest at home, for `minutes`."""
    out = {"ada": "coffee_shop", "bo": "park", "cy": "square"}
    return [
        Sample(at(m), npc, out.get(npc, "home"), out.get(npc), "idle")
        for m in range(minutes)
        for npc in NPCS
    ]


def rel(owner: str, about: str, **scores: float) -> Relationship:
    values = {"like": 0.5, "trust": 0.5, "respect": 0.5, "familiarity": 0.0} | scores
    return Relationship(
        owner=owner,
        about=about,
        baseline=Baseline(like=0.5, trust=0.5, respect=0.5),
        **values,
    )


def healthy() -> RecordedRun:
    pairs = [("ada", "bo"), ("cy", "di"), ("ed", "fi"), ("ada", "cy"), ("bo", "ed"), ("di", "fi")]
    talks = [
        talk(a, b, f"Hello {b}, lovely {i} morning.", f"Hello {a}, it is day {i} indeed.", start=i)
        for i, (a, b) in enumerate(pairs)
    ]
    return RecordedRun(
        id=1,
        started=START,
        ended=at(60),
        real_seconds=360.0,
        speed=10,
        npcs=NPCS,
        samples=spread(),
        conversations=talks,
        calls=[call(rate_limit={"status": "allowed", "window": "five_hour", "utilization": 0.3})],
        start={},
        end={},
        memories=[memory(c.participants[0], topics=["weather"]) for c in talks],
        flags_opened=[],
        flags_resolved=[],
        events=[],
        news={},
        news_items=0,
    )


def change(run: RecordedRun, **fields: Any) -> RecordedRun:
    return dataclasses.replace(run, **fields)


def test_a_healthy_run_has_no_problems() -> None:
    run = healthy()

    assert problems(run) == []
    assert "## Problems\n\nNone found." in report(run)


def test_most_of_the_village_at_one_place_is_a_problem() -> None:
    crowd = [
        Sample(at(m), npc, "coffee_shop" if npc != "fi" else "home", None, "idle")
        for m in range(20)
        for npc in NPCS
    ]

    found = problems(change(healthy(), samples=crowd))

    assert found == [
        "At least 5 of 6 NPCs were at one place for 20 sim minutes, mostly the coffee_shop.",
        "The coffee_shop had 100% of the time NPCs spent at places other than home and the street.",
    ]


def test_a_short_crowd_or_a_little_time_out_is_not_a_problem() -> None:
    crowd = [
        Sample(at(m), npc, "coffee_shop" if npc != "fi" else "home", None, "idle")
        for m in range(10)
        for npc in NPCS
    ]

    assert problems(change(healthy(), samples=crowd)) == []


def test_the_same_few_pairs_or_one_npc_talking_is_a_problem() -> None:
    talks = [
        *(talk("ada", "bo", f"Line {i} of ours.", start=i) for i in range(4)),
        *(talk("cy", "di", f"Another {i} of theirs.", start=i) for i in range(2)),
        talk("ada", "cy", "Something else entirely."),
        talk("ada", "di", "And one more thing."),
    ]
    memories = [memory(c.participants[0]) for c in talks]

    found = problems(change(healthy(), conversations=talks, memories=memories))

    assert "75% of conversations were between 2 pairs: ada–bo (4), cy–di (2)." in found
    assert "ada was in 6 of 8 conversations." in found
    assert "bo was in 4 of 8 conversations." in found
    assert "Never talked: ed, fi." in found


def test_repeated_lines_loops_and_catchphrases_are_problems() -> None:
    script = ("Morning! How are things?", "Not bad. And you?", "Morning! How are things?")
    talks = [talk(a, b, *script, start=i) for i, (a, b) in enumerate(itertools.pairwise(NPCS))]
    talks.append(talk("fi", "ada", "Morning! How are things with the bees?", start=6))
    run = change(healthy(), conversations=talks)

    found = problems(run)

    assert found[0] == "13 of 16 lines (81%) repeat an earlier line word for word."
    assert found[1].startswith("Conversations that repeat one of their own lines word for word: 5")
    assert found[2] == (
        'Catchphrases, out of 6 conversations: "morning how are things" in 6; '
        '"not bad and you" in 5.'
    )
    assert len(found) == 3
    fake = change(run, calls=[call(provider="canned")])
    assert all(p.endswith("Expected with canned lines.") for p in problems(fake)[:3])


def test_b3_storing_nothing_is_a_problem() -> None:
    run = change(healthy(), memories=[], calls=[call("reflection"), call("news-reaction")])

    assert problems(run) == [
        "B3 stored no memories, events or flags from 6 conversations.",
        "No news reactions were stored from 1 call.",
    ]
    fake = change(run, calls=[call("reflection", provider="canned")])
    assert problems(fake) == [
        "B3 stored no memories, events or flags from 6 conversations. Expected under the fake "
        "provider, whose replies are never JSON."
    ]


def test_nobody_talking_is_a_problem() -> None:
    assert problems(change(healthy(), conversations=[], memories=[])) == ["Nobody talked."]


def test_failing_calls_and_usage_limits_are_problems() -> None:
    calls = [
        *(call() for _ in range(17)),
        call(error="cancelled"),
        call(error="LLMError: usage limit reached"),
        call(error="LLMError: usage limit reached"),
        call(rate_limit={"status": "allowed_warning", "window": "five_hour", "utilization": 0.85}),
        call(rate_limit={"status": "rejected", "window": "seven_day", "utilization": 1.0}),
    ]

    assert problems(change(healthy(), calls=calls)) == [
        "2 of 22 LLM calls failed, most often (2) with: LLMError: usage limit reached",
        "Used 85% of the five_hour usage limit.",
        "Claude Code rejected calls at the seven_day usage limit.",
    ]


def test_drift_shows_what_moved_as_a_matrix() -> None:
    start = {("ada", "bo"): rel("ada", "bo"), ("bo", "ada"): rel("bo", "ada")}
    end = {
        ("ada", "bo"): rel("ada", "bo", like=0.7, familiarity=0.2),
        ("bo", "ada"): rel("bo", "ada", like=0.45, familiarity=0.2),
    }
    run = change(healthy(), npcs=["ada", "bo"], start=start, end=end)

    section = "\n".join(drift_section(run))

    assert "**Like**\n\n| | ada | bo |\n|---|--:|--:|\n| ada |  | +0.20 |\n| bo | -0.05 |  |" in (
        section
    )
    assert "**Familiarity**" in section
    assert "**Trust**" not in section
    assert "- ada about bo: like 0.50→0.70, familiarity 0.00→0.20" in section
    unchanged = drift_section(change(run, end=start))
    assert unchanged[-1] == "No relationship among 2 changed by 0.01 or more."


def test_lists_the_flags_opened_and_resolved() -> None:
    promise = Flag(
        id="f1",
        kind=FlagKind.PROMISE,
        owner="ada",
        about="bo",
        description="fix the fence by Friday",
        created=at(5),
        resolved=at(30),
    )
    grudge = Flag(
        id="f0",
        kind=FlagKind.GRUDGE,
        owner="cy",
        about="di",
        description="the parking spot",
        created=at(-600),
        resolved=at(40),
    )
    run = change(healthy(), flags_opened=[promise], flags_resolved=[promise, grudge])

    section = "\n".join(reflection_section(run))

    assert "Flags: 1 opened, 2 resolved." in section
    assert "| 09:05 | ada | bo | promise | fix the fence by Friday | 09:30 |" in section
    assert "- cy about di: grudge, the parking spot (09:40)" in section


def test_finds_lines_that_bring_up_an_article_the_speaker_read() -> None:
    item = NewsItem(
        id="n1",
        title="Village council approves new solar farm",
        url="https://example.com/n1",
        summary="",
        published=at(-60),
    )
    read = memory(
        "ada",
        MemoryKind.NEWS,
        content=f'I read "{item.title}" on the news terminal.',
        timestamp=at(10),
        topics=["solar power"],
        news_id="n1",
    )
    before = talk("ada", "bo", "Did you hear the council approved a solar farm?", start=5)
    after = talk(
        "ada",
        "bo",
        "Did you hear the council approved a solar farm?",
        "Yes, the council and their solar plans.",
        "Solar power is the future, mark my words.",
        "Did you see the news today?",
        start=20,
    )
    run = change(healthy(), conversations=[before, after], memories=[read], news={"n1": item})

    found = article_mentions(run)

    assert [(line.text, title) for line, title in found] == [
        ("Did you hear the council approved a solar farm?", item.title),
        ("Solar power is the future, mark my words.", item.title),
    ]
    section = "\n".join(news_section(change(run, news_items=12)))
    assert "Articles in the news table: 12. Read and rated: 1, by 1 NPC," in section
    assert "1 of 5 lines (20%), in 1 conversation, mention the news" in section
    assert "Lines that bring up an article their speaker had read: 2." in section
    assert "Topics of what they read: solar power (1)." in section


def test_summarises_llm_usage_by_purpose_and_model() -> None:
    resets = int(datetime(2026, 1, 1, 13, tzinfo=UTC).timestamp())
    limits = [
        {
            "status": "allowed",
            "window": "five_hour",
            "utilization": 0.4,
            "resets_at": resets,
            "windows": {"five_hour": 0.4, "seven_day": 0.6},
        },
        {
            "status": "allowed_warning",
            "window": "five_hour",
            "utilization": 0.43,
            "resets_at": resets,
            "windows": {"five_hour": 0.43, "seven_day": 0.61},
        },
    ]
    calls = [
        call(latency_ms=100.0, thinking_tokens=10),
        call(latency_ms=200.0, cost_usd=0.01),
        call(latency_ms=300.0, error="cancelled", ttft_ms=None),
        call(latency_ms=4000.0, error="LLMError: boom"),
        *(call(rate_limit=limit) for limit in limits),
        call(
            "reflection",
            model="claude-sonnet-5",
            tokens_in=3000,
            tokens_out=200,
            thinking_tokens=150,
            cost_usd=0.002,
        ),
    ]

    section = "\n".join(llm_section(change(healthy(), calls=calls)))

    assert "7 calls (7 per sim hour), 9,000 tokens in and 380 out, 160 of them thinking" in section
    assert "$0.01 if it were billed per call on the API" in section
    assert (
        "| conversation | claude-haiku-4-5 | 6 | 1 (+1 cancelled) | 6,000 | 180 | 10 | $0.0100 | "
        "300 ms | 4.0 s | 700 ms | 0 ms |"
    ) in section
    assert "| reflection | claude-sonnet-5 | 1 | 0 | 3,000 | 200 | 150 | $0.0020 |" in section
    assert "- 1× LLMError: boom" in section
    assert (
        "Usage limit five_hour: 40% at the first report, 43% at the last, at most 43%; last "
        "status allowed_warning; resets 2026-01-01 13:00 UTC."
    ) in section
    assert "Usage limit seven_day: 60% at the first report, 61% at the last, at most 61%." in (
        section
    )
    assert "Usage limits: none reported." in llm_section(change(healthy(), calls=[call()]))


def test_counts_minutes_per_place_and_talking() -> None:
    section = "\n".join(place_section(healthy()))

    assert "| NPC | home | coffee_shop | square | park | Asleep | Talking | Conversations |" in (
        section
    )
    assert "| ada | · | 60 | · | · | · | 2.0 | 2 |" in section
    assert "| **Most at once** |  | 1 | 1 | 1 | | | |" in section


def test_leaves_out_conversations_nobody_spoke_in() -> None:
    run = healthy()
    empty = Conversation(id="empty", participants=["ed", "fi"], started=at(50), ended=at(50))
    with_empty = change(run, conversations=[*run.conversations, empty])

    assert conversation_section(with_empty)[2] == conversation_section(run)[2] + (
        " Left out: 1 that ended before a line was said."
    )
    assert conversation_section(with_empty)[3:] == conversation_section(run)[3:]
    assert place_section(with_empty) == place_section(run)
    assert problems(with_empty) == []


def test_lists_tied_lines_and_phrases_in_order() -> None:
    script = ("Zulu yankee xray whiskey.", "Alpha bravo charlie delta.")
    run = change(healthy(), conversations=[talk("ada", "bo", *script, start=i) for i in range(2)])

    section = repetition_section(run)

    assert section[section.index("Lines said more than once:") + 2 :][:2] == [
        '- 2× "alpha bravo charlie delta"',
        '- 2× "zulu yankee xray whiskey"',
    ]
    assert section[-2:] == [
        '- "alpha bravo charlie delta": 2 of 2',
        '- "zulu yankee xray whiskey": 2 of 2',
    ]


def test_says_when_the_provider_was_fake() -> None:
    text = report(change(healthy(), calls=[call(provider="canned")]))

    assert "LLM provider: canned." in text
    assert "> **Fake provider.**" in text
    assert "**Fake provider.**" not in report(healthy())


def test_percentile_is_nearest_rank() -> None:
    assert percentile([], 0.5) is None
    assert percentile([3.0, 1.0, 2.0], 0.5) == 2.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.95) == 4.0
    assert percentile([5.0], 0.01) == 5.0


def test_aspects_cover_the_schema() -> None:
    from simile.tools.report import ASPECTS

    assert set(ASPECTS) == {a.value for a in Aspect} | {"familiarity"}
