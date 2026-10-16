"""Inside Blender: the light on the ground from straight above, in three passes."""

import time
from pathlib import Path

import bpy
import numpy as np

from simile.art.iso import camera as cam
from simile.art.iso.in_blender.common import L, W, link, render, setup_render

PASSES = (
    ("sunsky", True, True, False),
    ("sun", True, False, False),
    ("lights", False, False, True),
)
MARKINGS = ("inlay", "tactile", "line", "zebra")


def render_lightmap(out: Path, width: int, height: int, px: int) -> float:
    """Write light_<pass>.npy: linear RGB, a row per px from the map's north edge."""
    sc = bpy.context.scene
    white = bpy.data.materials.new("white")
    for obj in sc.objects:
        if obj.type not in ("MESH", "FONT"):
            continue
        ground = obj["group"] == "ground"
        obj.visible_camera = ground
        obj.hide_render = ground and obj.name.startswith(MARKINGS)
        if ground:
            for slot in obj.material_slots:
                slot.material = white
    glowing = [
        (n.inputs["Emission Strength"], n.inputs["Emission Strength"].default_value)
        for m in bpy.data.materials
        if m.node_tree
        for n in m.node_tree.nodes
        if n.type == "BSDF_PRINCIPLED" and n.inputs["Emission Strength"].default_value > 0
    ]
    data = bpy.data.cameras.new("top")
    data.type = "ORTHO"
    data.sensor_fit = "HORIZONTAL"
    data.ortho_scale = width * cam.TILE_M
    top = link(bpy.data.objects.new("top", data))
    top.location = W(width / 2, height / 2, 200)
    data.clip_end = 400
    sc.camera = top
    setup_render(width * px, height * px, transparent=False)
    sc.cycles.samples = 32
    sc.cycles.max_bounces = 0
    sc.render.image_settings.file_format = "OPEN_EXR"
    sc.render.image_settings.color_mode = "RGB"
    sc.render.image_settings.color_depth = "32"
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0
    sun = sc.objects["sun"]
    sky = next(n for n in sc.world.node_tree.nodes if n.type == "BACKGROUND").inputs["Strength"]
    lamps = [o for o in sc.objects if o.type == "LIGHT" and o.name.startswith("lamp")]
    start = time.time()
    for name, with_sun, with_sky, with_lights in PASSES:
        sun.hide_render = not with_sun
        sky.default_value = L["light"]["sky_strength"] if with_sky else 0.0
        for lamp in lamps:
            lamp.hide_render = not with_lights
        for socket, strength in glowing:
            socket.default_value = strength if with_lights else 0.0
        exr = out / f"light_{name}.exr"
        render(exr)
        np.save(out / f"light_{name}.npy", read_linear(exr))
    return time.time() - start


def read_linear(path: Path) -> np.ndarray:
    image = bpy.data.images.load(str(path))
    w, h = image.size
    pixels = np.empty(w * h * 4, np.float32)
    image.pixels.foreach_get(pixels)
    bpy.data.images.remove(image)
    return pixels.reshape(h, w, 4)[::-1, :, :3].copy()
