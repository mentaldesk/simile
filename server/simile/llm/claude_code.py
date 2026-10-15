import logging
import os
import tempfile
from collections.abc import AsyncGenerator, AsyncIterator, Iterator, Sequence
from contextlib import aclosing, asynccontextmanager, contextmanager, suppress
from pathlib import Path
from typing import Any

import anyio
from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ClaudeSDKError,
    RateLimitEvent,
    ResultMessage,
    StreamEvent,
    SystemMessage,
)
from claude_agent_sdk import Message as SDKMessage

from simile.llm.provider import LLMError, Message, RateLimit, Request, Usage

logger = logging.getLogger("simile.llm")

API_CREDENTIALS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
)


def drop_api_credentials() -> None:
    """The CLI inherits our environment, and the SDK can add variables to it but not unset them."""
    for name in API_CREDENTIALS:
        os.environ.pop(name, None)


class ClaudeCodeProvider:
    """Plain text generation through the local Claude Code CLI on the user's subscription login."""

    name = "claude-code"

    def __init__(self, *, cli_path: str | Path | None = None, cwd: Path | None = None) -> None:
        self.cli_path = cli_path
        self.cwd = cwd or Path(tempfile.gettempdir()) / "simile-llm"
        self.session_info: dict[str, Any] | None = None
        """The last call's `system/init` frame: model, tools, MCP servers, API key source."""

    def options(self, request: Request) -> ClaudeAgentOptions:
        return ClaudeAgentOptions(
            model=request.model,
            system_prompt=request.system,
            tools=[],
            mcp_servers={},
            strict_mcp_config=True,
            setting_sources=[],
            skills=[],
            max_turns=1,
            permission_mode="dontAsk",
            thinking={"type": "disabled"},
            include_partial_messages=True,
            verbatim_prompts=True,
            cwd=self.cwd,
            cli_path=self.cli_path,
            extra_args={
                "safe-mode": None,
                "disable-slash-commands": None,
                "no-session-persistence": None,
            },
        )

    async def stream(self, request: Request) -> AsyncGenerator[str | Usage, None]:
        async with self.session(request) as sdk, aclosing(self.turn(sdk, request)) as chunks:
            async for chunk in chunks:
                yield chunk

    @asynccontextmanager
    async def session(self, request: Request) -> AsyncIterator[ClaudeSDKClient]:
        """A connected Claude Code process with this request's model and system prompt."""
        drop_api_credentials()
        self.cwd.mkdir(parents=True, exist_ok=True)
        with as_llm_errors():
            async with ClaudeSDKClient(self.options(request)) as sdk:
                yield sdk

    async def turn(
        self, sdk: ClaudeSDKClient, request: Request
    ) -> AsyncGenerator[str | Usage, None]:
        """Send the request as the session's next turn. Interrupt it if the caller stops early."""
        finished = False
        try:
            with as_llm_errors():
                await sdk.query(render_prompt(request.messages))
                async with aclosing(self.parse(sdk.receive_response())) as chunks:
                    async for chunk in chunks:
                        yield chunk
            finished = True
        finally:
            if not finished:
                await interrupt(sdk)

    async def parse(self, messages: AsyncIterator[SDKMessage]) -> AsyncGenerator[str | Usage, None]:
        subscription_confirmed = False
        rate_limit: RateLimit | None = None
        async for message in messages:
            match message:
                case SystemMessage(subtype="init", data=data):
                    self.session_info = data
                    if data.get("apiKeySource") != "none":
                        raise LLMError(
                            "Claude Code must use the subscription login, but reported API key "
                            f"source {data.get('apiKeySource')!r}. Log in with a Claude "
                            "subscription and unset any API key."
                        )
                    subscription_confirmed = True
                case StreamEvent(event={"delta": {"type": "text_delta", "text": text}}):
                    if not subscription_confirmed:
                        raise LLMError("Claude Code sent text before confirming its login")
                    yield text
                case RateLimitEvent(rate_limit_info=info):
                    rate_limit = RateLimit(
                        info.status, info.rate_limit_type, info.utilization, info.resets_at
                    )
                    if info.status != "allowed":
                        logger.warning("Claude usage limit %s: %s", info.status, info.raw)
                case ResultMessage():
                    if message.is_error:
                        raise LLMError(
                            f"Claude Code call failed ({message.subtype}): "
                            f"{message.errors or message.result}"
                        )
                    if not subscription_confirmed:
                        raise LLMError("Claude Code finished without confirming its login")
                    yield usage_from(message, rate_limit)
                    return
        raise LLMError("Claude Code stopped without finishing the reply")


@contextmanager
def as_llm_errors() -> Iterator[None]:
    try:
        yield
    except ClaudeSDKError as e:
        raise LLMError(f"Claude Code failed: {e}") from e


async def interrupt(sdk: ClaudeSDKClient) -> None:
    """Stop the turn now: leaving the client only closes stdin, and Claude Code finishes first."""

    async def drain() -> None:
        async for _ in sdk.receive_messages():
            pass

    with anyio.CancelScope(shield=True), anyio.move_on_after(1), suppress(Exception):
        async with anyio.create_task_group() as tasks:
            # A full SDK buffer would otherwise hold back the reply to the interrupt.
            tasks.start_soon(drain)
            await sdk.interrupt()
            tasks.cancel_scope.cancel()


def usage_from(result: ResultMessage, rate_limit: RateLimit | None = None) -> Usage:
    usage = result.usage or {}
    return Usage(
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        cache_read_tokens=usage.get("cache_read_input_tokens", 0),
        cache_creation_tokens=usage.get("cache_creation_input_tokens", 0),
        cost_usd=result.total_cost_usd,
        model=next(iter(result.model_usage or {}), None),
        api_ms=result.duration_api_ms,
        rate_limit=rate_limit,
    )


def render_prompt(messages: Sequence[Message]) -> str:
    """Fold earlier turns into the one user message a single Claude Code turn takes."""
    *earlier, last = messages
    if not earlier:
        return last.content
    turns = "\n".join(f"<{m.role}>\n{m.content}\n</{m.role}>" for m in earlier)
    return f"<earlier_turns>\n{turns}\n</earlier_turns>\n\n{last.content}"
