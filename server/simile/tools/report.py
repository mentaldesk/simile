import json
import math
import re
import sqlite3
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from simile.behaviour.simulate import PLACES
from simile.schema import (
    PLAYER_ID,
    Conversation,
    Flag,
    InteractionEvent,
    Line,
    Memory,
    MemoryKind,
    NewsItem,
    Relationship,
)
from simile.tools.recorder import HOME, STREET

FAKE_PROVIDERS = frozenset({"canned", "fake"})
ASPECTS = ("like", "trust", "respect", "familiarity")
NEWS_WORDS = re.compile(r"\b(news|headlines?|articles?)\b")
STOPWORDS = frozenset(
    {"about", "after", "again", "being", "could", "every", "might", "other", "their", "there"}
    | {"these", "those", "under", "where", "which", "while", "would", "should", "years"}
)


class ReportConfig(BaseModel):
    """When the report calls something a problem."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    crowd_share: float = Field(
        default=0.7, description="Share of the NPCs at one place that counts as everyone there."
    )
    crowd_minutes: int = Field(
        default=15, description="Sim minutes of everyone at one place before it's a problem."
    )
    dominant_share: float = Field(
        default=0.5,
        description="Most of the time spent at places (not home or the street) one may take.",
    )
    min_place_minutes: int = Field(
        default=60, description="NPC minutes at places before judging which dominates."
    )
    min_conversations: int = Field(
        default=6, description="Conversations before judging who talks to whom, or catchphrases."
    )
    top_pairs: int = Field(
        default=3, description="How many pairs, each talking more than once, make 'the same few'."
    )
    top_pairs_share: float = Field(
        default=0.5, description="Share of conversations the same few pairs may have."
    )
    hub_share: float = Field(default=0.4, description="Share of conversations one NPC may be in.")
    repeated_share: float = Field(
        default=0.1, description="Share of lines that may repeat an earlier line word for word."
    )
    phrase_words: int = Field(default=4, description="Words in a repeated phrase.")
    catchphrase_share: float = Field(
        default=0.5, description="Share of conversations a phrase may come up in."
    )
    error_share: float = Field(default=0.05, description="Share of LLM calls that may fail.")
    rate_limit_warning: float = Field(
        default=0.8, description="Utilisation of a usage-limit window worth calling out."
    )


DEFAULT_CONFIG = ReportConfig()


@dataclass(frozen=True)
class Sample:
    time: datetime
    npc: str
    place: str
    location: str | None
    activity: str


@dataclass(frozen=True)
class Call:
    time: datetime
    purpose: str
    model: str
    provider: str
    latency_ms: float
    ttft_ms: float | None
    queued_ms: float
    tokens_in: int
    tokens_out: int
    cost_usd: float | None
    error: str | None
    rate_limit: dict[str, Any] | None

    @classmethod
    def parse(cls, when: float, data: str) -> "Call":
        record = json.loads(data)
        usage = record.get("usage") or {}
        return cls(
            time=datetime.fromtimestamp(when, UTC),
            purpose=record["purpose"] or "call",
            model=usage.get("model") or record["model"],
            provider=record["provider"],
            latency_ms=record["latency_ms"],
            ttft_ms=record["ttft_ms"],
            queued_ms=record["queued_ms"],
            tokens_in=sum(
                usage.get(key, 0)
                for key in ("input_tokens", "cache_read_tokens", "cache_creation_tokens")
            ),
            tokens_out=usage.get("output_tokens", 0),
            cost_usd=usage.get("cost_usd"),
            error=record["error"],
            rate_limit=usage.get("rate_limit"),
        )


@dataclass(frozen=True)
class RecordedRun:
    id: int
    started: datetime
    ended: datetime
    real_seconds: float | None
    speed: float
    npcs: list[str]
    samples: list[Sample]
    conversations: list[Conversation]
    calls: list[Call]
    start: dict[tuple[str, str], Relationship]
    end: dict[tuple[str, str], Relationship]
    memories: list[Memory]
    """R2 memories from during the run."""
    flags_opened: list[Flag]
    flags_resolved: list[Flag]
    events: list[InteractionEvent]
    news: dict[str, NewsItem]
    """The articles read during the run, by id."""
    news_items: int
    """Articles in the news table, read or not."""


class NoRun(LookupError):
    pass


def load_run(path: Path, run: int | None = None) -> RecordedRun:
    """A run recorded with `SIMILE_RECORD=1` in the database at `path`: the latest unless
    `run` says which. Opens it read-only."""
    db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        return _load(db, path, run)
    finally:
        db.close()


def _load(db: sqlite3.Connection, path: Path, run: int | None) -> RecordedRun:
    tables = {name for (name,) in db.execute("SELECT name FROM sqlite_master")}
    runs = (
        [id for (id,) in db.execute("SELECT id FROM record_runs ORDER BY id")]
        if "record_runs" in tables
        else []
    )
    if not runs:
        raise NoRun(f"No runs recorded in {path}. Record one with SIMILE_RECORD=1.")
    if run is None:
        run = runs[-1]
    elif run not in runs:
        raise NoRun(f"No run {run} in {path}. Recorded runs: {', '.join(map(str, runs))}.")

    def rows(table: str, query: str, *params: object) -> list[tuple[Any, ...]]:
        return db.execute(query, params).fetchall() if table in tables else []

    started, ended, wall_started, wall_ended, speed, npcs = db.execute(
        "SELECT started, ended, wall_started, wall_ended, speed, npcs FROM record_runs"
        " WHERE id = ?",
        (run,),
    ).fetchone()
    samples = [
        Sample(_time(when), npc, place, location, activity)
        for when, npc, place, location, activity in rows(
            "record_samples",
            "SELECT time, npc, place, location, activity FROM record_samples"
            " WHERE run = ? ORDER BY time, rowid",
            run,
        )
    ]
    calls = [
        Call.parse(when, data)
        for when, data in rows(
            "record_llm_calls",
            "SELECT time, data FROM record_llm_calls WHERE run = ? ORDER BY time, rowid",
            run,
        )
    ]
    if ended is None:
        ended = max([started, *(s.time.timestamp() for s in samples)])
    else:
        samples = [s for s in samples if s.time.timestamp() < ended]
    conversations = sorted(
        (
            Conversation.model_validate_json(data)
            for (data,) in rows(
                "record_conversations", "SELECT data FROM record_conversations WHERE run = ?", run
            )
        ),
        key=lambda c: c.started,
    )
    relationships: dict[str, dict[tuple[str, str], Relationship]] = {"start": {}, "end": {}}
    for phase, data in rows(
        "record_relationships", "SELECT phase, data FROM record_relationships WHERE run = ?", run
    ):
        rel = Relationship.model_validate_json(data)
        relationships[phase][rel.owner, rel.about] = rel
    window = (started, ended)
    memories = [
        Memory.model_validate_json(data)
        for (data,) in rows(
            "memories",
            "SELECT data FROM memories WHERE time BETWEEN ? AND ? ORDER BY time, id",
            *window,
        )
    ]
    flags_opened = [
        Flag.model_validate_json(data)
        for (data,) in rows(
            "flags",
            "SELECT data FROM flags WHERE created BETWEEN ? AND ? ORDER BY created",
            *window,
        )
    ]
    flags_resolved = [
        Flag.model_validate_json(data)
        for (data,) in rows(
            "flags",
            "SELECT data FROM flags WHERE resolved BETWEEN ? AND ? ORDER BY resolved",
            *window,
        )
    ]
    events = [
        InteractionEvent.model_validate_json(data)
        for (data,) in rows(
            "events", "SELECT data FROM events WHERE time BETWEEN ? AND ? ORDER BY time", *window
        )
    ]
    read = sorted({m.news_id for m in memories if m.kind is MemoryKind.NEWS and m.news_id})
    news = {
        item.id: item
        for item in (
            NewsItem.model_validate_json(data)
            for (data,) in rows(
                "news",
                "SELECT data FROM news WHERE id IN (SELECT value FROM json_each(?))",
                json.dumps(read),
            )
        )
    }
    news_items = rows("news", "SELECT COUNT(*) FROM news")
    return RecordedRun(
        id=run,
        started=_time(started),
        ended=_time(ended),
        real_seconds=None if wall_ended is None else wall_ended - wall_started,
        speed=speed,
        npcs=json.loads(npcs),
        samples=samples,
        conversations=conversations,
        calls=calls,
        start=relationships["start"],
        end=relationships["end"],
        memories=memories,
        flags_opened=flags_opened,
        flags_resolved=flags_resolved,
        events=events,
        news=news,
        news_items=news_items[0][0] if news_items else 0,
    )


def report(run: RecordedRun, config: ReportConfig = DEFAULT_CONFIG) -> str:
    """The run summarised as Markdown, with its problems first."""
    sections = [
        header(run),
        ["## Problems", "", *([f"- {p}" for p in problems(run, config)] or ["None found."])],
        conversation_section(run),
        drift_section(run),
        reflection_section(run),
        repetition_section(run, config),
        news_section(run),
        place_section(run),
        llm_section(run),
    ]
    return "\n\n".join("\n".join(section) for section in sections) + "\n"


def header(run: RecordedRun) -> list[str]:
    hours = (run.ended - run.started) / timedelta(hours=1)
    real = ""
    if run.real_seconds:
        achieved = (run.ended - run.started).total_seconds() / run.real_seconds
        real = f" in {_real(run.real_seconds)} ({achieved:.1f}x achieved)"
    providers = sorted({call.provider for call in run.calls}) or ["none called"]
    lines = [
        f"# Soak report: run {run.id}",
        "",
        f"{_stamp(run.started)} to {_stamp(run.ended, run.started)} UTC: {hours:.2f} sim hours "
        f"at {run.speed:g}x{real}. {len(run.npcs)} NPCs. LLM provider: {', '.join(providers)}.",
    ]
    if is_fake(run):
        lines += [
            "",
            "> **Fake provider.** Every LLM reply was one of L1's canned lines "
            "(`SIMILE_LLM=fake`), so the dialogue repeats itself, and B3's reflections and B4's "
            "news reactions, which need structured replies, stored nothing. Timings and token "
            "counts aren't Claude's.",
        ]
    return lines


def problems(run: RecordedRun, config: ReportConfig = DEFAULT_CONFIG) -> list[str]:
    """Signs of degenerate behaviour, as one sentence each."""
    fake = is_fake(run)
    expected = " Expected with canned lines." if fake else ""
    found = []
    talks = [c for c in run.conversations if c.lines]
    if not talks:
        found.append("Nobody talked.")

    need = crowd_size(run, config)
    crowded = crowded_minutes(run, need)
    if len(crowded) >= config.crowd_minutes:
        place, _ = Counter(crowded.values()).most_common(1)[0]
        found.append(
            f"At least {need} of {len(run.npcs)} NPCs were at one place for {len(crowded)} sim "
            f"minutes, mostly the {place}."
        )
    totals = Counter(s.place for s in run.samples if s.place not in (HOME, STREET))
    total = sum(totals.values())
    if total >= config.min_place_minutes:
        place, minutes = totals.most_common(1)[0]
        if minutes / total > config.dominant_share:
            found.append(
                f"The {place} had {minutes / total:.0%} of the time NPCs spent at places other "
                "than home and the street."
            )

    if len(talks) >= config.min_conversations:
        pairs = [
            (p, n)
            for p, n in Counter(pair_of(c) for c in talks).most_common(config.top_pairs)
            if n > 1
        ]
        share = sum(n for _, n in pairs) / len(talks)
        if share >= config.top_pairs_share:
            names = ", ".join(f"{_pair(p)} ({n})" for p, n in pairs)
            found.append(
                f"{share:.0%} of conversations were between {_n(len(pairs), 'pair')}: {names}."
            )
        held = Counter(npc for c in talks for npc in c.participants if npc in run.npcs)
        for npc, n in held.most_common():
            if n / len(talks) > config.hub_share:
                found.append(f"{npc} was in {n} of {len(talks)} conversations.")
        quiet = [npc for npc in run.npcs if npc not in held]
        if quiet:
            found.append(f"Never talked: {', '.join(quiet)}.")

    lines = spoken(run)
    repeats = repeated_lines(lines)
    if lines and repeats / len(lines) > config.repeated_share:
        found.append(
            f"{repeats} of {len(lines)} lines ({repeats / len(lines):.0%}) repeat an earlier line "
            f"word for word.{expected}"
        )
    loops = looping(talks)
    if loops:
        found.append(
            f"Conversations that repeat one of their own lines word for word: {len(loops)}, "
            f"e.g. `{loops[0].id}`.{expected}"
        )
    if len(talks) >= config.min_conversations:
        common = [
            (phrase, n)
            for phrase, n in phrases(talks, config.phrase_words).most_common(3)
            if n / len(talks) > config.catchphrase_share
        ]
        if common:
            said = "; ".join(f'"{phrase}" in {n}' for phrase, n in common)
            found.append(f"Catchphrases, out of {len(talks)} conversations: {said}.{expected}")

    reflected = [c for c in talks if any(p in run.npcs for p in c.participants)]
    if reflected and not _kind(run.memories, MemoryKind.CONVERSATION):
        found.append(
            f"B3 stored no memories, events or flags from {_n(len(reflected), 'conversation')}."
            + (" Expected under the fake provider, whose replies are never JSON." if fake else "")
        )
    reactions = [c for c in run.calls if c.purpose == "news-reaction"]
    if reactions and not _kind(run.memories, MemoryKind.NEWS):
        found.append(
            f"No news reactions were stored from {_n(len(reactions), 'call')}."
            + (" Expected under the fake provider." if fake else "")
        )

    failed = [c for c in run.calls if c.error and c.error != "cancelled"]
    if run.calls and len(failed) / len(run.calls) > config.error_share:
        top, n = Counter(c.error for c in failed).most_common(1)[0]
        found.append(
            f"{len(failed)} of {len(run.calls)} LLM calls failed, most often ({n}) with: {top}"
        )
    for window, limit in rate_limits(run).items():
        if limit.get("status") == "rejected":
            found.append(f"Claude Code rejected calls at the {window} usage limit.")
        elif (limit["max"] or 0) >= config.rate_limit_warning:
            found.append(f"Used {limit['max']:.0%} of the {window} usage limit.")
    return found


def conversation_section(run: RecordedRun) -> list[str]:
    talks = run.conversations
    lines = ["## Conversations", ""]
    if not talks:
        return [*lines, "None."]
    counts = [len(c.lines) for c in talks]
    minutes = [_minutes(c) for c in talks]
    pairs: dict[tuple[str, str], list[Conversation]] = defaultdict(list)
    for c in talks:
        pairs[pair_of(c)].append(c)
    npcs = len(run.npcs)
    possible = npcs * (npcs - 1) // 2
    player = sum(1 for c in talks if PLAYER_ID in c.participants)
    lines += [
        f"{_n(len(talks), 'conversation')}, {_n(sum(counts), 'line')}, between "
        f"{_n(len(pairs), 'pair')} "
        f"({possible} possible among the NPCs). Lines per conversation: {min(counts)} to "
        f"{max(counts)}, median {median(counts):g}. Sim minutes: median {median(minutes):.1f}, "
        f"longest {max(minutes):.1f}." + (f" {player} with the player." if player else ""),
        "",
        "| Pair | Conversations | Lines | Lines each | Minutes each | Most lines |",
        "|---|--:|--:|--:|--:|--:|",
    ]
    for p, held in sorted(pairs.items(), key=lambda item: (-len(item[1]), item[0])):
        said = [len(c.lines) for c in held]
        lines.append(
            f"| {_pair(p)} | {len(held)} | {sum(said)} | {sum(said) / len(held):.1f} | "
            f"{sum(_minutes(c) for c in held) / len(held):.1f} | {max(said)} |"
        )
    talked = {p for c in talks for p in c.participants}
    quiet = [npc for npc in run.npcs if npc not in talked]
    if quiet:
        lines += ["", f"Never talked: {', '.join(quiet)}."]
    return lines


def drift_section(run: RecordedRun) -> list[str]:
    lines = ["## Relationship drift", ""]
    keys = sorted(set(run.start) & set(run.end))
    if not keys:
        return [*lines, "No relationships were recorded."]
    deltas = {
        key: {a: _aspect(run.end[key], a) - _aspect(run.start[key], a) for a in ASPECTS}
        for key in keys
    }
    moved = [a for a in ASPECTS if any(abs(d[a]) >= 0.005 for d in deltas.values())]
    if not moved:
        return [*lines, f"No relationship among {len(keys)} changed by 0.01 or more."]
    owners = [npc for npc in run.npcs if any(o == npc for o, _ in keys)]
    abouts = run.npcs + sorted({b for _, b in keys} - set(run.npcs))
    lines.append(
        "End minus start, as each row feels about each column (R1 `as_of` the start and end), "
        "for the aspects that moved."
    )
    for aspect in moved:
        lines += [
            "",
            f"**{aspect.capitalize()}**",
            "",
            "| | " + " | ".join(abouts) + " |",
            "|---|" + "--:|" * len(abouts),
        ]
        for owner in owners:
            cells = []
            for about in abouts:
                d = deltas.get((owner, about), {}).get(aspect)
                cells.append("" if d is None else f"{d:+.2f}" if abs(d) >= 0.005 else "·")
            lines.append(f"| {owner} | " + " | ".join(cells) + " |")
    biggest = sorted(
        keys, key=lambda k: -sum(abs(deltas[k][a]) for a in ("like", "trust", "respect"))
    )[:10]
    lines += ["", "Largest shifts:", ""]
    for key in biggest:
        start, end = run.start[key], run.end[key]
        change = ", ".join(
            f"{a} {_aspect(start, a):.2f}→{_aspect(end, a):.2f}"
            for a in ASPECTS
            if abs(deltas[key][a]) >= 0.005
        )
        if change:
            lines.append(f"- {key[0]} about {key[1]}: {change}")
    return lines


def reflection_section(run: RecordedRun) -> list[str]:
    remembered = _kind(run.memories, MemoryKind.CONVERSATION)
    calls = [c for c in run.calls if c.purpose == "reflection"]
    lines = [
        "## Reflections and flags",
        "",
        f"Reflection calls: {len(calls)}. Stored: {len(remembered)} conversation memories, "
        f"{len(run.events)} interaction events. Flags: {len(run.flags_opened)} opened, "
        f"{len(run.flags_resolved)} resolved.",
    ]
    if run.flags_opened:
        lines += [
            "",
            "| Opened | Owner | About | Kind | Description | Resolved |",
            "|---|---|---|---|---|---|",
        ]
        for flag in run.flags_opened:
            resolved = f"{flag.resolved:%H:%M}" if flag.resolved else ""
            lines.append(
                f"| {flag.created:%H:%M} | {flag.owner} | {flag.about} | {flag.kind} | "
                f"{_cell(flag.description)} | {resolved} |"
            )
    older = [f for f in run.flags_resolved if f.created < run.started]
    if older:
        lines += ["", "Resolved from before the run:", ""]
        lines += [
            f"- {f.owner} about {f.about}: {f.kind}, {f.description} ({f.resolved:%H:%M})"
            for f in older
        ]
    return lines


def repetition_section(run: RecordedRun, config: ReportConfig = DEFAULT_CONFIG) -> list[str]:
    lines = ["## Repeated topics and phrases", ""]
    topics = Counter(t for m in _kind(run.memories, MemoryKind.CONVERSATION) for t in m.topics)
    if topics:
        lines.append(
            "Topics of conversation memories: "
            + ", ".join(f"{t} ({n})" for t, n in topics.most_common(10))
            + "."
        )
    else:
        lines.append("No conversation memories, so no topics.")
    said = spoken(run)
    repeated = [
        (text, n)
        for text, n in Counter(normalise(line.text) for line in said).most_common(5)
        if n > 1
    ]
    if repeated:
        lines += ["", "Lines said more than once:", ""]
        lines += [f'- {n}× "{text}"' for text, n in repeated]
    talks = [c for c in run.conversations if c.lines]
    common = [(p, n) for p, n in phrases(talks, config.phrase_words).most_common(8) if n > 1]
    if common:
        lines += [
            "",
            f"Phrases of {config.phrase_words} words in the most conversations:",
            "",
        ]
        lines += [f'- "{p}": {n} of {len(talks)}' for p, n in common]
    loops = looping(talks)
    if loops:
        lines += [
            "",
            f"Conversations that repeat one of their own lines: {len(loops)} of {len(talks)}.",
        ]
    return lines


def news_section(run: RecordedRun) -> list[str]:
    read = _kind(run.memories, MemoryKind.NEWS)
    readers = {m.owner for m in read}
    calls = sum(1 for c in run.calls if c.purpose == "news-reaction")
    lines = [
        "## News",
        "",
        f"Articles in the news table: {run.news_items}. Read and rated: {len(read)}, by "
        f"{_n(len(readers), 'NPC')}, from {_n(calls, 'news-reaction call')}.",
    ]
    if not run.news_items:
        lines.append("Nothing to read: `SIMILE_NEWS=1` fetches the feed.")
    said = spoken(run)
    mentions = [line for line in said if NEWS_WORDS.search(line.text.lower())]
    if said:
        talks = {line.conversation_id for line in mentions}
        lines += [
            "",
            f"{len(mentions)} of {len(said)} lines ({len(mentions) / len(said):.0%}), in "
            f"{_n(len(talks), 'conversation')}, mention the news, headlines or articles.",
        ]
    brought = article_mentions(run)
    lines += ["", f"Lines that bring up an article their speaker had read: {len(brought)}."]
    if brought:
        lines += [""] + [
            f'- {line.speaker}, {line.timestamp:%H:%M}: "{_cell(line.text)}" ({title})'
            for line, title in brought[:5]
        ]
    topics = Counter(t for m in read for t in m.topics)
    if topics:
        lines += [
            "",
            "Topics of what they read: "
            + ", ".join(f"{t} ({n})" for t, n in topics.most_common(8))
            + ".",
        ]
    return lines


def place_section(run: RecordedRun) -> list[str]:
    lines = ["## Time per location", ""]
    if not run.samples:
        return [*lines, "No samples."]
    seen = {s.place for s in run.samples}
    places = [p for p in PLACES if p in seen] + sorted(seen - set(PLACES))
    minutes: dict[str, Counter[str]] = defaultdict(Counter)
    asleep: Counter[str] = Counter()
    for s in run.samples:
        minutes[s.npc][s.place] += 1
        if s.activity == "sleep":
            asleep[s.npc] += 1
    held: Counter[str] = Counter()
    talking: Counter[str] = Counter()
    for c in run.conversations:
        held.update(c.participants)
        talking.update(dict.fromkeys(c.participants, _minutes(c)))
    lines += [
        "Sim minutes each NPC spent in each place, sampled once a sim minute. Other people's "
        "houses count as street, as in B1's fast-forward. Talking is the length of their "
        "conversations.",
        "",
        "| NPC | " + " | ".join(places) + " | Asleep | Talking | Conversations |",
        "|---|" + "--:|" * (len(places) + 3),
    ]
    for npc in run.npcs:
        cells = [_count(minutes[npc][p]) for p in places]
        cells += [_count(asleep[npc]), f"{talking[npc]:.1f}" if talking[npc] else "·"]
        lines.append(f"| {npc} | " + " | ".join([*cells, _count(held[npc])]) + " |")
    peaks = {place: max(n.values(), default=0) for place, n in _at_places(run).items()}
    lines.append(
        "| **Most at once** | "
        + " | ".join("" if p in (HOME, STREET) else _count(peaks.get(p, 0)) for p in places)
        + " | | | |"
    )
    return lines


def llm_section(run: RecordedRun) -> list[str]:
    lines = ["## LLM usage", ""]
    if not run.calls:
        return [*lines, "No calls."]
    hours = max((run.ended - run.started) / timedelta(hours=1), 1e-9)
    tokens_in = sum(c.tokens_in for c in run.calls)
    tokens_out = sum(c.tokens_out for c in run.calls)
    costs = [c.cost_usd for c in run.calls if c.cost_usd is not None]
    lines.append(
        f"{len(run.calls)} calls ({len(run.calls) / hours:.0f} per sim hour), {tokens_in:,} "
        f"tokens in and {tokens_out:,} out ({(tokens_in + tokens_out) / hours:,.0f} per sim hour)."
        + (
            f" ${sum(costs):.2f} if it were billed per call on the API; the subscription isn't."
            if costs
            else ""
        )
    )
    groups: dict[tuple[str, str], list[Call]] = defaultdict(list)
    for call in run.calls:
        groups[call.purpose, call.model].append(call)
    lines += [
        "",
        "| Purpose | Model | Calls | Failed | Tokens in | Tokens out | Latency p50 | p95 | "
        "First token p50 | Queued p95 |",
        "|---|---|--:|--:|--:|--:|--:|--:|--:|--:|",
    ]
    for (purpose, model), calls in sorted(groups.items(), key=lambda item: -len(item[1])):
        latency = [c.latency_ms for c in calls]
        ttft = [c.ttft_ms for c in calls if c.ttft_ms is not None]
        failed = sum(1 for c in calls if c.error and c.error != "cancelled")
        cancelled = sum(1 for c in calls if c.error == "cancelled")
        lines.append(
            f"| {purpose} | {model} | {len(calls)} | {failed}"
            + (f" (+{cancelled} cancelled)" if cancelled else "")
            + f" | {sum(c.tokens_in for c in calls):,} | {sum(c.tokens_out for c in calls):,} | "
            f"{_ms(percentile(latency, 0.5))} | {_ms(percentile(latency, 0.95))} | "
            f"{_ms(percentile(ttft, 0.5))} | "
            f"{_ms(percentile([c.queued_ms for c in calls], 0.95))} |"
        )
    errors = Counter(c.error for c in run.calls if c.error and c.error != "cancelled")
    if errors:
        lines += ["", "Errors:", ""]
        lines += [f"- {n}× {_cell(error)}" for error, n in errors.most_common(5)]
    limits = rate_limits(run)
    lines.append("")
    if not limits:
        lines.append("Rate limits: none reported.")
    for window, limit in limits.items():
        last = limit.get("utilization")
        resets = limit.get("resets_at")
        lines.append(
            f"Rate limit {window}: last {limit.get('status')}"
            + (f" at {last:.0%}" if last is not None else "")
            + (f", at most {limit['max']:.0%}" if limit["max"] is not None else "")
            + (f", resets {_time(resets):%Y-%m-%d %H:%M} UTC" if resets else "")
            + "."
        )
    return lines


def is_fake(run: RecordedRun) -> bool:
    return any(call.provider in FAKE_PROVIDERS for call in run.calls)


def pair_of(conversation: Conversation) -> tuple[str, str]:
    a, b, *_ = sorted(conversation.participants)
    return a, b


def spoken(run: RecordedRun) -> list[Line]:
    return sorted((line for c in run.conversations for line in c.lines), key=_line_order)


def normalise(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", text.lower().replace("’", "'")))


def repeated_lines(lines: Iterable[Line]) -> int:
    """How many lines repeat an earlier one word for word."""
    seen: set[str] = set()
    repeats = 0
    for line in lines:
        text = normalise(line.text)
        repeats += text in seen
        seen.add(text)
    return repeats


def looping(conversations: Iterable[Conversation]) -> list[Conversation]:
    """Conversations that repeat one of their own lines word for word."""
    return [
        c for c in conversations if len({normalise(line.text) for line in c.lines}) < len(c.lines)
    ]


def phrases(conversations: Iterable[Conversation], words: int) -> Counter[str]:
    """How many conversations each run of `words` words comes up in."""
    found: Counter[str] = Counter()
    for c in conversations:
        grams = set()
        for line in c.lines:
            said = normalise(line.text).split()
            grams.update(" ".join(said[i : i + words]) for i in range(len(said) - words + 1))
        found.update(grams)
    return found


def crowd_size(run: RecordedRun, config: ReportConfig = DEFAULT_CONFIG) -> int:
    return max(2, math.ceil(config.crowd_share * len(run.npcs)))


def crowded_minutes(run: RecordedRun, need: int) -> dict[datetime, str]:
    """The sampled minutes when at least `need` NPCs were at one place, and where."""
    crowded = {}
    for place, at in _at_places(run).items():
        for when, n in at.items():
            if n >= need:
                crowded[when] = place
    return crowded


def article_mentions(run: RecordedRun) -> list[tuple[Line, str]]:
    """Lines that bring up an article their speaker had read: one of its topics, or two of its
    title's longer words."""
    read: dict[str, list[tuple[Memory, NewsItem | None]]] = defaultdict(list)
    for memory in _kind(run.memories, MemoryKind.NEWS):
        read[memory.owner].append((memory, run.news.get(memory.news_id or "")))
    found = []
    for line in spoken(run):
        text = normalise(line.text)
        words = set(text.split())
        for memory, item in read.get(line.speaker, []):
            if memory.timestamp > line.timestamp:
                continue
            title = item.title if item else memory.content
            keywords = {w for w in normalise(title).split() if len(w) >= 5} - STOPWORDS
            topics = [normalise(t) for t in memory.topics if len(t) >= 4]
            if any(t and f" {t} " in f" {text} " for t in topics) or len(keywords & words) >= 2:
                found.append((line, title))
                break
    return found


def rate_limits(run: RecordedRun) -> dict[str, dict[str, Any]]:
    """The last rate-limit report for each usage window, with the highest utilisation seen."""
    limits: dict[str, dict[str, Any]] = {}
    for call in run.calls:
        if not call.rate_limit:
            continue
        window = call.rate_limit.get("window") or "unknown"
        used = call.rate_limit.get("utilization")
        highest = limits.get(window, {}).get("max")
        limits[window] = {
            **call.rate_limit,
            "max": max((u for u in (used, highest) if u is not None), default=None),
        }
    return limits


def percentile(values: Sequence[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(math.ceil(p * len(ordered)) - 1, 0)]


def _at_places(run: RecordedRun) -> dict[str, Counter[datetime]]:
    """How many NPCs were at each place other than home and the street, by sampled minute."""
    at: dict[str, Counter[datetime]] = defaultdict(Counter)
    for s in run.samples:
        if s.place not in (HOME, STREET):
            at[s.place][s.time] += 1
    return at


def _kind(memories: Iterable[Memory], kind: MemoryKind) -> list[Memory]:
    return [m for m in memories if m.kind is kind]


def _aspect(rel: Relationship, aspect: str) -> float:
    return getattr(rel, aspect)


def _minutes(conversation: Conversation) -> float:
    end = conversation.ended or (
        conversation.lines[-1].timestamp if conversation.lines else conversation.started
    )
    return (end - conversation.started) / timedelta(minutes=1)


def _line_order(line: Line) -> tuple[datetime, int]:
    return line.timestamp, line.id


def _pair(pair: tuple[str, str]) -> str:
    return "–".join(pair)


def _time(epoch: float) -> datetime:
    return datetime.fromtimestamp(epoch, UTC)


def _stamp(when: datetime, since: datetime | None = None) -> str:
    return f"{when:%H:%M}" if since and since.date() == when.date() else f"{when:%Y-%m-%d %H:%M}"


def _n(count: int, noun: str) -> str:
    return f"{count} {noun}" + ("" if count == 1 else "s")


def _real(seconds: float) -> str:
    return f"{seconds:.0f} real seconds" if seconds < 60 else f"{seconds / 60:.1f} real minutes"


def _count(n: int) -> str:
    return str(n) if n else "·"


def _ms(ms: float | None) -> str:
    if ms is None:
        return "-"
    return f"{ms:.0f} ms" if ms < 1000 else f"{ms / 1000:.1f} s"


def _cell(text: str, limit: int = 160) -> str:
    text = " ".join(text.split()).replace("|", "\\|")
    return text if len(text) <= limit else text[: limit - 1] + "…"
