from multiprocessing.connection import Connection
from typing import TYPE_CHECKING

from simile.art.iso.camera import TILE_M, TILE_W
from simile.art.iso.town import STOREY_M
from simile.works.svg import BadSvg
from simile.world.map import MuralWall

if TYPE_CHECKING:
    import numpy as np

PX_PER_M = TILE_W / TILE_M
PLASTER = (0.84, 0.8, 0.72)


def metres(wall: MuralWall) -> tuple[float, float]:
    return wall.width * TILE_M, (wall.top - wall.bottom) * STOREY_M


def canvas(wall: MuralWall) -> tuple[int, int]:
    """A mural's size in px: an iso tile's width per tile, at the same scale up the wall."""
    width, height = metres(wall)
    return round(width * PX_PER_M), round(height * PX_PER_M)


def draw(svg: str, width: int, height: int, *, seed: int, timeout: float) -> bytes:
    """`render` in a child process, so an SVG that crashes resvg or keeps it busy can't take the
    sim with it. Blocks for up to `timeout` seconds. `BadSvg` if it fails, crashes or runs out
    of time."""
    import multiprocessing

    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    child = context.Process(target=_draw, args=(send, svg, width, height, seed), daemon=True)
    child.start()
    send.close()
    try:
        if not receive.poll(timeout):
            raise BadSvg(f"it took more than {timeout:g} s to draw")
        drawn, result = receive.recv()
    except EOFError:
        raise BadSvg("it crashed the renderer") from None
    finally:
        child.kill()
        child.join()
        receive.close()
    if not drawn:
        raise BadSvg(f"it couldn't be drawn ({result})")
    return result


def _draw(send: Connection, svg: str, width: int, height: int, seed: int) -> None:
    try:
        send.send((True, render(svg, width, height, seed=seed)))
    except BaseException as error:  # resvg's panics are BaseExceptions
        send.send((False, str(error)))


def render(svg: str, width: int, height: int, *, seed: int) -> bytes:
    """The SVG drawn at `width` × `height` and painted onto lightly weathered plaster, as a PNG.
    Call it through `draw`."""
    import io

    import numpy as np
    import resvg_py
    from PIL import Image

    drawn = bytes(resvg_py.svg_to_bytes(svg_string=svg, width=width, height=height))
    paint = np.asarray(Image.open(io.BytesIO(drawn)).convert("RGBA"), dtype=np.float32) / 255
    rng = np.random.default_rng(seed)
    wall, relief = _plaster(rng, width, height)
    rows = np.linspace(0, 1, height, dtype=np.float32)[:, None]
    columns = np.linspace(0, 1, width, dtype=np.float32)[None, :]
    edge = np.minimum(np.minimum(rows, 1 - rows) * height, np.minimum(columns, 1 - columns) * width)
    near_edge = np.clip(1 - edge / (0.1 * min(width, height)), 0, 1)
    flakes = _noise(rng, width, height, 24) * 0.7 + _noise(rng, width, height, 4) * 0.3
    worn = np.clip((flakes - 0.84 + 0.08 * rows**2 + 0.1 * near_edge) * 5, 0, 0.4)
    cover = paint[..., 3] * (1 - worn) * 0.97
    colour = paint[..., :3] * (0.9 + 0.1 * relief[..., None]) * relief[..., None] ** 0.6
    colour = colour * 0.94 + 0.06 * wall
    out = wall * (1 - cover[..., None]) + colour * cover[..., None]
    streaks = _noise(rng, width, 1, 6).repeat(height, axis=0) * (1 - rows) ** 2
    grime = 1 - 0.08 * streaks - 0.12 * rows**4 * _noise(rng, width, height, 20)
    image = Image.fromarray((np.clip(out * grime[..., None], 0, 1) * 255).astype(np.uint8), "RGB")
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def _noise(rng: "np.random.Generator", width: int, height: int, cell: float) -> "np.ndarray":
    """Smooth noise from 0 to 1 that varies over about `cell` px."""
    import numpy as np
    from PIL import Image

    small = rng.random((max(2, round(height / cell)), max(2, round(width / cell))))
    field = Image.fromarray(small.astype(np.float32), "F").resize((width, height), Image.BICUBIC)
    return np.clip(np.asarray(field), 0, 1)


def _plaster(
    rng: "np.random.Generator", width: int, height: int
) -> tuple["np.ndarray", "np.ndarray"]:
    import numpy as np

    relief = (
        0.9
        + 0.08 * _noise(rng, width, height, 40)
        + 0.05 * _noise(rng, width, height, 6)
        + 0.03 * rng.random((height, width))
    ).astype(np.float32)
    return np.array(PLASTER, dtype=np.float32) * relief[..., None], relief
