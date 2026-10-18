from collections.abc import Callable
from pathlib import Path

import pytest

from simile.characters.pool import load_pool
from simile.schema import Character, Hook, HookKind, HookSide


@pytest.fixture(scope="session")
def pool() -> list[Character]:
    return load_pool()


@pytest.fixture
def make(pool: list[Character]) -> Callable[..., Character]:
    """A character like the pool's first, named after `id`, with `hooks` as (kind, side) or
    (kind, side, description), and a voice `clip`."""
    template = pool[0]

    def make(
        id: str,
        hooks: tuple[tuple[str, ...], ...] = (),
        clip: str | None = None,
        **changes: object,
    ) -> Character:
        name = " ".join(part.capitalize() for part in id.split("_"))
        return template.model_copy(
            update={
                "id": id,
                "name": name,
                "hooks": [_hook(*spec) for spec in hooks],
                "past": [],
                "arrival": None,
                "voice": template.voice.model_copy(update={"reference_clip": clip}),
                **changes,
            }
        )

    return make


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A new world's data directory, which `SIMILE_DB` points at."""
    folder = tmp_path / "world"
    monkeypatch.setenv("SIMILE_DB", str(folder / "simile.db"))
    return folder


def _hook(kind: str, side: str, description: str = "") -> Hook:
    return Hook(
        kind=HookKind(kind), side=HookSide(side), description=description or f"{kind} {side}."
    )
