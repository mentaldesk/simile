"""blender -b -P render_scenery.py -- job.json result.json: a set's scenery renders."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import bpy  # noqa: E402

from simile.art.iso.in_blender import common as C  # noqa: E402
from simile.art.iso.in_blender import scenery as S  # noqa: E402
from simile.art.iso.in_blender.lightmap import render_lightmap  # noqa: E402

DRAWN = ("MESH", "FONT")


def build(spec: dict) -> None:
    if spec["type"] == "building":
        S.build_building(spec)
    else:
        S.build_prop(spec)


def ground(job: dict, out: Path, result: dict) -> None:
    C.clear()
    town = job["town"]
    C.group("ground")
    S.build_ground(town["ground"])
    for spec in [*town["buildings"], *town["props"]]:
        C.group(spec["id"])
        build(spec)
    for obj in bpy.context.scene.objects:
        if obj.type in DRAWN and obj["group"] != "ground":
            obj.visible_camera = False
    C.group("")
    C.setup_lights()
    if task := job.get("ground"):
        x0, y0, w, h = task["rect"]
        C.frame(x0, y0, w, h)
        C.setup_render(w, h, transparent=True)
        result["seconds"]["ground"] = round(C.render(out / "ground.png"), 1)
        C.progress(f"ground {w}x{h} in {result['seconds']['ground']} s")
    if task := job.get("lightmap"):
        seconds = render_lightmap(out, town["width"], town["height"], task["px_per_tile"])
        result["seconds"]["lightmap"] = round(seconds, 1)
        C.progress(f"light map in {result['seconds']['lightmap']} s")


def sprite(task: dict, out: Path) -> dict:
    C.clear()
    C.group("target")
    build(task["target"])
    targets = [o for o in bpy.context.scene.objects if o.type in DRAWN]
    C.group("context")
    for spec in task["context"]:
        build(spec)
    for obj in bpy.context.scene.objects:
        if obj.type in DRAWN and obj["group"] == "context":
            obj.visible_camera = False
    C.group("")
    S.ground_plane(*task["centre"])
    C.setup_lights()
    rect = C.screen_box(targets)
    C.frame(*rect)
    C.setup_render(rect[2], rect[3], transparent=True)
    seconds = C.render(out / "sprites" / f"{task['key']}.png")
    C.progress(f"{task['key']} {rect[2]}x{rect[3]} in {seconds:.1f} s")
    return {"rect": list(rect), "seconds": round(seconds, 2)}


def main() -> None:
    job, result_path = C.job()
    out = Path(job["out"])
    C.configure(job["look"], job["light"])
    result: dict = {"seconds": {}, "sprites": {}}
    start = time.time()
    if job.get("ground") or job.get("lightmap"):
        ground(job, out, result)
    for task in job["sprites"]:
        result["sprites"][task["key"]] = sprite(task, out)
    result["seconds"]["sprites"] = round(sum(s["seconds"] for s in result["sprites"].values()), 1)
    result["seconds"]["total"] = round(time.time() - start, 1)
    result_path.write_text(json.dumps(result, indent=2))


main()
