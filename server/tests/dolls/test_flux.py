import os

import pytest

from simile.characters.palette import PLAYER
from simile.dolls import flux
from simile.dolls.figure import edit_prompt, stand_prompt
from simile.dolls.flux import Flux


@pytest.mark.mlx
def test_paints_from_text_then_edits_the_painting() -> None:
    pytest.importorskip("mflux")
    from simile.works.config import DEFAULT_CONFIG
    from simile.works.flux import downloaded

    if downloaded(DEFAULT_CONFIG.image_model) is None:
        pytest.skip(f"{DEFAULT_CONFIG.image_model} isn't downloaded")

    with Flux() as painter:
        stand = painter.paint(stand_prompt(PLAYER, "player"), (256, 352), 1)
        sit = painter.paint(edit_prompt("sit", PLAYER, "player"), (256, 352), 1, [stand])

    assert stand.size == sit.size == (256, 352)
    assert stand.tobytes() != sit.tobytes()


class Ran:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout


def test_waits_for_other_image_models_but_not_for_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    def run(command: list[str], **kwargs: object) -> Ran:
        if command[0] == "ollama":
            return Ran("NAME ID SIZE\n")
        if "mflux" in command:
            return Ran("41 /bin/zsh -c pgrep mflux\n")
        return Ran("7 uv run simile dolls paint\n8 python simile papercraft\n")

    monkeypatch.setattr(flux.subprocess, "run", run)
    monkeypatch.setattr(flux, "ours", lambda: {"7"})
    naps: list[float] = []
    monkeypatch.setattr(flux.time, "sleep", naps.append)

    assert flux.busy() == ["8 python simile papercraft"]

    calls = iter([["8 python simile papercraft"], []])
    monkeypatch.setattr(flux, "busy", lambda: next(calls))
    flux.wait_for_gpu(log=lambda _: None)
    assert naps == [flux.WAIT_S]


def test_this_process_and_what_started_it_are_its_own() -> None:
    assert {str(os.getpid()), str(os.getppid())} <= flux.ours()
