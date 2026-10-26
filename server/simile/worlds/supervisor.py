import logging
import os
import signal
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import FrameType

from simile.worlds.store import TODAY_ID, Worlds, running

logger = logging.getLogger(__name__)

SUPERVISOR_ENV = "SIMILE_SUPERVISOR"
SWITCH = signal.SIGUSR1
STOPS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
FIRST_ONLY = ("SIMILE_FRESH",)

type Spawn = Callable[..., subprocess.Popen[bytes]]


def server_command(host: str, port: int, reload: bool) -> list[str]:
    serve = [sys.executable, "-c", "from simile.cli import main; main()", "serve"]
    return [*serve, "--host", host, "--port", str(port), *(["--reload"] if reload else [])]


def switch() -> bool:
    """Asks the supervisor to restart the server on the last world opened. False if there's no
    supervisor."""
    pid = os.environ.get(SUPERVISOR_ENV)
    if not pid:
        return False
    try:
        os.kill(int(pid), SWITCH)
    except (ValueError, ProcessLookupError, PermissionError):
        return False
    return True


class Supervisor:
    """Runs the server on one world at a time, each in a process of its own, so no state carries
    from one world to the next. The server asks for another world with `switch`."""

    def __init__(
        self,
        command: Sequence[str],
        worlds: Worlds,
        environ: Mapping[str, str] = os.environ,
        spawn: Spawn = subprocess.Popen,
        killpg: Callable[[int, int], None] = os.killpg,
    ) -> None:
        self.command = list(command)
        self.worlds = worlds
        self.environ = dict(environ)
        self.spawn = spawn
        self.killpg = killpg
        self.child: subprocess.Popen[bytes] | None = None
        self.switching = self.stopping = False
        self.signalled = False

    def run(self) -> int:
        handlers = {sig: signal.signal(sig, self._stop) for sig in STOPS}
        handlers[SWITCH] = signal.signal(SWITCH, self._switch)
        try:
            return self._serve()
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)

    def _serve(self) -> int:
        first = True
        while True:
            env, id = self.environment(first)
            first = False
            self.switching = self.signalled = False
            self.child = self.spawn(self.command, env=env, start_new_session=True)
            if self.stopping:
                self._signal(force=False)
            code = self.child.wait()
            if self.stopping:
                return 0 if code < 0 else code
            if not self.switching:
                return code
            logger.info("Switching worlds, from %s", id or self.environ.get("SIMILE_DB"))

    def environment(self, first: bool) -> tuple[dict[str, str], str | None]:
        """The server's environment, and the id of the world it opens, if it's one of the worlds:
        the one the menu asked for, else the last played. On the first start `$SIMILE_DB`
        overrides both."""
        from simile.library.store import DEFAULT_ROOT as LIBRARY

        env = {**self.environ, SUPERVISOR_ENV: str(os.getpid())}
        if first and self.environ.get("SIMILE_DB"):
            return env, running(self.worlds.root, Path(self.environ["SIMILE_DB"]))
        if not first:
            for name in FIRST_ONLY:
                env.pop(name, None)
        ids = self.worlds.ids()
        id = next((id for id in self.worlds.index.take() if id in ids), TODAY_ID)
        env["SIMILE_DB"] = str(self.worlds.database(id))
        env["SIMILE_LIBRARY"] = self.environ.get("SIMILE_LIBRARY") or str(LIBRARY)
        return env, id

    def _switch(self, sig: int, frame: FrameType | None) -> None:
        if not self.switching and not self.stopping:
            self.switching = True
            self._signal(force=False)

    def _stop(self, sig: int, frame: FrameType | None) -> None:
        force, self.stopping = self.stopping, True
        self._signal(force)

    def _signal(self, force: bool) -> None:
        """SIGTERM to the server, which shuts down and saves. Forced, SIGINT to its whole group,
        so it reaches the worker under uvicorn's reloader too."""
        if self.child is None or self.child.poll() is not None:
            return
        if force:
            self.killpg(self.child.pid, signal.SIGINT)
        elif not self.signalled:
            self.signalled = True
            self.child.send_signal(signal.SIGTERM)
