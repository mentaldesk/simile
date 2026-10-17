"""blender -b -P render_characters.py -- job.json result.json: character frames and light probes."""

import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import bmesh  # noqa: E402
import bpy  # noqa: E402

from simile.art.iso.in_blender import character  # noqa: E402
from simile.art.iso.in_blender import common as C  # noqa: E402


def scene(spec: dict, light: dict, look: dict, rect: list[int], catcher: bool = False):
    C.configure(look, light)
    C.clear()
    rig = character.build(spec)
    if catcher:
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30)
        C.mesh_object("catcher", bm, C.material("catcher", "white")).is_shadow_catcher = True
    C.setup_lights()
    C.frame(*rect)
    C.setup_render(rect[2], rect[3], transparent=True)
    return rig


def face(rig, degrees: float) -> None:
    rig.rotation_euler.z = math.radians(degrees)


def sheet(job: dict, spec: dict, out: Path) -> dict:
    """Every frame of one character, as <row>-<column>.png: a row per direction."""
    f = job["frame"]
    rect = [-f["anchor"][0], -f["anchor"][1], f["width"], f["height"]]
    rig = scene(spec, job["light"], job["look"], rect)
    # Frames this small render faster on the CPU than through the GPU's per-render setup.
    bpy.context.scene.cycles.device = "CPU"
    start, count = time.time(), 0
    for row, degrees in enumerate(job["directions"].values()):
        face(rig, degrees)
        column = 0
        for animation, params in job["animations"].items():
            for i in range(params["frames"]):
                character.pose(rig, animation, i, params)
                C.render(out / spec["key"] / f"{row}-{column}.png")
                column += 1
                count += 1
    seconds = time.time() - start
    C.progress(f"{spec['key']}: {count} frames in {seconds:.0f} s")
    return {"frames": count, "seconds": round(seconds, 1)}


def probe(job: dict, out: Path) -> dict:
    """The probe standing in each direction, under each set's light over a shadow catcher."""
    task, seconds = job["probe"], {}
    for light in [job["light"], *task["sets"]]:
        start = time.time()
        catcher = light["name"] != job["light"]["name"]
        rig = scene(task["character"], light, job["look"], task["rect"], catcher)
        for name, degrees in job["directions"].items():
            face(rig, degrees)
            character.pose(rig, "idle", 0, {"frames": 1})
            C.render(out / "probe" / light["name"] / f"{name}.png")
        seconds[light["name"]] = round(time.time() - start, 1)
        C.progress(f"probe under {light['name']} in {seconds[light['name']]} s")
    return seconds


def main() -> None:
    job, result_path = C.job()
    out = Path(job["out"])
    result: dict = {"characters": {}, "seconds": {}}
    start = time.time()
    if job.get("probe"):
        result["seconds"]["probe"] = probe(job, out)
    for spec in job["characters"]:
        result["characters"][spec["key"]] = sheet(job, spec, out)
    result["seconds"]["total"] = round(time.time() - start, 1)
    result_path.write_text(json.dumps(result, indent=2))


main()
