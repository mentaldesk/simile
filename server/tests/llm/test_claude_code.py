import asyncio
import time
from collections.abc import Callable
from contextlib import aclosing
from pathlib import Path
from typing import Any

import pytest

from simile.llm import CallRecord, LLMClient, LLMError, Message, Request, Usage
from simile.llm.claude_code import API_CREDENTIALS, ClaudeCodeProvider, render_prompt
from simile.llm.provider import RateLimit
from simile.llm.smoke import SessionProvider

MakeFakeCli = Callable[..., Any]

pytestmark = pytest.mark.anyio

SYSTEM = "You are Mara, who runs the coffee shop."


def value_after(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


def client_for(cli: Any, tmp_path: Path, **kwargs: Any) -> LLMClient:
    return LLMClient(ClaudeCodeProvider(cli_path=cli.path, cwd=tmp_path), **kwargs)


async def collect_until_error(client: LLMClient) -> tuple[list[str], LLMError]:
    chunks: list[str] = []
    with pytest.raises(LLMError) as error:
        async for chunk in client.stream("Hello"):
            chunks.append(chunk)
    return chunks, error.value


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
        thinking_tokens=3,
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

    chunks, error = await collect_until_error(client_for(cli, tmp_path))

    assert chunks == []
    assert "'ANTHROPIC_API_KEY'" in str(error)
    assert cli.interrupted


async def test_refuses_a_session_that_doesnt_report_its_api_key_source(
    fake_cli: MakeFakeCli, tmp_path: Path
) -> None:
    cli = fake_cli(api_key_source=None)

    chunks, error = await collect_until_error(client_for(cli, tmp_path))

    assert chunks == []
    assert "None" in str(error)


async def test_refuses_text_before_the_login_is_confirmed(
    fake_cli: MakeFakeCli, tmp_path: Path
) -> None:
    cli = fake_cli(init=False)

    chunks, error = await collect_until_error(client_for(cli, tmp_path))

    assert chunks == []
    assert "confirming its login" in str(error)


async def test_a_cli_crash_raises_llm_error(fake_cli: MakeFakeCli, tmp_path: Path) -> None:
    cli = fake_cli(chunks=("Morn",), result=False, exit_code=1)

    chunks, error = await collect_until_error(client_for(cli, tmp_path))

    assert chunks == ["Morn"]
    assert "exit code 1" in str(error)


async def test_a_reply_cut_short_raises_llm_error(fake_cli: MakeFakeCli, tmp_path: Path) -> None:
    cli = fake_cli(chunks=("Morn",), result=False, exit_code=0)

    chunks, error = await collect_until_error(client_for(cli, tmp_path))

    assert chunks == ["Morn"]
    assert "without finishing" in str(error)


async def test_a_missing_cli_raises_llm_error(tmp_path: Path) -> None:
    client = LLMClient(ClaudeCodeProvider(cli_path=tmp_path / "missing", cwd=tmp_path))

    with pytest.raises(LLMError, match="not found"):
        await client.complete("Hello")


async def test_leaving_a_stream_early_interrupts_the_cli(
    fake_cli: MakeFakeCli, tmp_path: Path
) -> None:
    cli = fake_cli(("word ",) * 100, delay=0.05)
    client = client_for(cli, tmp_path, max_concurrency=1)

    async with aclosing(client.stream("Hello")) as chunks:
        async for _ in chunks:
            left = time.perf_counter()
            break

    assert time.perf_counter() - left < 2
    assert cli.interrupted


async def test_interrupts_promptly_when_the_reader_fell_behind(
    fake_cli: MakeFakeCli, tmp_path: Path
) -> None:
    cli = fake_cli(("word ",) * 300, delay=0.005)
    client = client_for(cli, tmp_path)

    async with aclosing(client.stream("Hello")) as chunks:
        async for _ in chunks:
            await asyncio.sleep(1)  # long enough for the SDK's 100-message buffer to fill
            left = time.perf_counter()
            break

    assert time.perf_counter() - left < 0.9
    assert cli.interrupted


async def test_cancelling_a_call_interrupts_the_cli(fake_cli: MakeFakeCli, tmp_path: Path) -> None:
    cli = fake_cli(("word ",) * 100, delay=0.05)
    client = client_for(cli, tmp_path, max_concurrency=1)
    streaming = asyncio.Event()

    async def listen() -> None:
        async for _ in client.stream("Hello"):
            streaming.set()

    call = asyncio.create_task(listen())
    await streaming.wait()
    cancelled = time.perf_counter()
    call.cancel()
    with pytest.raises(asyncio.CancelledError):
        await call

    assert time.perf_counter() - cancelled < 2
    assert cli.interrupted


async def test_a_finished_call_is_not_interrupted(fake_cli: MakeFakeCli, tmp_path: Path) -> None:
    cli = fake_cli()

    await client_for(cli, tmp_path).complete("Hello")

    assert not cli.interrupted


async def test_records_the_subscription_usage_limit(fake_cli: MakeFakeCli, tmp_path: Path) -> None:
    limit = {"status": "allowed", "rateLimitType": "five_hour", "utilization": 0.4, "resetsAt": 9}
    cli = fake_cli(rate_limit=limit)
    records: list[CallRecord] = []

    await client_for(cli, tmp_path, listeners=[records.append]).complete("Hello")

    assert records[0].usage is not None
    assert records[0].usage.rate_limit == RateLimit("allowed", "five_hour", 0.4, 9)


async def test_reads_every_windows_utilisation(fake_cli: MakeFakeCli, tmp_path: Path) -> None:
    limit = {
        "status": "allowed",
        "rateLimitType": "five_hour",
        "resetsAt": 9,
        "unifiedWindows": {
            "five_hour": {"utilization": 0.27, "resetsAt": 9},
            "seven_day": {"utilization": 0.64, "resetsAt": 99},
        },
    }
    cli = fake_cli(rate_limit=limit)
    records: list[CallRecord] = []

    await client_for(cli, tmp_path, listeners=[records.append]).complete("Hello")

    assert records[0].usage is not None
    assert records[0].usage.rate_limit == RateLimit(
        "allowed", "five_hour", 0.27, 9, {"five_hour": 0.27, "seven_day": 0.64}
    )


async def test_raises_on_an_error_result(fake_cli: MakeFakeCli, tmp_path: Path) -> None:
    cli = fake_cli(chunks=(), subtype="error_max_turns")
    records: list[CallRecord] = []
    client = LLMClient(
        ClaudeCodeProvider(cli_path=cli.path, cwd=tmp_path), listeners=[records.append]
    )

    with pytest.raises(LLMError, match="error_max_turns"):
        await client.complete("Hello")

    assert records[0].error is not None
    assert not cli.interrupted


@pytest.mark.parametrize(
    "account",
    [
        {"apiProvider": "gateway", "subscriptionType": "Claude Max"},
        {"apiProvider": "bedrock"},
        {"apiProvider": "firstParty", "apiKeySource": "ANTHROPIC_API_KEY"},
        None,
    ],
    ids=["gateway", "bedrock", "api-key", "no-account"],
)
async def test_refuses_any_backend_but_the_subscription(
    fake_cli: MakeFakeCli, tmp_path: Path, account: dict[str, str] | None
) -> None:
    cli = fake_cli(account=account)

    with pytest.raises(LLMError, match="must bill the Claude subscription"):
        await client_for(cli, tmp_path).complete("Hello")

    assert cli.stdin == []


async def test_records_the_subscription(fake_cli: MakeFakeCli, tmp_path: Path) -> None:
    provider = ClaudeCodeProvider(cli_path=fake_cli().path, cwd=tmp_path)

    await LLMClient(provider).complete("Hello")

    assert provider.subscription == "Claude Max"


async def test_a_session_takes_another_turn_after_an_interrupted_one(
    fake_cli: MakeFakeCli, tmp_path: Path
) -> None:
    cli = fake_cli(("word ",) * 20, delay=0.02)
    provider = ClaudeCodeProvider(cli_path=cli.path, cwd=tmp_path)

    async with provider.session(Request((Message("user", "Hi"),), SYSTEM, "haiku")) as sdk:
        client = LLMClient(SessionProvider(sdk, provider))
        async with aclosing(client.stream("Turn 1")) as chunks:
            async for _ in chunks:
                break
        second = await client.complete("Turn 2")

    assert cli.interrupted
    assert [prompt["message"]["content"] for prompt in cli.stdin] == ["Turn 1", "Turn 2"]
    assert second == "word " * 20


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
