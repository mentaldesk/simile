import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from simile.llm.claude_code import API_CREDENTIALS

FAKE_CLI = """#!{python}
import json
import os
import sys
import threading
import time

scenario = json.loads({scenario!r})

if sys.argv[1:] == ["-v"]:
    print("2.1.300 (Claude Code)")
    sys.exit()

lock = threading.Lock()
interrupted = threading.Event()
ids = {{"uuid": "u1", "session_id": "s1"}}


def log(entry):
    with lock, open(scenario["log"], "a") as f:
        f.write(json.dumps(entry) + "\\n")


def send(message):
    with lock:
        print(json.dumps(message), flush=True)


def reply():
    if scenario["init"]:
        init = {{"type": "system", "subtype": "init", "tools": [], "mcp_servers": [], **ids}}
        if scenario["api_key_source"] is not None:
            init["apiKeySource"] = scenario["api_key_source"]
        send(init)
    if scenario["rate_limit"]:
        send({{"type": "rate_limit_event", "rate_limit_info": scenario["rate_limit"], **ids}})
    for text in scenario["chunks"]:
        if interrupted.is_set():
            break
        time.sleep(scenario["delay"])
        delta = {{"type": "text_delta", "text": text}}
        event = {{"type": "content_block_delta", "index": 0, "delta": delta}}
        send({{"type": "stream_event", "event": event, **ids}})
    if not scenario["result"]:
        os._exit(scenario["exit_code"])
    subtype = "error_during_execution" if interrupted.is_set() else scenario["subtype"]
    send(
        {{
            "type": "result",
            "subtype": subtype,
            "is_error": subtype != "success",
            "duration_ms": 50,
            "duration_api_ms": 30,
            "num_turns": 1,
            "result": "".join(scenario["chunks"]),
            "usage": {{"input_tokens": 12, "output_tokens": 4, "cache_read_input_tokens": 600}},
            "total_cost_usd": 0.001,
            "modelUsage": {{"claude-haiku-test": {{}}}},
            "session_id": "s1",
        }}
    )


log({{"argv": sys.argv[1:], "env": dict(os.environ), "pid": os.getpid()}})
replying = None
for line in sys.stdin:
    message = json.loads(line)
    if message["type"] == "control_request":
        if message["request"]["subtype"] == "interrupt":
            log({{"interrupt": True}})
            interrupted.set()
        body = {{}}
        if message["request"]["subtype"] == "initialize" and scenario["account"] is not None:
            body = {{"account": scenario["account"]}}
        response = {{"subtype": "success", "request_id": message["request_id"], "response": body}}
        send({{"type": "control_response", "response": response}})
    elif message["type"] == "user":
        log({{"stdin": message}})
        if replying:
            replying.join()
        interrupted.clear()
        replying = threading.Thread(target=reply)
        replying.start()
if replying:
    replying.join()
sys.exit(scenario["exit_code"])
"""


@dataclass
class FakeCli:
    """A stand-in for the `claude` CLI that speaks the SDK's stream-json protocol."""

    path: Path
    log: Path

    def entries(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    @property
    def argv(self) -> list[str]:
        return next(e["argv"] for e in self.entries() if "argv" in e)

    @property
    def env(self) -> dict[str, str]:
        return next(e["env"] for e in self.entries() if "env" in e)

    @property
    def stdin(self) -> list[dict[str, Any]]:
        return [e["stdin"] for e in self.entries() if "stdin" in e]

    @property
    def pids(self) -> list[int]:
        """Every process started, in order."""
        return [e["pid"] for e in self.entries() if "pid" in e]

    @property
    def interrupted(self) -> bool:
        return any("interrupt" in e for e in self.entries())


MakeFakeCli = Callable[..., FakeCli]

FIRST_PARTY = {"apiProvider": "firstParty", "subscriptionType": "Claude Max"}


@pytest.fixture(autouse=True)
def no_api_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in API_CREDENTIALS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def fake_cli(tmp_path: Path) -> MakeFakeCli:
    def make(
        chunks: tuple[str, ...] = ("Morning", ", stranger."),
        *,
        delay: float = 0,
        init: bool = True,
        api_key_source: str | None = "none",
        rate_limit: dict[str, Any] | None = None,
        result: bool = True,
        subtype: str = "success",
        exit_code: int = 0,
        account: dict[str, Any] | None = FIRST_PARTY,
    ) -> FakeCli:
        log = tmp_path / "fake-claude.log"
        log.touch()
        scenario = json.dumps(
            {
                "log": str(log),
                "chunks": chunks,
                "delay": delay,
                "init": init,
                "api_key_source": api_key_source,
                "rate_limit": rate_limit,
                "result": result,
                "subtype": subtype,
                "exit_code": exit_code,
                "account": account,
            }
        )
        path = tmp_path / "claude"
        path.write_text(FAKE_CLI.format(python=sys.executable, scenario=scenario))
        path.chmod(0o755)
        return FakeCli(path, log)

    return make
