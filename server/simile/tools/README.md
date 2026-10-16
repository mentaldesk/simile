# simile.tools

Tools for watching how the village behaves. D1's soak test records a run and `simile report`
summarises it.

## Recording a run

```bash
cd server && SIMILE_RECORD=1 uv run simile headless --speed 10 --duration 2
```

With `SIMILE_RECORD=1`, `simile headless` or `simile serve` records the run in the database
(`$SIMILE_DB`, or `server/data/simile.db`), in its own `record_*` tables:

- where each NPC is and what they're doing, once a sim minute;
- every conversation, with its lines, when it ends;
- every LLM call's L1 `CallRecord`: purpose, model, latency, tokens and rate limit;
- how every NPC feels about everyone they know, and strangers they'd `meet`, at the start and the
  end (R1 `as_of` then).

Recording starts once every module is up, after I3 has restored the village, and finishes after the
shutdown has ended the conversations going on and waited for their reflections. Rows are written
once a sim minute. With `SIMILE_DB=:memory:` nothing is recorded, since the report runs in another
process. Recording is off unless the variable is set, so tests and normal play don't pay for it.

## The report

```bash
cd server && uv run simile report            # the latest run; --run N for another, --db PATH
```

Markdown on stdout, with any problems first. It reads the recorded tables and what R2 stored during
the run: memories, interaction events and flags.

| Section | |
|---|---|
| Problems | Signs of degenerate behaviour: most of the village at one place, one place taking most of the time out, the same few pairs or one NPC in most conversations, NPCs who never talked, lines repeated word for word, conversations that loop, catchphrases, B3 or B4 storing nothing, failing LLM calls and usage limits. Thresholds are in `ReportConfig`. |
| Conversations | Per pair: how many, their lines and sim minutes. |
| Relationship drift | End minus start as a matrix, owner by row, for each aspect that moved, and the largest shifts. |
| Reflections and flags | What B3 stored, and every flag opened or resolved. |
| Repeated topics and phrases | Topics of conversation memories, lines said more than once, and 4-word phrases by how many conversations they come up in. |
| News | Articles read, lines mentioning the news, and lines that bring up an article the speaker read (one of its topics, or two of its title's longer words). |
| Time per location | Sim minutes per NPC per place, as B1's fast-forward counts places, plus time asleep and talking. |
| LLM usage | Calls, tokens and latency by purpose and model, errors, and the last usage-limit report. |

Under `SIMILE_LLM=fake` the report says so: every line is canned, so it flags repeated dialogue, and
B3's reflections never store anything.

A fast fake sim-day, about 15 real seconds:

```bash
cd server && SIMILE_RECORD=1 SIMILE_LLM=fake SIMILE_FRESH=1 SIMILE_DB=data/fake-day.db \
  uv run simile headless --speed 100000 --duration 24 > /dev/null
uv run simile report --db data/fake-day.db
```
