import asyncio
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
    "CLAUDE_CODE_USE_ANTHROPIC_AWS",
    "CLAUDE_CODE_USE_ANTHROPIC_GOOGLE_CLOUD",
    "CLAUDE_CODE_USE_MANTLE",
    "CLAUDE_CODE_USE_GATEWAY",
)


def drop_api_credentials() -> None:
    """The CLI inherits our environment, and the SDK can add variables to it but not unset them."""
    for name in API_CREDENTIALS:
        os.environ.pop(name, None)


class ClaudeCodeProvider:
    """Plain text generation through the local Claude Code CLI on the user's subscription login."""

    name = "claude-code"

    def __init__(
        self,
        *,
        cli_path: str | Path | None = None,
        cwd: Path | None = None,
        max_warm: int = 2,
        warm_for: float = 120,
    ) -> None:
        self.cli_path = cli_path
        self.cwd = cwd or Path(tempfile.gettempdir()) / "simile-llm"
        self.max_warm = max_warm
        self.warm_for = warm_for
        self.session_info: dict[str, Any] | None = None
        """The last call's `system/init` frame: model, tools, MCP servers, API key source."""
        self.subscription: str | None = None
        """The subscription the last session's account reported, e.g. `Claude Max`."""
        self._warm: dict[tuple[str, str], Warm] = {}

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
        if warm := self._warm.pop((request.system, request.model), None):
            replied = False
            try:
                if sdk := await warm.claim():
                    async with aclosing(self.turn(sdk, request)) as chunks:
                        async for chunk in chunks:
                            replied = replied or isinstance(chunk, str)
                            yield chunk
                    return
            except LLMError as error:
                if replied or not isinstance(error.__cause__, ClaudeSDKError):
                    raise
                logger.warning("A warm Claude Code process failed, so starting another: %s", error)
            finally:
                warm.release()
        async with self.session(request) as sdk, aclosing(self.turn(sdk, request)) as chunks:
            async for chunk in chunks:
                yield chunk

    def warm(self, system: str, model: str) -> None:
        """Start a process for one later call with this system prompt and model."""
        key = (system, model)
        if warm := self._warm.get(key):
            warm.keep()
            return
        while self._warm and len(self._warm) >= self.max_warm:
            self._warm.pop(next(iter(self._warm))).close()
        if self.max_warm:
            self._warm[key] = Warm(self, Request((), system, model), self.warm_for)

    async def aclose(self) -> None:
        """Close the warm processes."""
        warms = list(self._warm.values())
        self._warm.clear()
        for warm in warms:
            warm.close()
        await asyncio.gather(*(warm.task for warm in warms), return_exceptions=True)

    @asynccontextmanager
    async def session(self, request: Request) -> AsyncIterator[ClaudeSDKClient]:
        """A connected Claude Code process with this request's model and system prompt."""
        drop_api_credentials()
        self.cwd.mkdir(parents=True, exist_ok=True)
        with as_llm_errors():
            async with ClaudeSDKClient(self.options(request)) as sdk:
                account = ((await sdk.get_server_info()) or {}).get("account") or {}
                if account.get("apiProvider") != "firstParty" or "apiKeySource" in account:
                    raise LLMError(
                        "Claude Code must bill the Claude subscription, but its account reports "
                        f"API provider {account.get('apiProvider')!r} and API key source "
                        f"{account.get('apiKeySource')!r}."
                    )
                self.subscription = account.get("subscriptionType")
                yield sdk

    async def turn(
        self, sdk: ClaudeSDKClient, request: Request
    ) -> AsyncGenerator[str | Usage, None]:
        """Send the request as the session's next turn. Interrupt it if the caller stops early."""
        ended = False

        async def messages() -> AsyncIterator[SDKMessage]:
            nonlocal ended
            async for message in sdk.receive_response():
                ended = isinstance(message, ResultMessage)
                yield message

        try:
            with as_llm_errors():
                await sdk.query(render_prompt(request.messages))
                async with aclosing(self.parse(messages())) as chunks:
                    async for chunk in chunks:
                        yield chunk
        finally:
            if not ended:
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


class Warm:
    """A Claude Code process for one turn, opened and closed in its own task as the SDK needs."""

    def __init__(self, provider: ClaudeCodeProvider, request: Request, idle: float) -> None:
        loop = asyncio.get_running_loop()
        self.ready: asyncio.Future[ClaudeSDKClient | None] = loop.create_future()
        self.claimed = asyncio.Event()
        self.released = asyncio.Event()
        self.idle = idle
        self.deadline = loop.time() + idle
        self.task = loop.create_task(self._hold(provider, request))

    def keep(self) -> None:
        self.deadline = max(self.deadline, asyncio.get_running_loop().time() + self.idle)

    async def claim(self) -> ClaudeSDKClient | None:
        """The connected client, or None if it couldn't connect."""
        self.claimed.set()
        return await asyncio.shield(self.ready)

    def release(self) -> None:
        self.released.set()

    def close(self) -> None:
        if not self.claimed.is_set():
            self.task.cancel()

    async def _hold(self, provider: ClaudeCodeProvider, request: Request) -> None:
        key = (request.system, request.model)
        try:
            async with provider.session(request) as sdk:
                self.ready.set_result(sdk)
                self.keep()
                await self._wait_for_claim()
                if provider._warm.get(key) is self:
                    del provider._warm[key]
                if self.claimed.is_set():
                    await self.released.wait()
        except Exception as error:
            logger.warning("A warm Claude Code process failed: %s", error)
        finally:
            if not self.ready.done():
                self.ready.set_result(None)
            if provider._warm.get(key) is self:
                del provider._warm[key]

    async def _wait_for_claim(self) -> None:
        loop = asyncio.get_running_loop()
        while not self.claimed.is_set() and (left := self.deadline - loop.time()) > 0:
            with suppress(TimeoutError):
                await asyncio.wait_for(self.claimed.wait(), left)


@contextmanager
def as_llm_errors() -> Iterator[None]:
    try:
        yield
    except ClaudeSDKError as e:
        raise LLMError(f"Claude Code failed: {e}") from e


async def interrupt(sdk: ClaudeSDKClient) -> None:
    """Stop the turn and read the rest of it, up to its result, so the session can take another.

    Leaving the client alone only closes stdin, and Claude Code finishes the turn before exiting.
    """
    with anyio.CancelScope(shield=True), anyio.move_on_after(1), suppress(Exception):
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(sdk.interrupt)
            async for message in sdk.receive_messages():
                if isinstance(message, ResultMessage):
                    break
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
