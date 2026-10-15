# simile.llm

Every LLM call in Simile goes through `LLMClient`. By default it drives the local Claude Code CLI on
the user's subscription login through the Claude Agent SDK. Never the Claude API.

## Calling it

```python
from simile.llm import LLMClient, Message, Model

llm = request.app.state.llm  # the server's shared client, or LLMClient() in a script

async for chunk in llm.stream("Good morning!", system=mara_persona, purpose="player-reply"):
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
- At most `max_concurrency` calls (default 4) run at once. The rest wait for a slot.
- Calls that fail raise `LLMError` (usage limit, CLI failure, an API key in use).

## Usage and latency

Every call produces a `CallRecord`: purpose, model, time queued for a slot, latency, time to first
token, token usage, and the error if it failed. It's logged at INFO on the `simile.llm` logger
(the record is in `extra={"llm_call": record}`) and passed to each function in
`client.listeners`:

```python
llm.listeners.append(lambda record: usage_this_hour.add(record.usage))
```

`uv run simile llm-smoke` makes one real call and prints its timings. `--runs 3` repeats it and
`--session` sends every run to one long-lived Claude Code session instead of a fresh process.

## Tests

Tests never call Claude. Give the client a `FakeProvider` with scripted replies:

```python
from simile.llm import FakeProvider, LLMClient

fake = FakeProvider(["Morning!", Mood(mood="glad", intensity=0.5), TimeoutError()])
llm = LLMClient(fake)

assert await llm.complete("Hello") == "Morning!"
assert fake.requests[0].messages[-1].content == "Hello"
```

A reply is a string, a pydantic model (sent as its JSON, for `structured`), an exception to raise,
or a function of the `Request` returning a string, sync or async (handy for holding a call open
until the test releases it). `FakeProvider(default="...")` answers every call after the script runs
out. Replies stream a word at a time.

## How Claude Code is called

`ClaudeCodeProvider` runs one fresh `claude` process per call (the SDK's bundled CLI unless
`cli_path` says otherwise), configured as a plain text generator:

- the game's system prompt replaces Claude Code's, with no tools, MCP servers, skills, slash
  commands, settings files or `CLAUDE.md` (`--safe-mode`, `--setting-sources=`), one turn and no
  extended thinking;
- prompts are delivered verbatim, so `@path` or `/command` in player text does nothing;
- it runs in an empty temporary directory and doesn't save the session to disk;
- `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL` and the Bedrock/Vertex/Foundry
  switches are removed from this process's environment before every call, and a call fails if
  Claude Code reports any API key source other than `none`.

Another backend implements `Provider`: an async generator of text chunks followed by one `Usage`.
