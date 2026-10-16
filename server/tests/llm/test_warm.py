import asyncio
import os
import signal
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from simile.llm import FakeProvider, LLMClient, LLMError
from simile.llm.claude_code import ClaudeCodeProvider
from simile.llm.lifespan import CannedProvider

MakeFakeCli = Callable[..., Any]

pytestmark = pytest.mark.anyio

SYSTEM = "You are Mara, who runs the coffee shop."


def provider_for(cli: Any, tmp_path: Path, **kwargs: Any) -> ClaudeCodeProvider:
    return ClaudeCodeProvider(cli_path=cli.path, cwd=tmp_path, **kwargs)


async def connected(provider: ClaudeCodeProvider, model: str = "haiku") -> None:
    warm = provider._warm[(SYSTEM, model)]
    assert await asyncio.wait_for(asyncio.shield(warm.ready), 10) is not None


async def test_a_warm_process_takes_the_next_call_with_its_system_prompt(
    fake_cli: MakeFakeCli, tmp_path: Path
) -> None:
    cli = fake_cli()
    provider = provider_for(cli, tmp_path)
    client = LLMClient(provider)

    client.warm(system=SYSTEM)
    await connected(provider)

    assert len(cli.pids) == 1
    assert cli.stdin == []
    assert await client.complete("Hello", system=SYSTEM) == "Morning, stranger."
    assert len(cli.pids) == 1
    assert [prompt["message"]["content"] for prompt in cli.stdin] == ["Hello"]
    assert provider._warm == {}

    assert await client.complete("Hello again", system=SYSTEM) == "Morning, stranger."
    assert len(cli.pids) == 2


async def test_a_warm_process_is_only_used_for_its_system_prompt_and_model(
    fake_cli: MakeFakeCli, tmp_path: Path
) -> None:
    cli = fake_cli()
    provider = provider_for(cli, tmp_path)
    client = LLMClient(provider)
    client.warm(system=SYSTEM)
    await connected(provider)

    await client.complete("Hello", system=SYSTEM, model="sonnet")
    await client.complete("Hello", system="You are someone else.")

    assert len(cli.pids) == 3
    assert list(provider._warm) == [(SYSTEM, "haiku")]
    await client.aclose()


async def test_a_warm_process_that_isnt_used_closes(fake_cli: MakeFakeCli, tmp_path: Path) -> None:
    provider = provider_for(fake_cli(), tmp_path, warm_for=0.3)
    provider.warm(SYSTEM, "haiku")
    warm = provider._warm[(SYSTEM, "haiku")]

    await asyncio.wait_for(warm.task, 10)

    assert provider._warm == {}


async def test_warming_again_keeps_it_longer(fake_cli: MakeFakeCli, tmp_path: Path) -> None:
    provider = provider_for(fake_cli(), tmp_path, warm_for=0.5)
    provider.warm(SYSTEM, "haiku")
    warm = provider._warm[(SYSTEM, "haiku")]
    await connected(provider)

    for _ in range(4):
        await asyncio.sleep(0.25)
        provider.warm(SYSTEM, "haiku")

    assert not warm.task.done()
    assert provider._warm[(SYSTEM, "haiku")] is warm
    await provider.aclose()
    assert warm.task.done()


async def test_the_oldest_warm_process_makes_way(fake_cli: MakeFakeCli, tmp_path: Path) -> None:
    provider = provider_for(fake_cli(), tmp_path, max_warm=1)
    provider.warm(SYSTEM, "haiku")
    first = provider._warm[(SYSTEM, "haiku")]

    provider.warm(SYSTEM, "sonnet")

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(first.task, 10)
    assert list(provider._warm) == [(SYSTEM, "sonnet")]
    await provider.aclose()


async def test_closing_the_client_closes_warm_processes(
    fake_cli: MakeFakeCli, tmp_path: Path
) -> None:
    provider = provider_for(fake_cli(), tmp_path)
    client = LLMClient(provider)
    client.warm(system=SYSTEM)
    await connected(provider)
    warm = provider._warm[(SYSTEM, "haiku")]

    await asyncio.wait_for(client.aclose(), 10)

    assert warm.task.done()
    assert provider._warm == {}


async def test_a_warm_process_that_died_is_replaced_by_a_fresh_one(
    fake_cli: MakeFakeCli, tmp_path: Path
) -> None:
    cli = fake_cli()
    provider = provider_for(cli, tmp_path)
    provider.warm(SYSTEM, "haiku")
    await connected(provider)

    os.kill(cli.pids[0], signal.SIGKILL)
    await asyncio.sleep(0.2)

    assert await LLMClient(provider).complete("Hello", system=SYSTEM) == "Morning, stranger."
    assert len(cli.pids) == 2


async def test_a_warm_process_checks_the_account_like_any_other(
    fake_cli: MakeFakeCli, tmp_path: Path
) -> None:
    cli = fake_cli(account={"apiProvider": "gateway"})
    provider = provider_for(cli, tmp_path)
    provider.warm(SYSTEM, "haiku")
    warm = provider._warm[(SYSTEM, "haiku")]
    await asyncio.wait_for(warm.task, 10)

    with pytest.raises(LLMError, match="must bill the Claude subscription"):
        await LLMClient(provider).complete("Hello", system=SYSTEM)

    assert cli.stdin == []


async def test_warming_needs_a_provider_that_can() -> None:
    fake = FakeProvider()
    LLMClient(fake).warm(system=SYSTEM, model="sonnet")
    LLMClient(CannedProvider()).warm(system=SYSTEM)

    assert fake.warmed == [(SYSTEM, "sonnet")]
