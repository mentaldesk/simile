import logging
import os
import tempfile
from collections.abc import AsyncGenerator, AsyncIterator, Sequence
from contextlib import aclosing
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    RateLimitEvent,
    ResultMessage,
    StreamEvent,
    SystemMessage,
)
from claude_agent_sdk import Message as SDKMessage

from simile.llm.provider import LLMError, Message, Request, Usage

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
        drop_api_credentials()
        self.cwd.mkdir(parents=True, exist_ok=True)
        async with ClaudeSDKClient(self.options(request)) as sdk:
            await sdk.query(render_prompt(request.messages))
            async with aclosing(self.parse(sdk.receive_response())) as chunks:
                async for chunk in chunks:
                    yield chunk

    async def parse(self, messages: AsyncIterator[SDKMessage]) -> AsyncGenerator[str | Usage, None]:
        async for message in messages:
            match message:
                case SystemMessage(subtype="init", data=data):
                    self.session_info = data
                    if data.get("apiKeySource", "none") != "none":
                        raise LLMError(
                            f"Claude Code is billing an API key ({data['apiKeySource']}). "
                            "Log in to Claude Code with a Claude subscription instead."
                        )
                case StreamEvent(event={"delta": {"type": "text_delta", "text": text}}):
                    yield text
                case RateLimitEvent(rate_limit_info=info) if info.status != "allowed":
                    logger.warning("Claude usage limit %s: %s", info.status, info.raw)
                case ResultMessage():
                    if message.is_error:
                        raise LLMError(
                            f"Claude Code call failed ({message.subtype}): "
                            f"{message.errors or message.result}"
                        )
                    yield usage_from(message)


def usage_from(result: ResultMessage) -> Usage:
    usage = result.usage or {}
    return Usage(
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        cache_read_tokens=usage.get("cache_read_input_tokens", 0),
        cache_creation_tokens=usage.get("cache_creation_input_tokens", 0),
        cost_usd=result.total_cost_usd,
        model=next(iter(result.model_usage or {}), None),
        api_ms=result.duration_api_ms,
    )


def render_prompt(messages: Sequence[Message]) -> str:
    """Fold earlier turns into the one user message a single Claude Code turn takes."""
    *earlier, last = messages
    if not earlier:
        return last.content
    turns = "\n".join(f"<{m.role}>\n{m.content}\n</{m.role}>" for m in earlier)
    return f"<earlier_turns>\n{turns}\n</earlier_turns>\n\n{last.content}"
