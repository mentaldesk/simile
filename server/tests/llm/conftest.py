import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

FAKE_CLI = """#!{python}
import json
import os
import sys

scenario = json.loads({scenario!r})

if sys.argv[1:] == ["-v"]:
    print("2.1.300 (Claude Code)")
    sys.exit()


def log(entry):
    with open(scenario["log"], "a") as f:
        f.write(json.dumps(entry) + "\\n")


def send(message):
    print(json.dumps(message), flush=True)


log({{"argv": sys.argv[1:], "env": dict(os.environ)}})
ids = {{"uuid": "u1", "session_id": "s1"}}
for line in sys.stdin:
    message = json.loads(line)
    if message["type"] == "control_request":
        response = {{"subtype": "success", "request_id": message["request_id"], "response": {{}}}}
        send({{"type": "control_response", "response": response}})
    elif message["type"] == "user":
        log({{"stdin": message}})
        send(
            {{
                "type": "system",
                "subtype": "init",
                "apiKeySource": scenario["api_key_source"],
                "tools": [],
                "mcp_servers": [],
                **ids,
            }}
        )
        for text in scenario["chunks"]:
            delta = {{"type": "text_delta", "text": text}}
            event = {{"type": "content_block_delta", "index": 0, "delta": delta}}
            send({{"type": "stream_event", "event": event, **ids}})
        send(
            {{
                "type": "result",
                "subtype": scenario["subtype"],
                "is_error": scenario["subtype"] != "success",
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


MakeFakeCli = Callable[..., FakeCli]


@pytest.fixture
def fake_cli(tmp_path: Path) -> MakeFakeCli:
    def make(
        chunks: tuple[str, ...] = ("Morning", ", stranger."),
        api_key_source: str = "none",
        subtype: str = "success",
    ) -> FakeCli:
        log = tmp_path / "fake-claude.log"
        scenario = json.dumps(
            {
                "log": str(log),
                "chunks": chunks,
                "api_key_source": api_key_source,
                "subtype": subtype,
            }
        )
        path = tmp_path / "claude"
        path.write_text(FAKE_CLI.format(python=sys.executable, scenario=scenario))
        path.chmod(0o755)
        return FakeCli(path, log)

    return make
