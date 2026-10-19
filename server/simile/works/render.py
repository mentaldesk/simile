from multiprocessing.connection import Connection
from typing import TYPE_CHECKING

from simile.art.iso.camera import TILE_M, TILE_W
from simile.art.iso.interior import FRAME_W_M, FRAME_Z, MOULDING_M
from simile.art.iso.town import STOREY_M
from simile.works.svg import BadSvg
from simile.world.map import MuralWall

if TYPE_CHECKING:
    import numpy as np
    from PIL import Image

PX_PER_M = TILE_W / TILE_M
PLASTER = (0.84, 0.8, 0.72)
PRIMED = (0.93, 0.91, 0.86)
PAINTING_M = (FRAME_W_M - 2 * MOULDING_M, FRAME_Z[1] - FRAME_Z[0] - 2 * MOULDING_M)
PAINTING_W = 960
STARTING = 60.0
WATCH_EVERY = 0.05


def metres(wall: MuralWall) -> tuple[float, float]:
    return wall.width * TILE_M, (wall.top - wall.bottom) * STOREY_M


def canvas(wall: MuralWall) -> tuple[int, int]:
    """A mural's size in px: an iso tile's width per tile, at the same scale up the wall."""
    width, height = metres(wall)
    return round(width * PX_PER_M), round(height * PX_PER_M)


def painting_canvas() -> tuple[int, int]:
    """A gallery painting's size in px: the frame's opening, `PAINTING_W` px across."""
    width, height = PAINTING_M
    return PAINTING_W, round(PAINTING_W * height / width)


def draw(
    svg: str,
    width: int,
    height: int,
    *,
    seed: int,
    timeout: float,
    memory: int,
    on_canvas: bool = False,
) -> bytes:
    """`render` in a child process, so an SVG that crashes resvg, keeps it busy or eats memory
    can't take the sim with it. Blocks until the child has started, and then for up to `timeout`
    seconds. `BadSvg` if it fails, crashes, runs out of time or uses more than `memory` bytes."""
    import multiprocessing
    import time

    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    child = context.Process(
        target=_draw, args=(send, svg, width, height, seed, on_canvas), daemon=True
    )
    child.start()
    send.close()
    try:
        if not receive.poll(STARTING):
            raise BadSvg("the renderer didn't start")
        receive.recv()
        deadline = time.monotonic() + timeout
        while not receive.poll(WATCH_EVERY):
            if time.monotonic() > deadline:
                raise BadSvg(f"it took more than {timeout:g} s to draw")
            if child.pid is not None and resident(child.pid) > memory:
                raise BadSvg(f"it took more than {memory // 2**20:,} MB to draw")
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


def resident(pid: int) -> int:
    """The bytes of memory process `pid` has resident, or 0 if that can't be found out."""
    import os
    import subprocess

    try:
        with open(f"/proc/{pid}/statm") as statm:
            return int(statm.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    except OSError:
        pass
    try:
        ps = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, timeout=1
        )
        return int(ps.stdout.strip() or 0) * 1024
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0


def _draw(send: Connection, svg: str, width: int, height: int, seed: int, on_canvas: bool) -> None:
    import importlib

    for module in ("numpy", "PIL.Image", "resvg_py"):
        importlib.import_module(module)
    send.send(None)
    try:
        send.send((True, render(svg, width, height, seed=seed, on_canvas=on_canvas)))
    except BaseException as error:  # resvg's panics are BaseExceptions
        send.send((False, str(error)))


def render(svg: str, width: int, height: int, *, seed: int, on_canvas: bool = False) -> bytes:
    """The SVG drawn at `width` × `height` and painted onto lightly weathered plaster, or onto a
    primed canvas, as a PNG. Call it through `draw`."""
    import io

    import resvg_py
    from PIL import Image

    drawn = bytes(resvg_py.svg_to_bytes(svg_string=svg, width=width, height=height))
    return finish(Image.open(io.BytesIO(drawn)), width, height, seed=seed, on_canvas=on_canvas)


def finish(
    picture: "Image.Image", width: int, height: int, *, seed: int, on_canvas: bool = False
) -> bytes:
    """The picture scaled to `width` × `height` and painted onto lightly weathered plaster, or
    onto a primed canvas, as a PNG."""
    import numpy as np
    from PIL import Image

    picture = picture.convert("RGBA")
    if picture.size != (width, height):
        picture = picture.resize((width, height), Image.Resampling.LANCZOS)
    paint = np.asarray(picture, dtype=np.float32) / 255
    if on_canvas:
        return _png(_primed(paint, width, height))
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
    return _png(out * grime[..., None])


def _primed(paint: "np.ndarray", width: int, height: int) -> "np.ndarray":
    """The paint on a primed canvas, with its weave showing faintly through."""
    import numpy as np

    x, y = np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32)
    weave = (np.cos(x * np.pi / 1.5)[None, :] + np.cos(y * np.pi / 1.5)[:, None]) / 4 + 0.5
    relief = (0.97 + 0.03 * weave)[..., None]
    cover = paint[..., 3:]
    return (np.array(PRIMED, dtype=np.float32) * (1 - cover) + paint[..., :3] * cover) * relief


def _png(rgb: "np.ndarray") -> bytes:
    import io

    import numpy as np
    from PIL import Image

    image = Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8), "RGB")
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
