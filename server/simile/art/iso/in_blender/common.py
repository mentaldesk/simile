"""Inside Blender: the look, materials, primitives, camera and lights every render shares."""

import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import bmesh
import bpy
from mathutils import Matrix, Vector

from simile.art import palette
from simile.art.iso import camera as cam
from simile.art.iso.lighting import to_sun

L: dict[str, Any] = {}
STATE: dict[str, Any] = {"group": "", "materials": {}}
FONTS = (
    Path("/Library/Fonts/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
)
FORWARD = Vector(cam.FORWARD)


def job() -> tuple[dict[str, Any], Path]:
    """The job file this script was started with, and where to write the result."""
    argv = sys.argv[sys.argv.index("--") + 1 :]
    return json.loads(Path(argv[0]).read_text()), Path(argv[1])


def progress(message: str) -> None:
    print(f"ISO {message}", flush=True)


def configure(look: dict[str, Any], light: dict[str, Any]) -> None:
    L.clear()
    L.update(look)
    L["light"] = light


def emit(kind: str, strength: float) -> float:
    return strength * L["light"]["emit"].get(kind, 1.0)


def lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def colour(name: str, sat: float | None = None, val: float = 1.0, tone: bool = True) -> tuple:
    hexv = palette.PALETTE.get(name, name)
    r, g, b = (lin(v) for v in palette.hex_to_rgb(hexv))
    s = L["saturation"] if sat is None else sat
    if tone:
        val *= L["value"]
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return tuple(val * (lum + (c - lum) * s) for c in (r, g, b)) + (1.0,)


def tree_of(owner):
    if owner.node_tree is None:
        owner.use_nodes = True
    return owner.node_tree


def material(
    name: str,
    base: str,
    rough: float = 0.8,
    metal: float = 0.0,
    sat: float | None = None,
    val: float = 1.0,
    emit: str | None = None,
    strength: float = 0.0,
    pattern: str | None = None,
    alt: str | None = None,
    scale: float = 1.0,
) -> bpy.types.Material:
    key = (name, base, rough, metal, sat, val, emit, strength, pattern, alt, scale)
    cache = STATE["materials"]
    if key in cache:
        return cache[key]
    mat = bpy.data.materials.new(name)
    nt = tree_of(mat)
    nodes, links = nt.nodes, nt.links
    bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    c1 = colour(base, sat, val)
    coord = nodes.new("ShaderNodeTexCoord")

    if pattern == "pavers":
        tex = nodes.new("ShaderNodeTexBrick")
        tex.offset = 0.5 if alt is None else 0.0
        tex.inputs["Color1"].default_value = c1
        tex.inputs["Color2"].default_value = colour(base, sat, val * 0.9)
        tex.inputs["Mortar"].default_value = colour(base, sat, val * 0.62)
        tex.inputs["Scale"].default_value = 1.0
        tex.inputs["Mortar Size"].default_value = 0.012
        tex.inputs["Brick Width"].default_value = 0.55 * scale
        tex.inputs["Row Height"].default_value = 0.55 * scale
        links.new(coord.outputs["Object"], tex.inputs["Vector"])
        col_out = tex.outputs["Color"]
    elif pattern == "stripes":
        tex = nodes.new("ShaderNodeTexWave")
        tex.wave_type = "BANDS"
        tex.bands_direction = "X"
        tex.inputs["Scale"].default_value = 1.0
        tex.inputs["Distortion"].default_value = 0.0
        links.new(coord.outputs["Object"], tex.inputs["Vector"])
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.interpolation = "CONSTANT"
        ramp.color_ramp.elements[0].color = c1
        ramp.color_ramp.elements[1].position = 0.5
        ramp.color_ramp.elements[1].color = colour(alt or "white", sat, val)
        links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        col_out = ramp.outputs["Color"]
    elif pattern in ("noise", "grass", "wall"):
        tex = nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = 9.0 * scale if pattern == "grass" else 3.0 * scale
        tex.inputs["Detail"].default_value = 4.0
        if pattern == "wall":
            mapping = nodes.new("ShaderNodeMapping")
            mapping.inputs["Scale"].default_value = (1.0, 1.0, 0.12)
            links.new(coord.outputs["Object"], mapping.inputs["Vector"])
            links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
        else:
            links.new(coord.outputs["Object"], tex.inputs["Vector"])
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.35
        ramp.color_ramp.elements[0].color = colour(alt or base, sat, val * 0.82)
        ramp.color_ramp.elements[1].position = 0.65
        ramp.color_ramp.elements[1].color = c1
        links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        col_out = ramp.outputs["Color"]
    else:
        rgb = nodes.new("ShaderNodeRGB")
        rgb.outputs[0].default_value = c1
        col_out = rgb.outputs[0]

    ao = nodes.new("ShaderNodeAmbientOcclusion")
    ao.inputs["Distance"].default_value = 0.9
    ao.samples = 8
    fac = nodes.new("ShaderNodeMath")
    fac.operation = "MULTIPLY_ADD"
    fac.inputs[1].default_value = 0.45
    fac.inputs[2].default_value = 0.55
    links.new(ao.outputs["AO"], fac.inputs[0])
    shade = fac.outputs[0]
    if pattern in ("pavers", "noise", "wall"):
        grime = nodes.new("ShaderNodeTexNoise")
        grime.inputs["Scale"].default_value = 0.45
        grime.inputs["Detail"].default_value = 3.0
        links.new(coord.outputs["Object"], grime.inputs["Vector"])
        span = nodes.new("ShaderNodeMapRange")
        span.inputs["From Min"].default_value = 0.35
        span.inputs["From Max"].default_value = 0.65
        span.inputs["To Min"].default_value = 0.7
        span.inputs["To Max"].default_value = 1.0
        links.new(grime.outputs["Fac"], span.inputs["Value"])
        both = nodes.new("ShaderNodeMath")
        both.operation = "MULTIPLY"
        links.new(shade, both.inputs[0])
        links.new(span.outputs["Result"], both.inputs[1])
        shade = both.outputs[0]
    if pattern == "pavers":
        bump = nodes.new("ShaderNodeBump")
        bump.invert = True
        bump.inputs["Strength"].default_value = 0.5
        bump.inputs["Distance"].default_value = 0.02
        links.new(tex.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    mul = nodes.new("ShaderNodeVectorMath")
    mul.operation = "SCALE"
    links.new(col_out, mul.inputs[0])
    links.new(shade, mul.inputs["Scale"])
    links.new(mul.outputs[0], bsdf.inputs["Base Color"])

    if emit:
        bsdf.inputs["Emission Color"].default_value = colour(emit, 1.0, tone=False)
        bsdf.inputs["Emission Strength"].default_value = strength
    cache[key] = mat
    return mat


def group(name: str) -> None:
    """Tag the objects made from now on, so a render can choose what the camera sees."""
    STATE["group"] = name


def link(obj):
    bpy.context.scene.collection.objects.link(obj)
    obj["group"] = STATE["group"]
    return obj


def mesh_object(name: str, bm: bmesh.types.BMesh, mat, smooth: bool = False, bevel: float = 0.0):
    me = bpy.data.meshes.new(name)
    if smooth:
        for f in bm.faces:
            f.smooth = True
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    obj = link(bpy.data.objects.new(name, me))
    if bevel:
        mod = obj.modifiers.new("bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 2
        mod.limit_method = "ANGLE"
    return obj


def box(name, x0, y0, z0, x1, y1, z1, mat, bevel=0.0):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(x1 - x0, y1 - y0, z1 - z0), verts=bm.verts)
    bmesh.ops.translate(bm, vec=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), verts=bm.verts)
    return mesh_object(name, bm, mat, bevel=bevel)


def cyl(name, x, y, z0, z1, r, mat, r_top=None, seg=None, smooth=True, bevel=0.0):
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        segments=seg or L["segments"],
        radius1=r,
        radius2=r if r_top is None else r_top,
        depth=z1 - z0,
    )
    bmesh.ops.translate(bm, vec=(x, y, (z0 + z1) / 2), verts=bm.verts)
    return mesh_object(name, bm, mat, smooth=smooth, bevel=bevel)


def rod(name, a, b, r, mat, seg=None):
    a, b = Vector(a), Vector(b)
    d = b - a
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        segments=seg or max(L["segments"] // 2, 5),
        radius1=r,
        radius2=r,
        depth=d.length,
    )
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix()
    bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=rot, verts=bm.verts)
    bmesh.ops.translate(bm, vec=(a + b) / 2, verts=bm.verts)
    return mesh_object(name, bm, mat, smooth=True)


def blob(name, x, y, z, r, mat, subdiv=2, squash=1.0, smooth=False):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=r)
    bmesh.ops.scale(bm, vec=(1, 1, squash), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(x, y, z), verts=bm.verts)
    return mesh_object(name, bm, mat, smooth=smooth)


def ellipsoid(name, centre, radii, mat, seg=None, cut=None):
    """A UV sphere; cut=(point, normal) keeps only the side the normal points to."""
    seg = seg or L["segments"]
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=max(seg // 2, 4), radius=1.0)
    bmesh.ops.scale(bm, vec=radii, verts=bm.verts)
    if cut:
        point, normal = cut
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(
            bm, geom=geom, plane_co=point, plane_no=Vector(normal), clear_inner=True
        )
        edges = [e for e in bm.edges if e.is_boundary]
        if edges:
            bmesh.ops.holes_fill(bm, edges=edges)
    bmesh.ops.translate(bm, vec=centre, verts=bm.verts)
    return mesh_object(name, bm, mat, smooth=True)


def text(name, body, x, y, z, size, mat, font=None, facing=0.0, depth=0.02):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.size = size
    cu.extrude = depth
    if font:
        cu.font = font
    cu.materials.append(mat)
    obj = link(bpy.data.objects.new(name, cu))
    obj.location = (x, y, z)
    obj.rotation_euler = (math.radians(90), 0, facing)
    return obj


def cjk_font():
    if "cjk" not in STATE:
        path = next((p for p in FONTS if p.exists()), None)
        STATE["cjk"] = bpy.data.fonts.load(str(path)) if path else None
    return STATE["cjk"]


def tilt(obj, angle, pivot, axis="X"):
    pivot = Vector(pivot)
    obj.data.transform(
        Matrix.Translation(pivot) @ Matrix.Rotation(angle, 4, axis) @ Matrix.Translation(-pivot)
    )


def W(tx: float, ty: float, z: float = 0.0) -> Vector:
    return Vector(cam.world(tx, ty, z))


def clear() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    STATE["materials"] = {}
    STATE.pop("cjk", None)
    STATE["group"] = ""


def use_gpu(scene) -> None:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for kind in ("METAL", "OPTIX", "CUDA", "HIP", "ONEAPI"):
        try:
            prefs.compute_device_type = kind
        except TypeError:
            continue
        prefs.get_devices()
        devices = [d for d in prefs.devices if d.type == kind]
        if devices:
            for d in prefs.devices:
                d.use = d.type == kind
            scene.cycles.device = "GPU"
            return
    scene.cycles.device = "CPU"


def setup_render(width: int, height: int, transparent: bool) -> None:
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    use_gpu(sc)
    sc.cycles.samples = L["samples"]
    sc.cycles.seed = 0
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 4
    sc.cycles.diffuse_bounces = 2
    sc.cycles.glossy_bounces = 2
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.cycles.filter_width = L["filter_width"]
    sc.render.resolution_x = width
    sc.render.resolution_y = height
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = transparent
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA" if transparent else "RGB"
    sc.render.image_settings.color_depth = "8"
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = L["view"]
    sc.view_settings.exposure = L["light"]["exposure"]


def setup_lights() -> None:
    light = L["light"]
    world = bpy.data.worlds.new("sky")
    bpy.context.scene.world = world
    nt = tree_of(world)
    bg = next(n for n in nt.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (*light["sky_colour"], 1)
    bg.inputs["Strength"].default_value = light["sky_strength"]
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = light["sun_energy"]
    sun.color = light["sun_colour"]
    sun.angle = math.radians(light["sun_angle"])
    obj = link(bpy.data.objects.new("sun", sun))
    towards = Vector(to_sun(light["azimuth"], light["elevation"]))
    obj.rotation_euler = Vector((0, 0, -1)).rotation_difference(-towards).to_euler()


def frame(x0: int, y0: int, width: int, height: int) -> None:
    """Point an orthographic camera at a rectangle of screen px (see camera.project)."""
    data = bpy.data.cameras.new("cam")
    data.type = "ORTHO"
    data.sensor_fit = "HORIZONTAL"
    data.ortho_scale = width / cam.PX_PER_M
    data.clip_start = 0.1
    data.clip_end = 600
    obj = link(bpy.data.objects.new("cam", data))
    obj.rotation_euler = cam.ROTATION
    tx, ty = cam.unproject(x0 + width / 2, y0 + height / 2)
    obj.location = W(tx, ty) - FORWARD * 250
    bpy.context.scene.camera = obj


def screen_box(objs, pad: int = 2) -> tuple[int, int, int, int]:
    """The whole-px screen rectangle that holds these objects, as (x0, y0, width, height)."""
    deps = bpy.context.evaluated_depsgraph_get()
    xs, ys = [], []
    for obj in objs:
        ev = obj.evaluated_get(deps)
        for corner in ev.bound_box:
            sx, sy = cam.screen(tuple(ev.matrix_world @ Vector(corner)))
            xs.append(sx)
            ys.append(sy)
    x0, y0 = math.floor(min(xs)) - pad, math.floor(min(ys)) - pad
    return x0, y0, math.ceil(max(xs)) + pad - x0, math.ceil(max(ys)) + pad - y0


def render(path: Path) -> float:
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(path)
    start = time.time()
    bpy.ops.render.render(write_still=True)
    return time.time() - start
