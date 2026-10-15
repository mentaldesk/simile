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
- `model` is `Model.HAIKU` (the default, for chatter and summaries), `Model.SONNET`, or any model
  name or alias `claude --model` accepts.
- `structured(prompt, schema)` adds the JSON Schema of a pydantic model to the system prompt,
  validates the reply, and retries once with the validation error before raising
  `StructuredOutputError`.
- At most `max_concurrency` calls (default 4) run at once. The rest wait for a slot, and a freed
  slot goes to the highest `priority` waiting (default 0), then first come first served. Player
  replies pass `priority=1` so they don't queue behind NPC chatter.
- Every failure raises `LLMError`: a usage limit, the CLI crashing or not found, a reply cut short,
  or Claude Code not confirming that it bills the Claude subscription.
- Leaving a stream early (`break`, or cancelling the task) interrupts the call, so it stops using
  the subscription and frees its slot within about a second. Wrap the stream in
  `contextlib.aclosing` when you `break`, so that happens straight away rather than when the
  generator is garbage collected.

## Usage and latency

Every call produces a `CallRecord`: purpose, model, time queued for a slot, latency, time to first
token, `usage` and the error if it failed. `usage` has the token counts, the model that answered,
the time spent on the model API, and `rate_limit` (status, window, utilisation and reset time)
when Claude Code reported the subscription's usage limit during the call. The record is logged at
INFO on the `simile.llm` logger (in `extra={"llm_call": record}`) and passed to each function in
`client.listeners`. A listener that raises is logged and doesn't fail the call.

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

## How Claude Code is called

`ClaudeCodeProvider` runs one fresh `claude` process per call (the SDK's bundled CLI unless
`cli_path` says otherwise), configured as a plain text generator:

- the game's system prompt replaces Claude Code's, with no tools, MCP servers, skills, slash
  commands, settings files or `CLAUDE.md` (`--safe-mode`, `--setting-sources=`), one turn and no
  extended thinking;
- prompts are delivered verbatim, so `@path` or `/command` in player text does nothing;
- it runs in an empty temporary directory and doesn't save the session to disk;
- `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL` and every
  `CLAUDE_CODE_USE_*` backend switch (Bedrock, Vertex, Foundry, Anthropic AWS and Google Cloud,
  Mantle, gateway) are removed from this process's environment before every call;
- once connected, and before any prompt is sent, the account Claude Code reports must have the API
  provider `firstParty` and no API key source. That also catches a gateway forced by host policy;
- no text is passed on until the turn's `init` frame reports the API key source `none`.

`ClaudeCodeProvider.session(request)` is the only way to start a Claude Code process: it drops the
credentials and checks the account. `turn(sdk, request)` streams one turn. If the caller leaves
early, it interrupts the turn and reads the rest of it, so the same session can take another turn.
A warm-session provider should build on these two, as `SessionProvider` in `smoke.py` does.

Another backend implements `Provider`: an async generator of text chunks followed by one `Usage`.
