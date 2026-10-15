import os
import time
from collections.abc import AsyncGenerator
from pathlib import Path

from claude_agent_sdk import ClaudeSDKClient

from simile.llm.claude_code import (
    API_CREDENTIALS,
    ClaudeCodeProvider,
    drop_api_credentials,
    render_prompt,
)
from simile.llm.client import CallRecord, LLMClient
from simile.llm.provider import Message, Request, Usage

SYSTEM = "You are Mara, who runs the coffee shop in a small village. You speak warmly and briefly."


class SessionProvider:
    """Sends every request as the next turn of one connected Claude Code session."""

    name = "claude-code-session"

    def __init__(self, sdk: ClaudeSDKClient, parent: ClaudeCodeProvider) -> None:
        self.sdk = sdk
        self.parent = parent

    async def stream(self, request: Request) -> AsyncGenerator[str | Usage, None]:
        await self.sdk.query(render_prompt(request.messages))
        async for chunk in self.parent.parse(self.sdk.receive_response()):
            yield chunk


async def smoke(
    prompt: str, *, model: str, runs: int, session: bool, cli_path: str | Path | None
) -> None:
    present = [name for name in API_CREDENTIALS if name in os.environ]
    print(f"Dropping from the environment: {', '.join(present)}" if present else "No API keys set")
    provider = ClaudeCodeProvider(cli_path=cli_path)
    if not session:
        await run(LLMClient(provider), prompt, model, runs)
    else:
        drop_api_credentials()
        provider.cwd.mkdir(parents=True, exist_ok=True)
        options = provider.options(Request((Message("user", prompt),), SYSTEM, model))
        start = time.perf_counter()
        async with ClaudeSDKClient(options) as sdk:
            print(f"Session connected in {(time.perf_counter() - start) * 1000:.0f} ms")
            await run(LLMClient(SessionProvider(sdk, provider)), prompt, model, runs)
    info = provider.session_info or {}
    print(
        f"Claude Code {info.get('claude_code_version')}, model {info.get('model')}, "
        f"API key source {info.get('apiKeySource')!r}, tools {info.get('tools')}, "
        f"MCP servers {info.get('mcp_servers')}, skills {info.get('skills')}, "
        f"plugins {info.get('plugins')}"
    )


async def run(client: LLMClient, prompt: str, model: str, runs: int) -> None:
    records: list[CallRecord] = []
    client.listeners.append(records.append)
    for _ in range(runs):
        async for chunk in client.stream(prompt, system=SYSTEM, model=model, purpose="smoke"):
            print(chunk, end="", flush=True)
        record = records[-1]
        usage = record.usage or Usage()
        print(
            f"\n  latency {record.latency_ms:.0f} ms (API {usage.api_ms or 0:.0f} ms), "
            f"first token {record.ttft_ms or 0:.0f} ms, "
            f"tokens in {usage.input_tokens} (+{usage.cache_read_tokens} cached, "
            f"+{usage.cache_creation_tokens} cache writes), out {usage.output_tokens}, "
            f"{usage.model}"
        )
