import json
import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from websockets.sync.client import connect

from simile.library import Library
from simile.library.store import DEFAULT_ROOT as LIBRARY
from simile.memory import MemoryStore
from simile.memory.store import DEFAULT_PATH
from simile.persistence import SavedWorld, WorldStore
from simile.worlds import NewWorld, Worlds
from simile.worlds.saves import progress
from simile.worlds.store import TODAY_ID
from simile.worlds.supervisor import SUPERVISOR_ENV, Supervisor, server_command, switch

from .conftest import POOL

SERVER = Path(__file__).resolve().parents[2]
BASE = {"SIMILE_LLM": "fake", "SIMILE_FRESH": "1"}


@pytest.fixture
def worlds(root: Path) -> Worlds:
    return Worlds(root)


def make(worlds: Worlds, library: Library, picks: list[str]) -> str:
    return worlds.create(NewWorld(count=len(picks), picks=picks, seed=1), library).id


class Child:
    def __init__(self, pid: int, exits: Callable[[], None] = lambda: None, code: int = 0) -> None:
        self.pid, self.exits, self.code, self.signals = pid, exits, code, list[int]()

    def wait(self) -> int:
        self.exits()
        return self.code

    def poll(self) -> int | None:
        return None

    def send_signal(self, sig: int) -> None:
        self.signals.append(sig)


class Spawner:
    """Starts a fake server for each world, each running `then` before it exits."""

    def __init__(self, *then: Callable[[], None]) -> None:
        self.then = list(then)
        self.envs: list[dict[str, str]] = []
        self.children: list[Child] = []

    def __call__(self, command: list[str], *, env: dict[str, str], **_: Any) -> Child:
        self.envs.append(env)
        pid = 1000 + len(self.children)
        self.children.append(Child(pid, self.then.pop(0) if self.then else lambda: None))
        return self.children[-1]


class Groups:
    def __init__(self) -> None:
        self.sent: list[tuple[int, int]] = []

    def __call__(self, group: int, sig: int) -> None:
        self.sent.append((group, sig))


def test_opens_todays_village_the_first_time(worlds: Worlds) -> None:
    env, id = Supervisor([], worlds, BASE).environment(first=True)

    assert id == TODAY_ID
    assert env["SIMILE_DB"] == str(DEFAULT_PATH)
    assert env["SIMILE_LIBRARY"] == str(LIBRARY)
    assert env[SUPERVISOR_ENV] == str(os.getpid())


def test_reopens_the_last_world_played(worlds: Worlds, library: Library) -> None:
    played = make(worlds, library, POOL[:2])
    worlds.index.opened(played)

    env, id = Supervisor([], worlds, BASE).environment(first=True)

    assert id == played
    assert env["SIMILE_DB"] == str(worlds.root / played / "simile.db")
    assert env["SIMILE_LIBRARY"] == str(LIBRARY)


def test_opens_todays_village_when_the_last_world_is_gone(worlds: Worlds, library: Library) -> None:
    played = make(worlds, library, POOL[:2])
    worlds.index.opened(played)
    worlds.index.opened(TODAY_ID)
    worlds.delete(played)

    _, id = Supervisor([], worlds, BASE).environment(first=True)

    assert id == TODAY_ID


def test_simile_db_overrides_the_last_world_on_the_first_start(
    worlds: Worlds, library: Library, tmp_path: Path
) -> None:
    played, other = make(worlds, library, POOL[:2]), make(worlds, library, POOL[2:4])
    worlds.index.opened(played)
    elsewhere = {**BASE, "SIMILE_DB": str(tmp_path / "mine.db"), "SIMILE_LIBRARY": "lib"}
    in_root = {**BASE, "SIMILE_DB": str(worlds.root / other / "simile.db")}

    env, id = Supervisor([], worlds, elsewhere).environment(first=True)
    _, found = Supervisor([], worlds, in_root).environment(first=True)
    later, _ = Supervisor([], worlds, elsewhere).environment(first=False)

    assert id is None
    assert env["SIMILE_DB"] == str(tmp_path / "mine.db") and env["SIMILE_LIBRARY"] == "lib"
    assert found == other
    assert later["SIMILE_DB"] == str(worlds.root / played / "simile.db")
    assert later["SIMILE_LIBRARY"] == "lib"


def test_starts_afresh_only_on_the_first_start(worlds: Worlds) -> None:
    supervisor = Supervisor([], worlds, BASE)

    assert supervisor.environment(first=True)[0]["SIMILE_FRESH"] == "1"
    assert "SIMILE_FRESH" not in supervisor.environment(first=False)[0]


def test_restarts_the_server_on_the_world_it_switches_to(worlds: Worlds, library: Library) -> None:
    other = make(worlds, library, POOL[:2])

    def switch() -> None:
        worlds.index.ask(other)
        supervisor._switch(signal.SIGUSR1, None)

    spawner = Spawner(switch)
    supervisor = Supervisor(["serve"], worlds, BASE, spawn=spawner)

    assert supervisor.run() == 0

    assert [env["SIMILE_DB"] for env in spawner.envs] == [
        str(DEFAULT_PATH),
        str(worlds.root / other / "simile.db"),
    ]
    assert spawner.children[0].signals == [signal.SIGTERM]
    assert spawner.children[1].signals == []
    assert worlds.index.read().next is None


def test_switches_on_a_real_signal(
    worlds: Worlds, library: Library, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = make(worlds, library, POOL[:2])
    monkeypatch.setenv(SUPERVISOR_ENV, str(os.getpid()))

    def asked() -> None:
        worlds.index.ask(other)
        assert switch()

    spawner = Spawner(asked)

    assert Supervisor(["serve"], worlds, BASE, spawn=spawner, killpg=Groups()).run() == 0

    assert len(spawner.envs) == 2
    assert spawner.children[0].signals == [signal.SIGTERM]


def test_a_world_asked_for_opens_once_and_the_last_played_after(
    worlds: Worlds, library: Library
) -> None:
    played, asked = make(worlds, library, POOL[:2]), make(worlds, library, POOL[2:4])
    worlds.index.opened(played)
    worlds.index.ask(asked)
    supervisor = Supervisor([], worlds, BASE)

    assert supervisor.environment(first=False)[1] == asked
    assert supervisor.environment(first=False)[1] == played


def test_a_world_asked_for_and_gone_falls_back_to_the_last_played(
    worlds: Worlds, library: Library
) -> None:
    played, asked = make(worlds, library, POOL[:2]), make(worlds, library, POOL[2:4])
    worlds.index.opened(played)
    worlds.index.ask(asked)
    worlds.delete(asked)

    assert Supervisor([], worlds, BASE).environment(first=False)[1] == played


def test_stops_with_the_server_and_forces_it_when_asked_again(worlds: Worlds) -> None:
    def stop() -> None:
        supervisor._stop(signal.SIGINT, None)
        supervisor._switch(signal.SIGUSR1, None)
        supervisor._stop(signal.SIGINT, None)
        supervisor._stop(signal.SIGINT, None)

    spawner, groups = Spawner(stop), Groups()
    supervisor = Supervisor(["serve"], worlds, BASE, spawn=spawner, killpg=groups)

    assert supervisor.run() == 0

    assert len(spawner.envs) == 1
    assert spawner.children[0].signals == [signal.SIGTERM]
    assert groups.sent == [(1000, signal.SIGINT), (1000, signal.SIGINT)]


def test_stopping_while_switching_lets_the_server_save(worlds: Worlds) -> None:
    def switch_then_stop() -> None:
        supervisor._switch(signal.SIGUSR1, None)
        supervisor._stop(signal.SIGINT, None)

    spawner, groups = Spawner(switch_then_stop), Groups()
    supervisor = Supervisor(["serve"], worlds, BASE, spawn=spawner, killpg=groups)

    assert supervisor.run() == 0

    assert len(spawner.envs) == 1
    assert spawner.children[0].signals == [signal.SIGTERM]
    assert groups.sent == []


def test_the_server_command_runs_simile_serve() -> None:
    command = server_command("127.0.0.1", 8123, reload=True)

    assert command[0] == sys.executable
    assert command[3:] == ["serve", "--host", "127.0.0.1", "--port", "8123", "--reload"]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def current(url: str) -> str | None:
    try:
        return httpx.get(f"{url}/api/worlds", timeout=5).json()["current"]["id"]
    except httpx.HTTPError:
        return None


def wait_for(url: str, id: str, server: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 90
    while current(url) != id:
        assert server.poll() is None, "the supervisor stopped"
        assert time.monotonic() < deadline, f"the server never opened {id}"
        time.sleep(0.2)


def snapshot(port: int) -> dict[str, Any]:
    with connect(f"ws://127.0.0.1:{port}/ws", open_timeout=10) as ws:
        while (message := json.loads(ws.recv(timeout=10)))["type"] != "snapshot":
            pass
    return message


def residents(message: dict[str, Any]) -> set[str]:
    return {e["id"] for e in message["entities"] if e["kind"] == "npc"}


def sim_time(message: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(message["time"])


def saved_at(database: Path) -> datetime:
    found = progress(database)
    assert found is not None, f"{database} holds no save"
    return found.now


@pytest.fixture
def supervised(
    worlds: Worlds, library: Library, tmp_path: Path
) -> Iterator[Callable[[str], tuple[subprocess.Popen[bytes], int]]]:
    servers: list[subprocess.Popen[bytes]] = []

    def start(first: str) -> tuple[subprocess.Popen[bytes], int]:
        port = free_port()
        env = {
            **os.environ,
            "SIMILE_WORLDS": str(worlds.root),
            "SIMILE_DB": str(worlds.root / first / "simile.db"),
            "SIMILE_LIBRARY": str(library.root),
            "SIMILE_JOBS": str(tmp_path / "jobs"),
            "SIMILE_LLM": "fake",
            "SIMILE_NEWS": "0",
        }
        for name in ("SIMILE_VOICE", "SIMILE_FRESH", "SIMILE_RECORD", "SIMILE_HOSTS"):
            env.pop(name, None)
        command = [sys.executable, "-c", "from simile.cli import main; main()"]
        server = subprocess.Popen(
            [*command, "worlds", "serve", "--port", str(port)], cwd=SERVER, env=env
        )
        servers.append(server)
        return server, port

    yield start
    for server in servers:
        stop(server)


def stop(server: subprocess.Popen[bytes]) -> None:
    """Stops the supervisor and, since it runs in a session of its own, its server's group."""
    if server.poll() is not None:
        return
    found = subprocess.run(["pgrep", "-P", str(server.pid)], capture_output=True, text=True)
    groups = [int(pid) for pid in found.stdout.split()]
    server.terminate()
    try:
        server.wait(timeout=30)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait()
    for group in groups:
        with suppress(ProcessLookupError, PermissionError):
            os.killpg(group, signal.SIGKILL)


def test_switches_worlds_without_restarting_and_keeps_each_as_it_was_saved(
    worlds: Worlds,
    library: Library,
    supervised: Callable[[str], tuple[subprocess.Popen[bytes], int]],
) -> None:
    first, second = make(worlds, library, POOL[:2]), make(worlds, library, POOL[2:5])
    begun = datetime(2031, 5, 5, 8, tzinfo=UTC)
    with MemoryStore(worlds.root / first / "simile.db") as memory, WorldStore(memory) as store:
        store.save(SavedWorld(now=begun, npcs={}))
    server, port = supervised(first)
    url = f"http://127.0.0.1:{port}"

    wait_for(url, first, server)
    in_first = snapshot(port)
    assert residents(in_first) >= set(POOL[:2])
    assert not residents(in_first) & set(POOL[2:5])
    assert sim_time(in_first) >= begun

    opened = httpx.post(f"{url}/api/worlds/{second}/open")
    assert opened.status_code == 202, opened.text
    wait_for(url, second, server)
    in_second = snapshot(port)
    left = saved_at(worlds.root / first / "simile.db")
    assert residents(in_second) >= set(POOL[2:5])
    assert not residents(in_second) & set(POOL[:2])
    assert sim_time(in_second).year < 2031
    assert left >= sim_time(in_first)

    assert httpx.post(f"{url}/api/worlds/{first}/open").status_code == 202
    wait_for(url, first, server)
    back = snapshot(port)
    assert residents(back) == residents(in_first)
    assert sim_time(back) >= left
    assert saved_at(worlds.root / second / "simile.db").year < 2031
    listed = {w["id"]: w for w in httpx.get(f"{url}/api/worlds").json()["worlds"]}
    assert [id for id, w in listed.items() if w["running"]] == [first]

    server.send_signal(signal.SIGINT)
    assert server.wait(timeout=60) == 0
    assert worlds.index.read().last == first
    assert saved_at(worlds.root / first / "simile.db") >= sim_time(back)
