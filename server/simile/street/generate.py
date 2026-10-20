import os
from pathlib import Path

from simile.street.plan import MARKERS_IMAGE, dumps, tmj
from simile.street.preview import markers, render
from simile.street.village import village
from simile.world.map import FLOORS, MapKind

PREVIEW = "preview.png"


def generate(out: Path) -> list[Path]:
    """Write every street to out/, every floor to out/floors/, the marker tileset their tile
    layers use, and a preview of the whole village."""
    plans = village()
    out.mkdir(parents=True, exist_ok=True)
    tileset = out / MARKERS_IMAGE
    markers().save(tileset)
    written = [tileset]
    for plan in plans:
        folder = out if plan.kind is MapKind.STREET else out / FLOORS
        folder.mkdir(exist_ok=True)
        path = folder / f"{plan.id}.tmj"
        path.write_text(dumps(tmj(plan, Path(os.path.relpath(tileset, folder)).as_posix())))
        written.append(path)
    render(plans).save(out / PREVIEW)
    return [*written, out / PREVIEW]
