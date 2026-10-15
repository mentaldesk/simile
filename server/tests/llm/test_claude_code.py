from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from simile.llm import CallRecord, LLMClient, LLMError, Message, Request, Usage
from simile.llm.claude_code import API_CREDENTIALS, ClaudeCodeProvider, render_prompt

MakeFakeCli = Callable[..., Any]

pytestmark = pytest.mark.anyio

SYSTEM = "You are Mara, who runs the coffee shop."


def value_after(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


def test_options_make_a_plain_text_generator(tmp_path: Path) -> None:
    provider = ClaudeCodeProvider(cwd=tmp_path)

    options = provider.options(Request((Message("user", "Hello"),), SYSTEM, "haiku"))

    assert options.model == "haiku"
    assert options.system_prompt == SYSTEM
    assert options.tools == []
    assert options.allowed_tools == []
    assert options.mcp_servers == {}
    assert options.strict_mcp_config
    assert options.setting_sources == []
    assert options.skills == []
    assert options.max_turns == 1
    assert options.verbatim_prompts
    assert options.include_partial_messages
    assert options.cwd == tmp_path


async def test_streams_through_the_cli(fake_cli: MakeFakeCli, tmp_path: Path) -> None:
    cli = fake_cli(chunks=("Morning", ", stranger."))
    records: list[CallRecord] = []
    client = LLMClient(
        ClaudeCodeProvider(cli_path=cli.path, cwd=tmp_path), listeners=[records.append]
    )

    chunks = [chunk async for chunk in client.stream("Hello", system=SYSTEM, purpose="greet")]

    assert chunks == ["Morning", ", stranger."]
    [record] = records
    assert record.provider == "claude-code"
    assert record.ttft_ms is not None
    assert record.usage == Usage(
        input_tokens=12,
        output_tokens=4,
        cache_read_tokens=600,
        cost_usd=0.001,
        model="claude-haiku-test",
        api_ms=30,
    )


async def test_runs_the_cli_with_no_tools_settings_or_mcp(
    fake_cli: MakeFakeCli, tmp_path: Path
) -> None:
    cli = fake_cli()
    client = LLMClient(ClaudeCodeProvider(cli_path=cli.path, cwd=tmp_path))

    await client.complete("Hello", system=SYSTEM, model="sonnet")

    argv = cli.argv
    assert value_after(argv, "--system-prompt") == SYSTEM
    assert value_after(argv, "--tools") == ""
    assert value_after(argv, "--model") == "sonnet"
    assert value_after(argv, "--max-turns") == "1"
    assert value_after(argv, "--thinking") == "disabled"
    assert "--setting-sources=" in argv
    assert "--strict-mcp-config" in argv
    assert "--mcp-config" not in argv
    assert "--allowedTools" not in argv
    assert "--safe-mode" in argv
    assert "--disable-slash-commands" in argv
    assert "--no-session-persistence" in argv
    [prompt] = cli.stdin
    assert prompt["message"] == {"role": "user", "content": "Hello"}
    assert prompt["client_composed"] is True


async def test_never_passes_api_credentials_to_the_cli(
    fake_cli: MakeFakeCli, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in API_CREDENTIALS:
        monkeypatch.setenv(name, "set-by-test")
    monkeypatch.setenv("SIMILE_TEST_MARKER", "inherited")
    cli = fake_cli()
    client = LLMClient(ClaudeCodeProvider(cli_path=cli.path, cwd=tmp_path))

    await client.complete("Hello")

    assert cli.env["SIMILE_TEST_MARKER"] == "inherited"
    assert [name for name in API_CREDENTIALS if name in cli.env] == []


async def test_refuses_a_session_billed_to_an_api_key(
    fake_cli: MakeFakeCli, tmp_path: Path
) -> None:
    cli = fake_cli(api_key_source="ANTHROPIC_API_KEY")
    client = LLMClient(ClaudeCodeProvider(cli_path=cli.path, cwd=tmp_path))
    chunks: list[str] = []

    with pytest.raises(LLMError, match="API key"):
        async for chunk in client.stream("Hello"):
            chunks.append(chunk)

    assert chunks == []


async def test_raises_on_an_error_result(fake_cli: MakeFakeCli, tmp_path: Path) -> None:
    cli = fake_cli(chunks=(), subtype="error_max_turns")
    records: list[CallRecord] = []
    client = LLMClient(
        ClaudeCodeProvider(cli_path=cli.path, cwd=tmp_path), listeners=[records.append]
    )

    with pytest.raises(LLMError, match="error_max_turns"):
        await client.complete("Hello")

    assert records[0].error is not None


def test_renders_earlier_turns_into_one_prompt() -> None:
    prompt = render_prompt(
        (
            Message("user", "Nice weather."),
            Message("assistant", "It is!"),
            Message("user", "Coffee?"),
        )
    )

    assert prompt == (
        "<earlier_turns>\n"
        "<user>\nNice weather.\n</user>\n"
        "<assistant>\nIt is!\n</assistant>\n"
        "</earlier_turns>\n\n"
        "Coffee?"
    )


def test_a_single_message_is_sent_as_is() -> None:
    assert render_prompt((Message("user", "Coffee?"),)) == "Coffee?"
