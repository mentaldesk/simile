import asyncio
import logging
import math
import os
import threading
import time
from collections.abc import AsyncIterator, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Protocol, Self

from simile.schema import PLAYER_ID, Id, Medium
from simile.sim import ConversationEnded, ConversationStarted
from simile.works.config import DEFAULT_CONFIG, WorksConfig

if TYPE_CHECKING:
    from PIL import Image

logger = logging.getLogger(__name__)

IMAGES_ENV = "SIMILE_IMAGES"
WAIT_EVERY = 0.25
NO_TEXT = "No text, no lettering, no logos."
STYLES = {
    Medium.MURAL: "Hand-painted street mural, flat matte acrylic on plaster, simplified shapes, "
    "bold flat colour, clean outlines, stylised and warm like the art in a cosy village game. "
    "Painted, not photographed. The artwork alone fills the picture edge to edge, seen straight "
    "on: no wall edges, no frame, no surroundings.",
    Medium.PAINTING: "Hand-painted acrylic painting on canvas with visible brushwork, stylised "
    "and warm like the art in a cosy village game. The artwork alone fills the picture edge to "
    "edge, seen straight on: no frame, no surroundings.",
}


def image_prompt(picture: str, medium: Medium) -> str:
    """What the image model paints: the artist's picture, the game's look, and no lettering."""
    return f"{picture} {STYLES[medium]} {NO_TEXT}"


class PaintingFailed(Exception):
    """The image model couldn't paint the picture, or took too long."""


class Talking:
    """Whether the player is in a conversation, from the sim's events, so pictures wait for it."""

    def __init__(self) -> None:
        self._conversations: set[Id] = set()

    def on_started(self, event: ConversationStarted) -> None:
        if PLAYER_ID in event.conversation.participants:
            self._conversations.add(event.conversation.id)

    def on_ended(self, event: ConversationEnded) -> None:
        self._conversations.discard(event.conversation.id)

    def __call__(self) -> bool:
        return bool(self._conversations)


class ImageModel(Protocol):
    """Blocking text to image. `Painter` only ever calls it from its one thread."""

    def load(self) -> None: ...

    def paint(
        self, prompt: str, width: int, height: int, seed: int, step: Callable[[], None]
    ) -> "Image.Image":
        """About `width` × `height`. Calls `step` before it starts and between its steps, and
        stops with whatever `step` raises."""
        ...


class Painter:
    """One image model, loaded once, painting one picture at a time on its own thread. Before it
    starts and between steps it waits while `waiting()`, up to `patience` seconds a picture all
    told, and it gives up on a picture after `timeout` seconds of painting, not counting the
    waits."""

    def __init__(
        self,
        model: ImageModel,
        *,
        timeout: float,
        waiting: Callable[[], bool] = lambda: False,
        patience: float = math.inf,
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.waiting = waiting
        self.patience = patience
        self._thread = ThreadPoolExecutor(max_workers=1, thread_name_prefix="simile-painter")
        self._closed = threading.Event()

    async def __aenter__(self) -> Self:
        try:
            await asyncio.get_running_loop().run_in_executor(self._thread, self.model.load)
        except BaseException:
            self._thread.shutdown(wait=False)
            raise
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        self._closed.set()
        self._thread.shutdown(wait=False, cancel_futures=True)

    async def paint(self, prompt: str, width: int, height: int, seed: int) -> "Image.Image":
        """`PaintingFailed` if it fails or takes too long."""
        cancelled = threading.Event()
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(
                self._thread, self._paint, prompt, width, height, seed, cancelled
            )
        except asyncio.CancelledError:
            cancelled.set()
            raise
        except PaintingFailed:
            raise
        except Exception as error:
            raise PaintingFailed(f"{type(error).__name__}: {error}") from error

    def _paint(
        self, prompt: str, width: int, height: int, seed: int, cancelled: threading.Event
    ) -> "Image.Image":
        painting = waited = 0.0
        since = time.monotonic()

        def step() -> None:
            nonlocal painting, waited, since
            painting += time.monotonic() - since
            since = time.monotonic()
            while self.waiting() and waited < self.patience and not self._stopped(cancelled):
                time.sleep(WAIT_EVERY)
                waited += time.monotonic() - since
                since = time.monotonic()
            if self._stopped(cancelled):
                raise PaintingFailed("it was stopped")
            if painting > self.timeout:
                raise PaintingFailed(f"it took more than {self.timeout:g} s to paint")

        return self.model.paint(prompt, width, height, seed, step)

    def _stopped(self, cancelled: threading.Event) -> bool:
        return cancelled.is_set() or self._closed.is_set()


class FakeImageModel:
    """Paints two bands of colour from the prompt at once, without MLX, for tests and dry runs.
    With `failing`, it raises instead."""

    def __init__(self, *, failing: bool = False, steps: int = 4) -> None:
        self.failing = failing
        self.steps = steps
        self.prompts: list[str] = []

    def load(self) -> None:
        pass

    def paint(
        self, prompt: str, width: int, height: int, seed: int, step: Callable[[], None]
    ) -> "Image.Image":
        import zlib

        from PIL import Image

        self.prompts.append(prompt)
        for _ in range(self.steps):
            step()
        if self.failing:
            raise RuntimeError("the fake image model failed")
        hue = zlib.crc32(prompt.encode()) % 256
        picture = Image.new("HSV", (width, height), (hue, 160, 200))
        picture.paste((hue, 120, 90), (0, height // 2, width, height))
        return picture.convert("RGB")


@asynccontextmanager
async def easel(
    config: WorksConfig = DEFAULT_CONFIG, waiting: Callable[[], bool] = lambda: False
) -> AsyncIterator[Painter | None]:
    """The image model with `SIMILE_IMAGES=1`, on Apple Silicon with the `images` extra and the
    model downloaded, or None, and murals and paintings are SVG. Never downloads."""
    if os.environ.get(IMAGES_ENV) != "1":
        yield None
        return
    try:
        from simile.works.flux import FluxKlein, downloaded
    except ImportError:
        logger.warning(
            "SIMILE_IMAGES=1 but the images extra isn't installed, so murals and paintings are SVG"
        )
        yield None
        return
    path = downloaded(config.image_model)
    if path is None:
        logger.warning(
            "SIMILE_IMAGES=1 but %s isn't downloaded, so murals and paintings are SVG. "
            "Run `uv run simile works download`.",
            config.image_model,
        )
        yield None
        return
    started = time.perf_counter()
    model = FluxKlein(path, bits=config.image_bits, steps=config.image_steps)
    try:
        painter = await Painter(
            model, timeout=config.image_timeout, waiting=waiting, patience=config.image_patience
        ).__aenter__()
    except Exception:
        logger.warning(
            "Couldn't load the image model, so murals and paintings are SVG", exc_info=True
        )
        yield None
        return
    logger.info(f"Loaded the image model in {time.perf_counter() - started:.1f}s")
    try:
        yield painter
    finally:
        await painter.__aexit__(None, None, None)
