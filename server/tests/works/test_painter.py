import asyncio
import logging
import sys
import threading
import time
import types
from collections.abc import Callable
from pathlib import Path

import pytest
from PIL import Image
from starlette.testclient import TestClient

from simile.app import create_app
from simile.schema import PLAYER_ID, Conversation, Medium
from simile.sim import ConversationEnded, ConversationStarted, world_of
from simile.works import DEFAULT_CONFIG
from simile.works.painter import (
    NO_TEXT,
    FakeImageModel,
    Painter,
    PaintingFailed,
    Talking,
    easel,
    image_prompt,
)

from .conftest import NOW

MakePackage = Callable[[dict[str, str]], str]


class Slow(FakeImageModel):
    """Takes `each` seconds a step, and notes how many paint at once."""

    def __init__(self, each: float = 0.0, steps: int = 4) -> None:
        super().__init__(steps=steps)
        self.each = each
        self.busy = 0
        self.most = 0
        self.lock = threading.Lock()

    def paint(
        self, prompt: str, width: int, height: int, seed: int, step: Callable[[], None]
    ) -> Image.Image:
        self.prompts.append(prompt)
        with self.lock:
            self.busy += 1
            self.most = max(self.most, self.busy)
        try:
            for _ in range(self.steps):
                step()
                time.sleep(self.each)
            return Image.new("RGB", (width, height))
        finally:
            with self.lock:
                self.busy -= 1


async def painted(painter: Painter, *prompts: str) -> list[Image.Image | BaseException]:
    async with painter:
        return await asyncio.gather(
            *(painter.paint(prompt, 64, 48, 1) for prompt in prompts), return_exceptions=True
        )


def test_paints_one_picture_at_a_time() -> None:
    model = Slow(each=0.01)

    pictures = asyncio.run(painted(Painter(model, timeout=10), "a", "b", "c"))

    assert [picture.size for picture in pictures] == [(64, 48)] * 3  # type: ignore[union-attr]
    assert model.most == 1
    assert model.prompts == ["a", "b", "c"]


def test_a_picture_that_fails_raises_painting_failed() -> None:
    [failed] = asyncio.run(painted(Painter(FakeImageModel(failing=True), timeout=10), "a"))

    assert isinstance(failed, PaintingFailed)
    assert "the fake image model failed" in str(failed)


def test_gives_up_on_a_picture_that_takes_too_long() -> None:
    model = Slow(each=0.05)

    [failed] = asyncio.run(painted(Painter(model, timeout=0.08), "a"))

    assert isinstance(failed, PaintingFailed)
    assert str(failed) == "it took more than 0.08 s to paint"


def test_waits_while_the_player_talks_without_counting_it() -> None:
    model = Slow(each=0.02)
    until = time.monotonic() + 0.3

    [picture] = asyncio.run(
        painted(Painter(model, timeout=0.2, waiting=lambda: time.monotonic() < until), "a")
    )

    assert isinstance(picture, Image.Image)
    assert time.monotonic() >= until


def test_paints_on_once_out_of_patience() -> None:
    started = time.monotonic()

    [picture] = asyncio.run(
        painted(Painter(Slow(), timeout=10, waiting=lambda: True, patience=0.3), "a")
    )

    assert isinstance(picture, Image.Image)
    assert 0.3 <= time.monotonic() - started < 2


def test_cancelling_stops_the_picture_at_its_next_step() -> None:
    model = Slow(each=0.05, steps=100)

    async def scenario() -> None:
        async with Painter(model, timeout=60) as painter:
            task = asyncio.create_task(painter.paint("a", 64, 48, 1))
            await asyncio.sleep(0.1)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await asyncio.sleep(0.2)

    asyncio.run(scenario())

    assert model.prompts == ["a"]
    assert model.busy == 0


def conversation(*participants: str) -> Conversation:
    return Conversation(id="c1", participants=list(participants), started=NOW)


def test_talking_is_while_the_player_is_in_a_conversation() -> None:
    talking = Talking()
    others = conversation("kofi", "priya").model_copy(update={"id": "c2"})

    talking.on_started(ConversationStarted(others))
    assert not talking()
    talking.on_started(ConversationStarted(conversation("kofi", PLAYER_ID)))
    assert talking()
    talking.on_ended(ConversationEnded(conversation("kofi", PLAYER_ID)))
    assert not talking()


@pytest.mark.parametrize("medium", [Medium.MURAL, Medium.PAINTING], ids=str)
def test_the_image_prompt_is_the_picture_in_the_games_look_with_no_lettering(
    medium: Medium,
) -> None:
    prompt = image_prompt("A heron on a lock gate at dusk.", medium)

    assert prompt.startswith("A heron on a lock gate at dusk. Hand-painted ")
    assert prompt.endswith(" No text, no lettering, no logos.")
    assert NO_TEXT == "No text, no lettering, no logos."


async def opened() -> Painter | None:
    async with easel() as painter:
        return painter


def test_no_painter_unless_asked_for(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIMILE_IMAGES", raising=False)

    assert asyncio.run(opened()) is None


def fake_flux(
    monkeypatch: pytest.MonkeyPatch, path: Path | None, model: FakeImageModel | None = None
) -> list[tuple[Path, int | None]]:
    loaded: list[tuple[Path, int | None]] = []

    class FluxKlein(FakeImageModel):
        def __init__(self, path: Path, *, bits: int | None, steps: int) -> None:
            super().__init__(steps=steps)
            loaded.append((path, bits))

        def load(self) -> None:
            if model is not None and model.failing:
                raise RuntimeError("out of memory")

    flux = types.ModuleType("simile.works.flux")
    flux.FluxKlein = FluxKlein  # type: ignore[attr-defined]
    flux.downloaded = lambda _: path  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "simile.works.flux", flux)
    monkeypatch.setenv("SIMILE_IMAGES", "1")
    return loaded


def test_loads_the_image_model_once_when_asked_for_and_downloaded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    loaded = fake_flux(monkeypatch, tmp_path)

    async def scenario() -> Image.Image:
        async with easel() as painter:
            assert painter is not None
            return await painter.paint("a", 64, 48, 1)

    assert asyncio.run(scenario()).size == (64, 48)
    assert loaded == [(tmp_path, DEFAULT_CONFIG.image_bits)]


@pytest.mark.parametrize(
    ("why", "setup"),
    [
        ("isn't installed", lambda m, p: m.setitem(sys.modules, "simile.works.flux", None)),
        ("isn't downloaded", lambda m, p: fake_flux(m, None)),
        ("Couldn't load", lambda m, p: fake_flux(m, p, FakeImageModel(failing=True))),
    ],
)
def test_svg_without_the_extra_the_download_or_a_model_that_loads(
    why: str,
    setup: Callable[[pytest.MonkeyPatch, Path], object],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("SIMILE_IMAGES", "1")
    setup(monkeypatch, tmp_path)

    with caplog.at_level(logging.WARNING):
        assert asyncio.run(opened()) is None

    assert why in caplog.text


def lifespans(make_package: MakePackage, *modules: str) -> str:
    return make_package(
        {
            f"{module}/lifespan.py": f"from simile.{module}.lifespan import lifespan\n"
            for module in modules
        }
    )


def test_the_server_gives_the_maker_the_painter_and_waits_while_the_player_talks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, make_package: MakePackage
) -> None:
    fake_flux(monkeypatch, tmp_path)
    app = create_app(lifespans(make_package, "llm", "memory", "works"))

    with TestClient(app):
        painter = app.state.maker.painter
        assert isinstance(painter, Painter)
        assert not painter.waiting()
        world_of(app).bus.publish(ConversationStarted(conversation("kofi", PLAYER_ID)))
        assert painter.waiting()
        world_of(app).bus.publish(ConversationEnded(conversation("kofi", PLAYER_ID)))
        assert not painter.waiting()


def test_the_server_draws_svg_without_images(
    monkeypatch: pytest.MonkeyPatch, make_package: MakePackage
) -> None:
    monkeypatch.delenv("SIMILE_IMAGES", raising=False)
    app = create_app(lifespans(make_package, "works"))

    with TestClient(app):
        assert app.state.maker.painter is None


@pytest.mark.mlx
def test_flux_paints_a_small_picture() -> None:
    pytest.importorskip("mflux")
    from simile.works.flux import FluxKlein, downloaded

    path = downloaded(DEFAULT_CONFIG.image_model)
    if path is None:
        pytest.skip(f"{DEFAULT_CONFIG.image_model} isn't downloaded")
    steps: list[None] = []

    async def scenario() -> Image.Image:
        model = FluxKlein(path, bits=DEFAULT_CONFIG.image_bits, steps=2)
        async with Painter(model, timeout=300) as painter:
            painter.waiting = lambda: bool(steps.append(None))
            return await painter.paint(
                image_prompt("A red apple on a blue table.", Medium.PAINTING), 256, 256, 1
            )

    picture = asyncio.run(scenario())

    assert picture.size == (256, 256)
    assert len(picture.convert("RGB").getcolors(256 * 256) or []) > 100
    assert len(steps) == 3
