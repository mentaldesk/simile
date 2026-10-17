from typing import TYPE_CHECKING

from simile.art.iso.camera import TILE_M, TILE_W
from simile.art.iso.town import STOREY_M
from simile.works.svg import BadSvg
from simile.world.map import MuralWall

if TYPE_CHECKING:
    import numpy as np

PX_PER_M = TILE_W / TILE_M
PLASTER = (0.84, 0.8, 0.72)
BRICK = (0.6, 0.33, 0.25)
MORTAR = (0.72, 0.69, 0.63)
BRICK_PX = (round(0.215 * PX_PER_M), round(0.075 * PX_PER_M))


def metres(wall: MuralWall) -> tuple[float, float]:
    return wall.width * TILE_M, (wall.top - wall.bottom) * STOREY_M


def canvas(wall: MuralWall) -> tuple[int, int]:
    """A mural's size in px: an iso tile's width per tile, at the same scale up the wall."""
    width, height = metres(wall)
    return round(width * PX_PER_M), round(height * PX_PER_M)


def brick(wall: str) -> bool:
    return sum(map(ord, wall)) % 2 == 1


def render(svg: str, width: int, height: int, *, seed: int, bricks: bool = False) -> bytes:
    """The SVG drawn at `width` × `height` and painted onto weathered plaster or brick, as a PNG.
    `BadSvg` if resvg can't draw it."""
    import io

    import numpy as np
    import resvg_py
    from PIL import Image

    try:
        drawn = bytes(resvg_py.svg_to_bytes(svg_string=svg, width=width, height=height))
    except ValueError as error:
        raise BadSvg(f"it couldn't be drawn ({error})") from None
    paint = np.asarray(Image.open(io.BytesIO(drawn)).convert("RGBA"), dtype=np.float32) / 255
    rng = np.random.default_rng(seed)
    wall, relief = (_bricks if bricks else _plaster)(rng, width, height)
    rows = np.linspace(0, 1, height, dtype=np.float32)[:, None]
    columns = np.linspace(0, 1, width, dtype=np.float32)[None, :]
    edge = np.minimum(np.minimum(rows, 1 - rows) * height, np.minimum(columns, 1 - columns) * width)
    near_edge = np.clip(1 - edge / (0.12 * min(width, height)), 0, 1)
    flakes = _noise(rng, width, height, 28) * 0.65 + _noise(rng, width, height, 4) * 0.35
    worn = np.clip((flakes - 0.85 + 0.1 * rows**2 + 0.1 * near_edge) * 10, 0, 1)
    cover = paint[..., 3] * (1 - worn) * 0.97
    colour = paint[..., :3] * (0.9 + 0.1 * relief[..., None]) * relief[..., None] ** 0.6
    colour = colour * 0.93 + 0.07 * wall
    out = wall * (1 - cover[..., None]) + colour * cover[..., None]
    streaks = _noise(rng, width, 1, 6).repeat(height, axis=0) * (1 - rows) ** 2
    grime = 1 - 0.1 * streaks - 0.16 * rows**4 * _noise(rng, width, height, 20)
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


def _bricks(
    rng: "np.random.Generator", width: int, height: int
) -> tuple["np.ndarray", "np.ndarray"]:
    import numpy as np

    along, high = BRICK_PX
    y = np.arange(height)[:, None]
    x = np.arange(width)[None, :] + (y // high % 2) * (along // 2)
    mortar = (y % high == 0) | (x % along == 0)
    tint = rng.normal(1, 0.08, (height // high + 1, width // along + 2)).astype(np.float32)
    shade = tint[y // high, x // along]
    relief = np.where(mortar, 0.82, shade) * (0.96 + 0.04 * rng.random((height, width)))
    base = np.where(mortar[..., None], np.array(MORTAR), np.array(BRICK) * shade[..., None])
    return base.astype(np.float32) * (0.96 + 0.04 * relief[..., None]), relief.astype(np.float32)
