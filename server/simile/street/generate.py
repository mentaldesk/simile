import os
from pathlib import Path

from PIL import Image, ImageDraw

from simile.street.jump import JUMP_FILE
from simile.street.jump import dumps as jump_json
from simile.street.plan import MARKERS_IMAGE, Plan, dumps, tmj
from simile.street.preview import markers, render
from simile.street.sewers import levels
from simile.street.village import village
from simile.world.map import FLOORS, LEVELS, MapKind

PREVIEW = "preview.png"


def generate(out: Path) -> list[Path]:
    """Write the streets to out/, the floors to out/floors/, each level to out/levels/<n>/, the
    marker tileset their tile layers use, and previews of the village and the levels."""
    plans = village()
    pool = levels()
    out.mkdir(parents=True, exist_ok=True)
    tileset = out / MARKERS_IMAGE
    markers().save(tileset)
    written = [tileset]

    def write(plan: Plan, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{plan.id}.tmj"
        path.write_text(dumps(tmj(plan, Path(os.path.relpath(tileset, folder)).as_posix())))
        written.append(path)

    for plan in plans:
        write(plan, out if plan.kind is MapKind.STREET else out / FLOORS)
    for number, plan in enumerate(pool):
        write(plan, out / LEVELS / str(number))
    (out / JUMP_FILE).write_text(jump_json())
    render(plans).save(out / PREVIEW)
    stacked(pool).save(out / LEVELS / PREVIEW)
    return [*written, out / JUMP_FILE, out / PREVIEW, out / LEVELS / PREVIEW]


def stacked(pool: list[Plan]) -> Image.Image:
    """Each level's preview, one under another, level 0 at the top."""
    panels = [render([plan]) for plan in pool]
    image = Image.new("RGBA", (max(p.width for p in panels), sum(p.height for p in panels)))
    draw, top = ImageDraw.Draw(image), 0
    for number, panel in enumerate(panels):
        image.paste(panel, (0, top))
        draw.text((140, top + 4), f"LEVEL {number}", fill=(255, 255, 255, 255))
        top += panel.height
    return image
