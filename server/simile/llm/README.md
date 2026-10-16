# simile.llm

Every LLM call in Simile goes through `LLMClient`. By default it drives the local Claude Code CLI on
the user's subscription login through the Claude Agent SDK. Never the Claude API.

## Calling it

```python
from simile.llm import LLMClient, Message, Model

llm = request.app.state.llm  # the server's shared client, or LLMClient() in a script

async for chunk in llm.stream(
    "Good morning!", system=mara_persona, purpose="player-reply", priority=1
):
    send_to_client(chunk)

summary = await llm.complete(transcript, system=summariser, purpose="summary")

events = await llm.structured(transcript, Extraction, model=Model.SONNET, purpose="extract")
```

- `prompt` is a string or a list of `Message(role, content)` ending with a user message. Claude
  Code takes one user message per turn, so earlier turns are folded into it as
  `<earlier_turns>`.
- `model` is `Model.HAIKU` (the default), `Model.SONNET`, `Model.HAIKU_4_5`, `Model.HAIKU_5_5`, or
  any model name or alias `claude --model` accepts. Each module's config names its model (see
  *Which model* below).
- `structured(prompt, schema)` adds the JSON Schema of a pydantic model to the system prompt,
  validates the reply, and retries once with the validation error before raising
  `StructuredOutputError`.
- At most `max_concurrency` calls (default 4) run at once. The rest wait for a slot, and a freed
  slot goes to the highest `priority` waiting (default 0), then first come first served. Player
  replies pass `priority=1` so they don't queue behind NPC chatter, and the last `reserved` (1)
  free slot only goes to a call with a priority above 0, so a reply never waits for a reflection
  that holds a slot for 10 seconds or more.
- Every failure raises `LLMError`: a usage limit, the CLI crashing or not found, a reply cut short,
  or Claude Code not confirming that it bills the Claude subscription.
- Leaving a stream early (`break`, or cancelling the task) interrupts the call, so it stops using
  the subscription and frees its slot within about a second. Wrap the stream in
  `contextlib.aclosing` when you `break`, so that happens straight away rather than when the
  generator is garbage collected.

## Warm processes

Starting Claude Code takes about half a second before a call can begin. `llm.warm(system=...,
model=...)` starts a process for a later `stream` with that system prompt and model, so that call
skips the startup. Each process takes one call and is then closed, so no history builds up. One
that isn't used within `warm_for` (120 s, counted again from each `warm`) is closed, and so is the
least recently warmed when more than `max_warm` (2) are waiting. Warming costs no usage.
`llm.aclose()`, which the lifespan calls on shutdown, closes those still waiting. A warm process
that died is replaced by a fresh one before any text, and providers without `warm` (the fake ones)
ignore it.

```python
llm.warm(system=mara_persona, model="claude-haiku-4-5")  # when the player walks up to Mara
...
async for chunk in llm.stream(line, system=mara_persona, model="claude-haiku-4-5", priority=1):
    ...
```

## Thinking

`thinking={"type": "disabled"}` only reaches the model when the model allows it. Haiku 5.5, which
`haiku` resolves to, doesn't: Claude Code says "Thinking can't be turned off" for it and sends no
thinking setting, so the API's adaptive thinking applies. On a conversation prompt it thought for
about 200 to 250 tokens, 1 to 1.3 s before the first word; `--effort low` barely changed that. A
trivial prompt like the smoke test's doesn't trigger it. Haiku 4.5 (`claude-haiku-4-5`) honours
`disabled`, and its first word came 0.75 s after the request on the same prompt.

## Which model

Measured by I4 on an M2 Max, each call a fresh Claude Code process. Usage is Claude Code's
API-equivalent cost (`Usage.cost_usd`), the best guide there is to how fast a call uses up the
subscription's limits.

Medians, with the range in brackets:

| Purpose | Model | Calls | First word | Whole call | Thinking | Usage per call |
|---|---|--:|--:|--:|---|--:|
| `player-reply` (B5) | Haiku 4.5 | 7 | 0.7 s (0.6 to 1.8) | | none | $0.0015 |
| `conversation` (B2) | Haiku 5.5 | 56 | 2.8 s (1.5 to 5.0) | 3.1 s (1.7 to 5.2) | 31 of 56 lines, 185 tokens on average | $0.00033 |
| `conversation` | Haiku 4.5 | 14 | 1.4 s (1.3 to 2.4) | 2.2 s (1.8 to 3.2) | none | $0.0015 |
| `reflection` (B3) | Haiku 5.5 | 9 | 11.6 s (7.7 to 12.9) | 13.9 s (9.9 to 15.3) | about 1,850 tokens | $0.0016 |
| `reflection` | Haiku 4.5 | 2 | | 5.8 and 6.7 s | none | $0.0058 |
| `news-reaction` (B4) | Haiku 5.5 | 2 | 2.5 and 3.1 s | 3.0 and 3.4 s | about 250 tokens | $0.00047 |

Haiku 5.5 costs about a tenth of Haiku 4.5 per token, so even with its thinking a line costs about
a quarter as much and a reflection about a third. Only player
replies wait on the first word; B2 writes each line while the one before it plays, and B3 and B4
run in the background. The configs name the version rather than the `haiku` alias, so these
numbers hold when the alias moves.

These calls wrote one-hour cache entries. Five-minute ones (see *How Claude Code is called*) cut a
Haiku 5.5 line's prompt cost by about a third and its usage by about a fifth. Haiku 4.5's
player-reply prompts, at 1,100 to 1,500 tokens, aren't cached at all.

## Usage and latency

Every call produces a `CallRecord`: purpose, model, time queued for a slot, latency, time to first
token, `usage` and the error if it failed. `usage` has the token counts, the model that answered,
the time spent on the model API, its API-equivalent cost, and `rate_limit` when Claude Code
reported the subscription's usage limit during the call: status, window, reset time, and in
`windows` the fraction used of each window (`five_hour`, `seven_day`), to the nearest 1%.
`output_tokens` counts every token the model wrote, including `thinking_tokens`. The record is
logged at INFO on the `simile.llm` logger (in `extra={"llm_call": record}`) and passed to each
function in `client.listeners`. A listener that raises is logged and doesn't fail the call.

```
llm conversation model=claude-haiku-5-5 latency=3125ms ttft=2907ms queued=0ms tokens in=1668
(cache read 787, write 879) out=468 (thinking 403) api_cost=$0.00042 five_hour=27% seven_day=64%
```

```python
llm.listeners.append(lambda record: usage_this_hour.add(record.usage))
```

`uv run simile llm-smoke` makes one real call and prints its timings. `--runs 3` repeats it and
`--session` sends every run to one long-lived Claude Code session instead of a fresh process.

## Tests

Tests never call Claude. Give the client a `FakeProvider` with scripted replies:

```python
import asyncio

from simile.llm import FakeProvider, LLMClient, LLMError

resume = asyncio.Event()
fake = FakeProvider(
    [
        "Morning!",
        Mood(mood="glad", intensity=0.5),
        TimeoutError(),
        ["Well, ", "I ", resume, LLMError("usage limit reached")],
    ]
)
llm = LLMClient(fake)

assert await llm.complete("Hello") == "Morning!"
assert fake.requests[0].messages[-1].content == "Hello"
```

Each call takes the next reply:

- a string, streamed a word at a time;
- a pydantic model, sent as its JSON (for `structured`);
- an exception, raised before any text;
- a list of steps: strings are streamed as given, an `asyncio.Event` pauses the stream until the
  test sets it, and an exception fails the stream at that point;
- a function of the `Request` that returns a string, sync or async.

`FakeProvider(default="...")` answers every call after the script runs out.

With `SIMILE_LLM=fake`, the server's client answers every call with a few stock lines instead of
calling Claude. The test suite sets it for every test, so a test that starts the real app can't
reach Claude.

## How Claude Code is called

`ClaudeCodeProvider` runs one fresh `claude` process per call (the SDK's bundled CLI unless
`cli_path` says otherwise), configured as a plain text generator:

- the game's system prompt replaces Claude Code's, with no tools, MCP servers, skills, slash
  commands, settings files or `CLAUDE.md` (`--safe-mode`, `--setting-sources=`), one turn and
  thinking disabled where the model allows it (see *Thinking*);
- prompts are delivered verbatim, so `@path` or `/command` in player text does nothing;
- it runs in an empty temporary directory and doesn't save the session to disk;
- prompt-cache entries last five minutes (`CLAUDE_CODE_PROMPT_CACHE_TTL=5m`, whatever this
  process's environment says) rather than the hour Claude Code picks on a subscription, because
  one-hour writes cost more. No prompt is sent twice, so the only reads are of a system prompt used
  again within minutes, like the speaker's next line in a conversation;
- `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL` and every
  `CLAUDE_CODE_USE_*` backend switch (Bedrock, Vertex, Foundry, Anthropic AWS and Google Cloud,
  Mantle, gateway) are removed from this process's environment before every call;
- once connected, and before any prompt is sent, the account Claude Code reports must have the API
  provider `firstParty` and no API key source. That also catches a gateway forced by host policy;
- no text is passed on until the turn's `init` frame reports the API key source `none`.

`ClaudeCodeProvider.session(request)` is the only way to start a Claude Code process: it drops the
credentials and checks the account. `turn(sdk, request)` streams one turn. If the caller leaves
early, it interrupts the turn and reads the rest of it, so the same session can take another turn.
Warm processes and `SessionProvider` in `smoke.py` both build on these two.

Another backend implements `Provider`: an async generator of text chunks followed by one `Usage`.
