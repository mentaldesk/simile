"""Approach 1 and 1b: the square modelled in code and pre-rendered at a 2:1 isometric angle.

blender -b -P render3d.py -- --level xcom|fallout --part scene|sprites|walk|objects|lightmap|all
    [--time night|morning|afternoon|evening|neutral]
"""

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.modules.setdefault("render3d", sys.modules[__name__])  # Blender runs this file as __main__.
import character as C  # noqa: E402
import scene as S  # noqa: E402

LEVELS = {
    "xcom": {
        "tile_px": 96,
        "samples": 48,
        "seg": 16,
        "detail": True,
        "knees": True,
        "dirs": S.GRID_FACINGS,
        "frames": 8,
        "sun_angle": 1.2,
        "sat": 0.6,
        "val": 0.78,
        "filter": 1.2,
        "sun": {"azimuth": 225, "elevation": 38, "energy": 2.8, "colour": (1.0, 0.64, 0.38)},
        "look": "AgX - Medium High Contrast",
        "sky": {"colour": (0.21, 0.28, 0.46), "strength": 0.6},
        "frame": (2.2, 1.45, 0.24),
    },
    "fallout": {
        "tile_px": 48,
        "samples": 20,
        "seg": 8,
        "detail": False,
        "knees": False,
        "dirs": ("s", "e", "n", "w"),
        "frames": 6,
        "sun_angle": 5.0,
        "sat": 0.8,
        "val": 1.0,
        "filter": 1.0,
        "sun": {"azimuth": 225, "elevation": 50, "energy": 2.7, "colour": (1.0, 0.84, 0.64)},
        "sky": {"colour": (0.5, 0.53, 0.62), "strength": 0.85},
        "look": "AgX - Punchy",
        "frame": (1.9, 1.45, 0.3),
    },
}

# Per time of day, over a level; the sun's position is in S.TIMES and `emit` dials the lights.
LIGHTING = {
    "night": {
        "sun": {"energy": 0.35, "colour": (0.55, 0.68, 1.0)},
        "sun_angle": 1.5,
        "sky": {"colour": (0.04, 0.07, 0.18), "strength": 0.45},
        "emit": {"lamp": 1.0, "neon": 1.0, "window": 1.0, "screen": 1.0},
        "exposure": 0.5,
    },
    "morning": {
        "sun": {"energy": 4.0, "colour": (1.0, 0.88, 0.74)},
        "sun_angle": 1.5,
        "sky": {"colour": (0.52, 0.62, 0.82), "strength": 0.6},
        "emit": {"lamp": 0.0, "neon": 0.12, "window": 0.1, "screen": 0.6},
    },
    "afternoon": {
        "sun": {"energy": 3.4, "colour": (1.0, 0.96, 0.9)},
        "sun_angle": 1.5,
        "sky": {"colour": (0.48, 0.6, 0.88), "strength": 0.6},
        "emit": {"lamp": 0.0, "neon": 0.12, "window": 0.1, "screen": 0.6},
    },
    "evening": {
        "sun": {"energy": 5.5, "colour": (1.0, 0.5, 0.25)},
        "sun_angle": 1.5,
        "sky": {"colour": (0.3, 0.27, 0.48), "strength": 0.5},
        "emit": {"lamp": 0.7, "neon": 0.8, "window": 0.7, "screen": 0.9},
    },
    "neutral": {
        "sun": {"azimuth": 160, "elevation": 55, "energy": 2.8, "colour": (1.0, 1.0, 1.0)},
        "sun_angle": 10.0,
        "sky": {"colour": (0.8, 0.8, 0.8), "strength": 0.9},
    },
}
LIGHTMAP_PX = 8
LIGHTMAP_EXPOSURE = -2.0
GROUND_MARKINGS = ("inlay", "tactile", "line", "zebra")

T = S.TILE_M
PAL = S.a1_palette()
ELEVATION = math.radians(30)
CAM_ROT = (math.radians(60), 0.0, math.radians(45))
CAM_RIGHT = Vector((math.cos(math.radians(45)), math.sin(math.radians(45)), 0))
CAM_UP = Vector((-0.5 * 0.70710678, 0.5 * 0.70710678, math.cos(ELEVATION)))
CAM_FWD = Vector((-0.70710678 * 0.8660254, 0.70710678 * 0.8660254, -0.5))
CJK_FONT = Path("/Library/Fonts/Arial Unicode.ttf")
SQUARE_SOUTH = 27

L: dict = {}
STATS = {"objects": 0}


def lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def colour(name: str, sat: float | None = None, val: float = 1.0, tone: bool = True) -> tuple:
    hexv = PAL.PALETTE.get(name, name)
    r, g, b = (lin(v) for v in PAL.hex_to_rgb(hexv))
    s = L["sat"] if sat is None else sat
    if tone:
        val *= L["val"]
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return tuple(val * (lum + (c - lum) * s) for c in (r, g, b)) + (1.0,)


def emit(kind: str, strength: float) -> float:
    return strength * L.get("emit", {}).get(kind, 1.0)


def tree_of(mat):
    if mat.node_tree is None:
        mat.use_nodes = True
    return mat.node_tree


_MATS: dict = {}


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
    if key in _MATS:
        return _MATS[key]
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
        tex.inputs["Mortar Size"].default_value = 0.012 if L["detail"] else 0.02
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

    if L["detail"]:
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
    else:
        links.new(col_out, bsdf.inputs["Base Color"])

    if emit:
        bsdf.inputs["Emission Color"].default_value = colour(emit, 1.0, tone=False)
        bsdf.inputs["Emission Strength"].default_value = strength
    _MATS[key] = mat
    return mat


def link(obj):
    bpy.context.scene.collection.objects.link(obj)
    STATS["objects"] += 1
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
    if bevel and L["detail"]:
        mod = obj.modifiers.new("bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 2
        mod.limit_method = "ANGLE"
    return obj


def box(name, x0, y0, z0, x1, y1, z1, mat, bevel=0.0):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    sx, sy, sz = x1 - x0, y1 - y0, z1 - z0
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    bmesh.ops.translate(bm, vec=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), verts=bm.verts)
    return mesh_object(name, bm, mat, bevel=bevel)


def cyl(name, x, y, z0, z1, r, mat, r_top=None, seg=None, smooth=None, bevel=0.0):
    seg = seg or L["seg"]
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        segments=seg,
        radius1=r,
        radius2=r if r_top is None else r_top,
        depth=z1 - z0,
    )
    bmesh.ops.translate(bm, vec=(x, y, (z0 + z1) / 2), verts=bm.verts)
    return mesh_object(name, bm, mat, smooth=L["detail"] if smooth is None else smooth, bevel=bevel)


def rod(name, a, b, r, mat, seg=None):
    a, b = Vector(a), Vector(b)
    d = b - a
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        segments=seg or max(L["seg"] // 2, 5),
        radius1=r,
        radius2=r,
        depth=d.length,
    )
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix()
    bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=rot, verts=bm.verts)
    bmesh.ops.translate(bm, vec=(a + b) / 2, verts=bm.verts)
    return mesh_object(name, bm, mat, smooth=L["detail"])


def blob(name, x, y, z, r, mat, subdiv=None, squash=1.0, smooth=False):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv or (2 if L["detail"] else 1), radius=r)
    bmesh.ops.scale(bm, vec=(1, 1, squash), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(x, y, z), verts=bm.verts)
    return mesh_object(name, bm, mat, smooth=smooth)


def ellipsoid(name, centre, radii, mat, seg=None, cut=None):
    """A UV sphere; cut=(point, normal) keeps only the side the normal points to."""
    seg = seg or L["seg"]
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
    return mesh_object(name, bm, mat, smooth=L["detail"])


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
    if "cjk" not in L:
        L["cjk"] = bpy.data.fonts.load(str(CJK_FONT)) if CJK_FONT.exists() else None
    return L["cjk"]


def W(tx: float, ty: float, z: float = 0.0) -> Vector:
    return Vector((tx * T, -ty * T, z))


def mats():
    d = L["detail"]
    return {
        "pavement": material("pavement", "pavement", 0.85, pattern="pavers", sat=0.4, val=0.78),
        "plaza": material("plaza", "sand", 0.7, pattern="pavers", alt="grid", val=0.8, sat=0.4),
        "inlay": material("inlay", "amber", 0.35, 0.9, sat=0.45, val=0.6),
        "grass": material("grass", "green", 0.95, pattern="grass", alt="forest", sat=0.6, val=0.85),
        "curb": material("curb", "concrete", 0.8, pattern="noise" if d else None, sat=0.3, val=0.9),
        "road": material("road", "slate", 0.9, pattern="noise" if d else None, sat=0.25, val=0.55),
        "line": material("line", "pavement", 0.7, sat=0.2, val=1.1),
        "tactile": material("tactile", "amber", 0.7, sat=0.85),
        "water": material("water", "blue", 0.05, sat=0.7, val=0.6, emit="cyan", strength=0.08),
        "bark": material("bark", "umber", 0.9, sat=0.6),
        "leaf": material("leaf", "green", 0.85, sat=0.65, val=0.9),
        "leaf2": material("leaf2", "forest", 0.85, sat=0.65, val=1.0),
        "leaf3": material("leaf3", "lime", 0.85, sat=0.5, val=0.7),
        "palm": material("palm", "lime", 0.8, sat=0.55, val=0.8),
        "steel": material("steel", "steel", 0.35, 0.8, sat=0.4),
        "dark": material("dark", "night", 0.5, 0.3, sat=0.4),
        "wood": material("wood", "brown", 0.7, sat=0.6),
        "concrete": material("concrete", "concrete", 0.85, pattern="noise" if d else None, sat=0.3),
        "soil": material("soil", "espresso", 1.0, sat=0.5),
        "lamp": material("lamp", "cream", 0.4, emit="cream", strength=emit("lamp", 14.0), sat=1.0),
        "glass": material("glass", "night", 0.08, sat=0.5, val=0.9),
        "glass_lit": material(
            "glass_lit", "amber", 0.15, emit="amber", strength=emit("window", 1.6), sat=0.7, val=0.5
        ),
        "glass_cool": material(
            "glass_cool", "ice", 0.15, emit="ice", strength=emit("window", 1.2), sat=0.6, val=0.4
        ),
        "screen_cyan": material(
            "screen_cyan", "blue", 0.3, emit="cyan", strength=emit("screen", 2.2), sat=1.0
        ),
        "screen_pink": material(
            "screen_pink", "magenta", 0.3, emit="neon", strength=emit("screen", 2.2), sat=1.0
        ),
        "neon_pink": material(
            "neon_pink", "neon", 0.3, emit="neon", strength=emit("neon", 6.0), sat=1.0
        ),
        "neon_cyan": material(
            "neon_cyan", "cyan", 0.3, emit="cyan", strength=emit("neon", 5.0), sat=1.0
        ),
        "neon_amber": material(
            "neon_amber", "amber", 0.3, emit="amber", strength=emit("neon", 5.0), sat=1.0
        ),
        "neon_violet": material(
            "neon_violet", "violet", 0.3, emit="violet", strength=emit("neon", 5.0), sat=1.0
        ),
        "white": material("white", "white", 0.6, sat=0.5),
        "red_box": material("red_box", "red", 0.4, sat=0.8),
        "flower_pink": material("flower_pink", "pink", 0.8, sat=0.9),
        "flower_yellow": material("flower_yellow", "yellow", 0.8, sat=0.9),
        "bin_green": material("bin_green", "green", 0.6, sat=0.7),
        "bin_blue": material("bin_blue", "blue", 0.6, sat=0.7),
        "cream_wall": material("cream_wall", "cream", 0.9, pattern="wall" if d else None, sat=0.55),
        "slate_wall": material("slate_wall", "slate", 0.8, pattern="wall" if d else None, sat=0.5),
        "band": material(
            "band", "concrete", 0.85, pattern="noise" if d else None, sat=0.3, val=0.8
        ),
        "tank": material("tank", "pavement", 0.4, 0.6, sat=0.3),
        "cafe_wall": material(
            "cafe_wall", "umber", 0.7, pattern="stripes" if d else None, alt="espresso", sat=0.6
        ),
        "roof": material("roof", "steel", 0.95, pattern="noise" if d else None, sat=0.3),
        "roof_green": material("roof_green", "green", 0.95, pattern="grass", alt="forest", sat=0.6),
        "solar": material("solar", "navy", 0.15, 0.4, sat=0.7, val=0.7),
        "cut": material("cut", "brown", 0.8, pattern="pavers", sat=0.5, val=0.7, scale=0.4),
        "awning_blue": material(
            "awning_blue", "blue", 0.8, pattern="stripes", alt="white", sat=0.7
        ),
        "awning_red": material("awning_red", "red", 0.8, pattern="stripes", alt="white", sat=0.7),
        "awning_cafe": material(
            "awning_cafe", "umber", 0.8, pattern="stripes", alt="cream", sat=0.7
        ),
    }


def build_ground(town: S.TownMap, M):
    groups: dict[str, list] = {}
    raised = {}
    for x, y, name in town.ground():
        name = name or "pavement"
        if name.startswith("grass"):
            kind, z = "grass", 0.18
        elif name.startswith("water"):
            kind, z = "water", -0.35
        elif name.startswith(("road", "crosswalk")):
            kind, z = "road", -0.08
        elif name.startswith("plaza"):
            kind, z = "plaza", 0.0
        else:
            kind, z = "pavement", 0.0
        raised[(x, y)] = (kind, z)
        groups.setdefault(kind, []).append((x, y, z))
        if name == "plaza_inlay":
            c = W(x + 0.5, y + 0.5)
            cyl("inlay", c.x, c.y, 0, 0.012, 0.42, M["inlay"], seg=max(L["seg"] * 2, 12))
            cyl("inlay_core", c.x, c.y, 0, 0.016, 0.3, M["plaza"], seg=max(L["seg"] * 2, 12))
        elif name.startswith("tactile"):
            c = W(x + 0.5, y + 0.5)
            if name.endswith("_v"):
                box(
                    "tactile",
                    c.x - 0.15,
                    c.y - T / 2,
                    0,
                    c.x + 0.15,
                    c.y + T / 2,
                    0.012,
                    M["tactile"],
                )
            else:
                box(
                    "tactile",
                    c.x - T / 2,
                    c.y - 0.15,
                    0,
                    c.x + T / 2,
                    c.y + 0.15,
                    0.012,
                    M["tactile"],
                )
        elif name.startswith("road_line"):
            c = W(x + 0.5, y + 0.5, -0.08)
            box("line", c.x - 0.3, c.y - 0.05, c.z, c.x + 0.3, c.y + 0.05, c.z + 0.01, M["line"])
        elif name.startswith("crosswalk"):
            c = W(x + 0.5, y + 0.5, -0.08)
            for i in range(3):
                yy = c.y - 0.4 + i * 0.36
                box("zebra", c.x - 0.5, yy, c.z, c.x + 0.5, yy + 0.16, c.z + 0.01, M["line"])

    for kind, cells in groups.items():
        bm = bmesh.new()
        for x, y, z in cells:
            a, b = W(x, y + 1, z), W(x + 1, y, z)
            vs = [
                bm.verts.new((a.x, a.y, z)),
                bm.verts.new((b.x, a.y, z)),
                bm.verts.new((b.x, b.y, z)),
                bm.verts.new((a.x, b.y, z)),
            ]
            bm.faces.new(vs)
            for (nx, ny), edge in (
                ((x, y + 1), (0, 1)),
                ((x + 1, y), (1, 2)),
                ((x, y - 1), (2, 3)),
                ((x - 1, y), (3, 0)),
            ):
                nz = raised.get((nx, ny), ("pavement", 0.0))[1]
                if nz < z:
                    p, q = vs[edge[0]], vs[edge[1]]
                    p2 = bm.verts.new((p.co.x, p.co.y, nz))
                    q2 = bm.verts.new((q.co.x, q.co.y, nz))
                    bm.faces.new([q, p, p2, q2])
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
        obj = mesh_object(f"ground_{kind}", bm, M[kind])
        if kind in ("grass", "water"):
            obj.data.materials.append(M["curb"])
            for poly in obj.data.polygons:
                if abs(poly.normal.z) < 0.5:
                    poly.material_index = 1


def build_building(b: dict, M, cutaway: bool = True):
    x0, x1, y0, y1 = b["x0"], b["x1"], b["y0"], b["y1"]
    cut = cutaway and y0 > SQUARE_SOUTH
    storeys = b["storeys"]
    height = 1.0 if cut else storeys * S.STOREY_M
    wall = {"cafe": M["cafe_wall"], "slate": M["slate_wall"], "cream": M["cream_wall"]}
    a, c = W(x0, y1), W(x1, y0)
    if cut:
        th = 0.22
        for bx0, by0, bx1, by1 in (
            (a.x, a.y, c.x, a.y + th),
            (a.x, c.y - th, c.x, c.y),
            (a.x, a.y + th, a.x + th, c.y - th),
            (c.x - th, a.y + th, c.x, c.y - th),
        ):
            box("cut_wall", bx0, by0, 0, bx1, by1, height, wall[b["material"]], bevel=0.02)
            box("cut_cap", bx0, by0, height, bx1, by1, height + 0.02, M["dark"])
        box("cut_floor", a.x + th, a.y + th, 0, c.x - th, c.y - th, 0.05, M["cut"])
        return
    box("building", a.x, a.y, 0, c.x, c.y, height, wall[b["material"]], bevel=0.03)
    detail = L["detail"]
    if detail:
        for k in range(1, storeys):
            z = k * S.STOREY_M
            box(
                "band",
                a.x - 0.06,
                a.y - 0.06,
                z - 0.08,
                c.x + 0.06,
                c.y + 0.06,
                z + 0.08,
                M["band"],
            )
        cyl("drainpipe", c.x - 0.12, a.y - 0.1, 0, height + 0.4, 0.05, M["steel"])
    box("plinth", a.x - 0.03, a.y - 0.03, 0, c.x + 0.03, c.y + 0.03, 0.35, M["concrete"])
    par = 0.25
    top = height + 0.55
    for bx0, by0, bx1, by1 in (
        (a.x, a.y, c.x, a.y + par),
        (a.x, c.y - par, c.x, c.y),
        (a.x, a.y + par, a.x + par, c.y - par),
        (c.x - par, a.y + par, c.x, c.y - par),
    ):
        box("parapet", bx0, by0, height, bx1, by1, top, M["concrete"], bevel=0.02)
    box(
        "roof",
        a.x + par,
        a.y + par,
        height,
        c.x - par,
        c.y - par,
        height + 0.06,
        M["roof_green"] if b["green_roof"] else M["roof"],
    )
    rnd = random.Random(x0 * 100 + y0)
    if detail and not b["green_roof"]:
        p = W(x0 + 1.2, y0 + 1.2, height + 0.06)
        for dx, dy in ((-0.3, -0.3), (0.3, -0.3), (-0.3, 0.3), (0.3, 0.3)):
            cyl("tank_leg", p.x + dx, p.y + dy, p.z, p.z + 0.5, 0.03, M["steel"])
        cyl("tank", p.x, p.y, p.z + 0.5, p.z + 1.6, 0.5, M["tank"])
        rod(
            "antenna",
            (c.x - 0.6, c.y - 0.6, height),
            (c.x - 0.6, c.y - 0.6, height + 2.2),
            0.02,
            M["steel"],
        )
    if b["green_roof"]:
        for _ in range(6 if detail else 3):
            p = W(rnd.uniform(x0 + 0.8, x1 - 0.8), rnd.uniform(y0 + 0.8, y1 - 0.8), height)
            blob("roofbush", p.x, p.y, p.z + 0.2, rnd.uniform(0.25, 0.45), M["leaf2"], squash=0.7)
    for tx, ty, item in b["roof_items"]:
        p = W(tx + 0.5, ty + 0.5, height + 0.06)
        if item == "solar":
            for i in range(2 if detail else 1):
                yy = p.y - 0.25 + i * 0.5
                panel = box(
                    "solar",
                    p.x - 0.5,
                    yy - 0.2,
                    p.z + 0.25,
                    p.x + 0.5,
                    yy + 0.2,
                    p.z + 0.3,
                    M["solar"],
                )
                tilt(panel, math.radians(-20), (0, yy, p.z + 0.27))
                cyl("solar_leg", p.x, yy + 0.1, p.z, p.z + 0.3, 0.03, M["steel"])
        elif item == "ac":
            box(
                "ac",
                p.x - 0.4,
                p.y - 0.3,
                p.z,
                p.x + 0.4,
                p.y + 0.3,
                p.z + 0.6,
                M["white"],
                bevel=0.03,
            )
            cyl("fan", p.x, p.y, p.z + 0.6, p.z + 0.63, 0.22, M["dark"])
        elif item == "skylight":
            box(
                "skylight",
                p.x - 0.4,
                p.y - 0.4,
                p.z,
                p.x + 0.4,
                p.y + 0.4,
                p.z + 0.35,
                M["glass_cool"],
            )

    face_y = a.y
    rows = b["facade"]
    for i, row in enumerate(rows):
        k = storeys - 1 - i
        z = k * S.STOREY_M
        for col, (tile, deco) in enumerate(row):
            tile = tile or ""
            cx = (x0 + col + 0.5) * T
            facade_item(tile, deco, cx, face_y, z, k, M, rnd)
    if rows:
        signs(b, rows, face_y, M)


def facade_item(tile, deco, cx, fy, z, k, M, rnd):
    detail = L["detail"]
    half = T / 2
    if tile.startswith(("window_", "base_window_")):
        lit = rnd.random() < 0.45
        g = M["glass_lit"] if lit else M["glass"]
        box("window", cx - 0.36, fy - 0.04, z + 0.9, cx + 0.36, fy + 0.02, z + 2.3, g)
        if detail and k > 0 and rnd.random() < 0.4:
            box(
                "window_ac",
                cx - 0.3,
                fy - 0.42,
                z + 0.35,
                cx + 0.3,
                fy - 0.02,
                z + 0.8,
                M["white"],
                bevel=0.02,
            )
        if detail:
            for zz in (z + 0.86, z + 2.3):
                box(
                    "frame",
                    cx - 0.42,
                    fy - 0.07,
                    zz,
                    cx + 0.42,
                    fy + 0.01,
                    zz + 0.06,
                    M["concrete"],
                )
            box("mullion", cx - 0.02, fy - 0.06, z + 0.9, cx + 0.02, fy, z + 2.3, M["dark"])
    elif tile.startswith("door_") and not tile.endswith("_top"):
        box("door", cx - 0.42, fy - 0.05, z + 0.0, cx + 0.42, fy + 0.02, z + 2.3, M["wood"])
        if detail:
            box("doorframe", cx - 0.5, fy - 0.08, z + 2.3, cx + 0.5, fy, z + 2.4, M["concrete"])
    elif tile.startswith(("shopfront", "cafe_window")):
        warm = tile.startswith("cafe") or rnd.random() < 0.5
        box(
            "shopglass",
            cx - half + 0.04,
            fy - 0.04,
            z + 0.35,
            cx + half - 0.04,
            fy + 0.02,
            z + 2.5,
            M["glass_lit"] if warm else M["glass_cool"],
        )
        if detail:
            box("mullion", cx - half, fy - 0.07, z + 0.3, cx - half + 0.06, fy, z + 2.55, M["dark"])
            box("transom", cx - half, fy - 0.07, z + 2.5, cx + half, fy, z + 2.58, M["dark"])
            box("sill", cx - half, fy - 0.09, z + 0.3, cx + half, fy, z + 0.36, M["dark"])
    elif tile in ("shop_door", "cafe_door"):
        box(
            "door_glass",
            cx - 0.42,
            fy - 0.04,
            z,
            cx + 0.42,
            fy + 0.02,
            z + 2.4,
            M["glass_lit"] if tile == "cafe_door" else M["glass_cool"],
        )
        box("door_frame", cx - 0.48, fy - 0.08, z + 2.4, cx + 0.48, fy, z + 2.5, M["dark"])
    if deco:
        if deco.startswith(("awning", "cafe_awning")):
            m = (
                M["awning_cafe"]
                if deco.startswith("cafe")
                else (M["awning_red"] if "red" in deco else M["awning_blue"])
            )
            aw = box("awning", cx - half, fy - 0.9, z + 2.6, cx + half, fy, z + 2.66, m)
            tilt(aw, math.radians(22), (0, fy, z + 2.9))
        elif deco == "ac_unit":
            box(
                "ac_unit",
                cx - 0.35,
                fy - 0.35,
                z + 2.0,
                cx + 0.35,
                fy,
                z + 2.5,
                M["white"],
                bevel=0.03,
            )
        elif deco == "screen_l":
            box(
                "screen_back",
                cx - half + 0.1,
                fy - 0.12,
                z + 0.5,
                cx + T + half - 0.1,
                fy,
                z + 2.6,
                M["dark"],
            )
            box(
                "screen",
                cx - half + 0.18,
                fy - 0.14,
                z + 0.6,
                cx + T + half - 0.18,
                fy - 0.1,
                z + 2.5,
                M["screen_pink"],
            )
            text("screen_text", "2026", cx + half, fy - 0.15, z + 1.55, 0.9, M["white"], depth=0.0)
        elif deco == "neon_bolt":
            bolt(cx, fy - 0.08, z + 1.5, M["neon_cyan"])
        elif deco == "neon_cup":
            font = cjk_font()
            if font:
                text("neon_cup", "咖\n啡", cx, fy - 0.1, z + 1.5, 0.75, M["neon_pink"], font=font)
            else:
                cyl("neon_cup", cx, fy - 0.1, z + 1.1, z + 1.8, 0.3, M["neon_pink"])
        elif deco == "neon_24h":
            text("neon_24h", "24H", cx, fy - 0.1, z + 1.5, 0.5, M["neon_amber"])
        elif deco == "neon_bowl":
            text(
                "neon_bowl",
                "面" if cjk_font() else "NOODLE",
                cx,
                fy - 0.1,
                z + 1.5,
                0.7,
                M["neon_amber"],
                font=cjk_font(),
            )
        elif deco.startswith("neon_vertical_top"):
            box("vsign", cx - 0.3, fy - 0.4, z - 2.0, cx + 0.3, fy - 0.3, z + 2.4, M["dark"])
            text(
                "vsign_text",
                "面\n馆" if cjk_font() else "N\nO\nO\nD",
                cx,
                fy - 0.42,
                z + 0.2,
                0.9,
                M["neon_violet"],
                font=cjk_font(),
            )
        elif deco.startswith("neon_"):
            text(deco, "*", cx, fy - 0.1, z + 1.5, 0.6, M["neon_pink"])


def tilt(obj, angle, pivot, axis="X"):
    pivot = Vector(pivot)
    obj.data.transform(
        Matrix.Translation(pivot) @ Matrix.Rotation(angle, 4, axis) @ Matrix.Translation(-pivot)
    )


def bolt(cx, fy, z, mat):
    pts = [
        (-0.1, 0.45),
        (0.22, 0.45),
        (0.05, 0.08),
        (0.25, 0.08),
        (-0.18, -0.5),
        (-0.02, -0.08),
        (-0.22, -0.08),
    ]
    bm = bmesh.new()
    vs = [bm.verts.new((cx + px, fy, z + pz)) for px, pz in pts]
    face = bm.faces.new(vs)
    ext = bmesh.ops.extrude_face_region(bm, geom=[face])
    bmesh.ops.translate(
        bm, vec=(0, -0.05, 0), verts=[v for v in ext["geom"] if isinstance(v, bmesh.types.BMVert)]
    )
    mesh_object("bolt", bm, mat)


def signs(b, rows, fy, M):
    top = rows[0]
    names = [t or "" for t, _ in top]
    if "cafe_sign_l" in names:
        i = names.index("cafe_sign_l")
        cx = (b["x0"] + i + 1.0) * T
        z = (b["storeys"] - 1) * S.STOREY_M
        box(
            "sign_board",
            cx - 1.05,
            fy - 0.12,
            z + 1.0,
            cx + 1.05,
            fy,
            z + 2.0,
            M["dark"],
            bevel=0.02,
        )
        text("sign", "COFFEE", cx, fy - 0.14, z + 1.5, 0.55, M["neon_amber"])


def build_prop(kind, tx, ty, town: S.TownMap, M, rnd):
    g = town.at("ground", int(tx), int(ty)) or ""
    z = 0.18 if g.startswith("grass") else 0.0
    p = W(tx, ty, z)
    detail = L["detail"]
    if kind == "tree":
        cyl("trunk", p.x, p.y, z, z + 2.4, 0.16, M["bark"], r_top=0.09)
        crowns = [
            (0, 0, 3.0, 1.05),
            (0.55, 0.2, 2.6, 0.75),
            (-0.5, -0.25, 2.7, 0.8),
            (0.15, -0.5, 3.3, 0.7),
            (-0.2, 0.45, 3.5, 0.65),
        ]
        for i, (dx, dy, dz, r) in enumerate(crowns[: 5 if detail else 3]):
            m = (M["leaf"], M["leaf2"], M["leaf3"])[i % 3 if detail else 0]
            crown = blob(
                "crown",
                p.x + dx,
                p.y + dy,
                z + dz,
                r * rnd.uniform(0.9, 1.1),
                m,
                squash=0.85,
                subdiv=3 if detail else 1,
                smooth=detail,
            )
            if detail:
                lumpy(crown)
    elif kind == "bush":
        for dx, dy, r in ((0, 0, 0.4), (0.3, 0.15, 0.3), (-0.25, -0.1, 0.28)):
            blob("bush", p.x + dx, p.y + dy, z + r * 0.7, r, M["leaf2"], squash=0.8)
    elif kind == "palm":
        prev = Vector((p.x, p.y, z))
        n = 6 if detail else 3
        for i in range(n):
            t = (i + 1) / n
            nxt = Vector((p.x + 0.35 * t * t, p.y - 0.15 * t * t, z + 4.0 * t))
            rod("palm_trunk", prev, nxt, 0.13 - 0.04 * t, M["bark"])
            prev = nxt
        for j in range(8 if detail else 5):
            ang = j / (8 if detail else 5) * math.tau
            frond(prev, ang, M["palm"])
    elif kind == "lamp":
        cyl("lamp_pole", p.x, p.y, z, z + 4.0, 0.06, M["steel"], r_top=0.045)
        box(
            "lamp_arm",
            p.x - 0.05,
            p.y - 0.05,
            z + 3.9,
            p.x + 0.65,
            p.y + 0.05,
            z + 3.98,
            M["steel"],
        )
        box("lamp_head", p.x + 0.3, p.y - 0.14, z + 3.78, p.x + 0.8, p.y + 0.14, z + 3.9, M["dark"])
        box(
            "lamp_glow",
            p.x + 0.34,
            p.y - 0.11,
            z + 3.7,
            p.x + 0.76,
            p.y + 0.11,
            z + 3.78,
            M["lamp"],
        )
        if detail and emit("lamp", 1.0):
            light = bpy.data.lights.new("lamp", "POINT")
            light.energy = emit("lamp", 900)
            light.color = (1.0, 0.82, 0.6)
            light.shadow_soft_size = 0.2
            obj = link(bpy.data.objects.new("lamp_light", light))
            obj.location = (p.x + 0.55, p.y, z + 3.5)
    elif kind == "bench":
        for i in range(3):
            yy = p.y - 0.22 + i * 0.16
            box(
                "slat",
                p.x - 0.95,
                yy,
                z + 0.42,
                p.x + 0.95,
                yy + 0.12,
                z + 0.47,
                M["wood"],
                bevel=0.01,
            )
        for dx in (-0.7, 0.7):
            box(
                "bench_leg",
                p.x + dx - 0.04,
                p.y - 0.25,
                z,
                p.x + dx + 0.04,
                p.y + 0.25,
                z + 0.42,
                M["dark"],
            )
    elif kind in ("planter_flowers", "planter"):
        box(
            "planter",
            p.x - 0.45,
            p.y - 0.45,
            z,
            p.x + 0.45,
            p.y + 0.45,
            z + 0.5,
            M["concrete"],
            bevel=0.03,
        )
        box("soil", p.x - 0.38, p.y - 0.38, z + 0.5, p.x + 0.38, p.y + 0.38, z + 0.52, M["soil"])
        blob("planter_bush", p.x, p.y, z + 0.7, 0.36, M["leaf2"], squash=0.7)
        if kind == "planter_flowers":
            for i in range(9 if detail else 4):
                a = i * 2.4
                m = M["flower_pink"] if i % 2 else M["flower_yellow"]
                blob(
                    "flower",
                    p.x + 0.26 * math.cos(a),
                    p.y + 0.26 * math.sin(a),
                    z + 0.82,
                    0.07,
                    m,
                    subdiv=1,
                )
    elif kind == "fountain":
        cyl("basin", p.x, p.y, z, z + 0.5, 1.15, M["concrete"], bevel=0.02)
        cyl("water", p.x, p.y, z + 0.5, z + 0.43 + 0.08, 1.0, M["water"])
        cyl("pedestal", p.x, p.y, z + 0.5, z + 1.2, 0.18, M["concrete"])
        cyl("bowl", p.x, p.y, z + 1.2, z + 1.35, 0.5, M["concrete"], r_top=0.55)
        cyl("bowl_water", p.x, p.y, z + 1.35, z + 1.36, 0.47, M["water"])
        cyl("jet", p.x, p.y, z + 1.35, z + 2.1, 0.05, M["screen_cyan"], r_top=0.02)
    elif kind == "terminal":
        box(
            "terminal",
            p.x - 0.3,
            p.y - 0.18,
            z,
            p.x + 0.3,
            p.y + 0.18,
            z + 2.1,
            M["dark"],
            bevel=0.03,
        )
        box(
            "terminal_screen",
            p.x - 0.24,
            p.y - 0.2,
            z + 0.9,
            p.x + 0.24,
            p.y - 0.17,
            z + 1.8,
            M["screen_cyan"],
        )
        box(
            "terminal_band",
            p.x - 0.31,
            p.y - 0.19,
            z + 1.92,
            p.x + 0.31,
            p.y + 0.19,
            z + 2.02,
            M["screen_pink"],
        )
    elif kind == "vending":
        box(
            "vending",
            p.x - 0.45,
            p.y - 0.35,
            z,
            p.x + 0.45,
            p.y + 0.35,
            z + 1.95,
            M["red_box"],
            bevel=0.03,
        )
        box(
            "vending_front",
            p.x - 0.36,
            p.y - 0.37,
            z + 0.7,
            p.x + 0.36,
            p.y - 0.34,
            z + 1.8,
            M["glass_cool"],
        )
    elif kind == "bins":
        for dx, m in ((-0.24, M["bin_green"]), (0.24, M["bin_blue"])):
            box(
                "bin",
                p.x + dx - 0.2,
                p.y - 0.25,
                z,
                p.x + dx + 0.2,
                p.y + 0.25,
                z + 0.95,
                m,
                bevel=0.03,
            )
    elif kind.startswith("bike"):
        frame_m = (
            M["bin_blue"] if "blue" in kind else material("bike_yellow", "amber", 0.5, sat=0.8)
        )
        for dx in (-0.45, 0.45):
            w = cyl("wheel", 0, 0, -0.03, 0.03, 0.32, M["dark"], seg=max(L["seg"], 8))
            w.rotation_euler.x = math.radians(90)
            w.location = (p.x + dx, p.y, z + 0.33)
        rod("bike_frame", (p.x - 0.45, p.y, z + 0.33), (p.x, p.y, z + 0.75), 0.025, frame_m)
        rod("bike_frame", (p.x, p.y, z + 0.75), (p.x + 0.45, p.y, z + 0.33), 0.025, frame_m)
        rod("bike_frame", (p.x - 0.1, p.y, z + 0.33), (p.x + 0.45, p.y, z + 0.85), 0.025, frame_m)
    elif kind == "cafe_table":
        cyl("table_top", p.x, p.y, z + 0.72, z + 0.76, 0.36, M["white"])
        cyl("table_leg", p.x, p.y, z, z + 0.72, 0.04, M["dark"])
        for dx in (-0.55, 0.55):
            box(
                "chair",
                p.x + dx - 0.2,
                p.y - 0.2,
                z + 0.42,
                p.x + dx + 0.2,
                p.y + 0.2,
                z + 0.47,
                M["wood"],
            )
            bx = p.x + dx + (0.18 if dx > 0 else -0.22)
            box("chair_back", bx, p.y - 0.2, z + 0.47, bx + 0.04, p.y + 0.2, z + 0.9, M["wood"])
            for ddx in (-0.16, 0.16):
                box(
                    "chair_leg",
                    p.x + dx + ddx - 0.02,
                    p.y - 0.02,
                    z,
                    p.x + dx + ddx + 0.02,
                    p.y + 0.02,
                    z + 0.42,
                    M["dark"],
                )
    elif kind == "cafe_menu":
        for s in (-1, 1):
            b = box(
                "aboard", p.x - 0.28, p.y - 0.02, z, p.x + 0.28, p.y + 0.02, z + 0.95, M["dark"]
            )
            tilt(b, math.radians(12 * s), (0, p.y, z + 0.95))
    elif kind == "bollard":
        cyl("bollard", p.x, p.y, z, z + 0.9, 0.09, M["steel"])


def lumpy(obj):
    tex = bpy.data.textures.get("leafy") or bpy.data.textures.new("leafy", "CLOUDS")
    tex.noise_scale = 0.35
    mod = obj.modifiers.new("lumps", "DISPLACE")
    mod.texture = tex
    mod.strength = 0.35
    mod.mid_level = 0.5
    mod.texture_coords = "GLOBAL"


def frond(top, ang, mat):
    bm = bmesh.new()
    n = 6
    d = Vector((math.cos(ang), math.sin(ang), 0))
    side = Vector((-d.y, d.x, 0))
    prev = None
    for i in range(n + 1):
        t = i / n
        c = top + d * (1.6 * t) + Vector((0, 0, 0.5 * t - 1.3 * t * t))
        w = 0.28 * math.sin(math.pi * min(t * 1.1, 1.0)) + 0.02
        pair = (bm.verts.new(c + side * w), bm.verts.new(c - side * w))
        if prev:
            bm.faces.new((prev[0], prev[1], pair[1], pair[0]))
        prev = pair
    mesh_object("frond", bm, mat)


def setup_render(width: int, height: int, transparent: bool):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "METAL"
    prefs.get_devices()
    for dev in prefs.devices:
        dev.use = dev.type == "METAL"
    sc.cycles.device = "GPU"
    sc.cycles.samples = L["samples"]
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 4
    sc.cycles.diffuse_bounces = 2
    sc.cycles.glossy_bounces = 2
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.cycles.filter_width = L["filter"]
    sc.render.resolution_x = width
    sc.render.resolution_y = height
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = transparent
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA" if transparent else "RGB"
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = L["look"]
    sc.view_settings.exposure = L.get("exposure", 0.0)


def setup_lights():
    world = bpy.data.worlds.new("sky")
    bpy.context.scene.world = world
    nt = tree_of(world)
    bg = next(n for n in nt.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (*L["sky"]["colour"], 1)
    bg.inputs["Strength"].default_value = L["sky"]["strength"]
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = L["sun"]["energy"]
    sun.color = L["sun"]["colour"]
    sun.angle = math.radians(L["sun_angle"])
    obj = link(bpy.data.objects.new("sun", sun))
    obj.rotation_euler = Vector((0, 0, -1)).rotation_difference(sunlight()).to_euler()


def sunlight() -> Vector:
    """The direction the sun's light travels."""
    return -Vector(S.to_sun(L["sun"]["azimuth"], L["sun"]["elevation"]))


def camera(width: int, height: int, ppm: float, centre: Vector):
    cam = bpy.data.cameras.new("cam")
    cam.type = "ORTHO"
    cam.sensor_fit = "HORIZONTAL"
    cam.ortho_scale = width / ppm
    cam.clip_start = 0.1
    cam.clip_end = 400
    obj = link(bpy.data.objects.new("cam", cam))
    obj.rotation_euler = CAM_ROT
    obj.location = centre - CAM_FWD * 120
    bpy.context.scene.camera = obj
    return obj


def ppm() -> float:
    return L["tile_px"] / (T * math.sqrt(2))


def project(p: Vector, cam_centre: Vector, width: int, height: int) -> tuple[float, float]:
    d = p - cam_centre
    return width / 2 + d.dot(CAM_RIGHT) * ppm(), height / 2 - d.dot(CAM_UP) * ppm()


def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _MATS.clear()
    L.pop("cjk", None)
    STATS["objects"] = 0


def poly_count() -> int:
    deps = bpy.context.evaluated_depsgraph_get()
    total = 0
    for obj in bpy.context.scene.objects:
        if obj.type in ("MESH", "FONT"):
            ev = obj.evaluated_get(deps)
            try:
                me = ev.to_mesh()
            except RuntimeError:
                continue
            total += sum(len(p.vertices) - 2 for p in me.polygons)
            ev.to_mesh_clear()
    return total


def render(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(path)
    start = time.time()
    bpy.ops.render.render(write_still=True)
    return time.time() - start


def build_town() -> S.TownMap:
    town = S.TownMap()
    M = mats()
    build_ground(town, M)
    for b in town.buildings():
        build_building(b, M)
    rnd = random.Random(1)
    for kind, tx, ty in town.props():
        build_prop(kind, tx, ty, town, M, rnd)
    return town


def render_scene(out: Path, timings: dict):
    clear()
    t0 = time.time()
    build_town()
    setup_lights()
    unit = L["tile_px"] / 2
    (sx0, sx1), (sy0, sy1) = S.VIEW["sx"], S.VIEW["sy"]
    width, height = round((sx1 - sx0) * unit), round((sy1 - sy0) * unit)
    sxc, syc = (sx0 + sx1) / 2, (sy0 + sy1) / 2
    centre = W(syc + sxc / 2, syc - sxc / 2)
    camera(width, height, ppm(), centre)
    setup_render(width, height, transparent=False)
    timings["scene_build_s"] = round(time.time() - t0, 1)
    timings["scene_triangles"] = poly_count()
    timings["scene_objects"] = STATS["objects"]
    timings["scene_render_s"] = round(render(out / "scene.png"), 1)
    origin = project(W(0, 0), centre, width, height)
    ex = project(W(1, 0), centre, width, height)
    ey = project(W(0, 1), centre, width, height)
    meta = {
        "size": [width, height],
        "origin": origin,
        "ex": [ex[0] - origin[0], ex[1] - origin[1]],
        "ey": [ey[0] - origin[0], ey[1] - origin[1]],
    }
    (out / "scene.json").write_text(json.dumps(meta, indent=2))


def render_lightmap(out: Path, timings: dict):
    """The direct light reaching the ground, from above: sun + sky, sun, and lamps and signs."""
    clear()
    town = build_town()
    white = bpy.data.materials.new("white")
    for obj in bpy.context.scene.objects:
        obj.visible_camera = obj.name.startswith("ground_")
        obj.visible_shadow = not obj.name.startswith(GROUND_MARKINGS)
        for slot in obj.material_slots if obj.visible_camera else ():
            slot.material = white
    glowing = [
        (n.inputs["Emission Strength"], n.inputs["Emission Strength"].default_value)
        for m in bpy.data.materials
        if m.node_tree
        for n in m.node_tree.nodes
        if n.type == "BSDF_PRINCIPLED" and n.inputs["Emission Strength"].default_value > 0
    ]
    setup_lights()
    w, h = town.width * LIGHTMAP_PX, town.height * LIGHTMAP_PX
    cam = bpy.data.cameras.new("top")
    cam.type = "ORTHO"
    cam.sensor_fit = "HORIZONTAL"
    cam.ortho_scale = town.width * T
    top = link(bpy.data.objects.new("top", cam))
    top.location = W(town.width / 2, town.height / 2, 100)
    bpy.context.scene.camera = top
    setup_render(w, h, transparent=False)
    sc = bpy.context.scene
    sc.cycles.samples = 32
    sc.cycles.max_bounces = 0
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = LIGHTMAP_EXPOSURE
    sun = sc.objects["sun"]
    sky = next(n for n in sc.world.node_tree.nodes if n.type == "BACKGROUND").inputs["Strength"]
    lamps = [o for o in sc.objects if o.type == "LIGHT" and o.name.startswith("lamp")]
    start = time.time()
    for name, with_sun, with_sky, with_lights in (
        ("sunsky", True, True, False),
        ("sun", True, False, False),
        ("lights", False, False, True),
    ):
        sun.hide_render = not with_sun
        sky.default_value = L["sky"]["strength"] if with_sky else 0.0
        for lamp in lamps:
            lamp.hide_render = not with_lights
        for socket, strength in glowing:
            socket.default_value = strength if with_lights else 0.0
        render(out / f"light_{name}.png")
    timings["lightmap_render_s"] = round(time.time() - start, 1)
    (out / "lightmap.json").write_text(json.dumps({"px_per_tile": LIGHTMAP_PX}))


def sprite_frame():
    if "time" in L:
        return fitted_frame()
    fw, fh, fx = L["frame"]
    w = round(L["tile_px"] * fw)
    h = round(L["tile_px"] * fh)
    anchor = (round(w * fx), round(h * 0.86))
    return w, h, anchor


def fitted_frame():
    pts = [Vector((x, y, z)) for x in (-0.45, 0.45) for y in (-0.45, 0.45) for z in (0.0, 2.0)]
    if L["time"] != "neutral":
        light = sunlight()
        pts += [p + light * (p.z / -light.z) for p in pts if p.z]
    k, pad = ppm(), 4
    xs = [p.dot(CAM_RIGHT) * k for p in pts]
    ys = [-p.dot(CAM_UP) * k for p in pts]
    w = math.ceil(max(xs) - min(xs)) + 2 * pad
    h = math.ceil(max(ys) - min(ys)) + 2 * pad
    return w, h, (round(pad - min(xs)), round(pad - min(ys)))


def sprite_camera(w, h, anchor):
    k = ppm()
    centre = -CAM_RIGHT * ((anchor[0] - w / 2) / k) + CAM_UP * ((anchor[1] - h / 2) / k)
    camera(w, h, k, centre)


def character_scene(npc_id):
    clear()
    rig = C.build_character(npc_id)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30)
    catcher = mesh_object("catcher", bm, material("catcher", "white"))
    catcher.is_shadow_catcher = True
    catcher.hide_render = L.get("time") == "neutral"
    setup_lights()
    w, h, anchor = sprite_frame()
    sprite_camera(w, h, anchor)
    setup_render(w, h, transparent=True)
    return rig, (w, h, anchor)


def walk_phase(frame: int) -> float:
    # A rig without knees poses by sin(phase) alone; this offset keeps every frame distinct.
    return math.tau * (frame + 0.25) / L["frames"]


def render_sprites(out: Path, timings: dict):
    frames = {}
    for npc_id, _, _, facing, frame in S.RESIDENTS:
        rig, (w, h, anchor) = character_scene(npc_id)
        timings[f"{npc_id}_triangles"] = poly_count()
        rig.rotation_euler.z = math.radians(S.FACING_DEG[facing])
        C.pose(rig, None if frame is None else walk_phase(frame))
        timings[f"{npc_id}_render_s"] = round(render(out / f"sprite_{npc_id}.png"), 1)
        frames[npc_id] = {"anchor": anchor, "size": [w, h]}
    (out / "sprites.json").write_text(json.dumps(frames, indent=2))


def render_walk(out: Path, timings: dict):
    rig, (w, h, anchor) = character_scene(S.WALKER)
    start = time.time()
    count = 0
    for facing in L["dirs"]:
        rig.rotation_euler.z = math.radians(S.FACING_DEG[facing])
        for f in range(L["frames"]):
            C.pose(rig, walk_phase(f))
            render(out / "walk" / f"{facing}_{f}.png")
            count += 1
    timings["walk_frames"] = count
    timings["walk_render_s"] = round(time.time() - start, 1)
    timings["walk_frame_size"] = [w, h]
    (out / "walk.json").write_text(
        json.dumps(
            {"dirs": list(L["dirs"]), "frames": L["frames"], "anchor": anchor, "size": [w, h]},
            indent=2,
        )
    )


def render_objects(out: Path, timings: dict):
    """One sprite per building and per prop kind: what C1 draws over a ground layer."""
    town = S.TownMap()
    jobs = [
        (f"building_{i}", lambda b=b: build_building(b, mats(), cutaway=False))
        for i, b in enumerate(town.buildings())
    ]
    first = {}
    for kind, tx, ty in town.props():
        first.setdefault(kind, (tx, ty))
    jobs += [
        (
            f"prop_{kind}",
            lambda kind=kind, p=p: build_prop(kind, *p, town, mats(), random.Random(1)),
        )
        for kind, p in first.items()
    ]
    k = ppm()
    start = time.time()
    total = pixels = 0
    for name, build in jobs:
        clear()
        build()
        xs, ys = [], []
        for obj in bpy.context.scene.objects:
            if obj.type in ("MESH", "FONT"):
                for corner in obj.bound_box:
                    p = obj.matrix_world @ Vector(corner)
                    xs.append(p.dot(CAM_RIGHT) * k)
                    ys.append(-p.dot(CAM_UP) * k)
        w = math.ceil(max(xs) - min(xs)) + 4
        h = math.ceil(max(ys) - min(ys)) + 4
        mid_x, mid_y = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        camera(w, h, k, CAM_RIGHT * (mid_x / k) - CAM_UP * (mid_y / k))
        setup_lights()
        setup_render(w, h, transparent=True)
        path = out / "objects" / f"{name}.png"
        render(path)
        total += path.stat().st_size
        pixels += w * h
    timings["object_sprites"] = len(jobs)
    timings["object_render_s"] = round(time.time() - start, 1)
    timings["object_mpx"] = round(pixels / 1e6, 2)
    timings["object_png_mb"] = round(total / 1e6, 2)


def main():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--level", choices=list(LEVELS), default="xcom")
    parser.add_argument(
        "--part",
        choices=["scene", "sprites", "walk", "objects", "lightmap", "all"],
        default="all",
    )
    parser.add_argument("--time", choices=list(LIGHTING))
    parser.add_argument("--samples", type=int)
    args = parser.parse_args(argv)
    L.update(LEVELS[args.level])
    out = S.OUT / args.level
    if args.time:
        L.update(LIGHTING[args.time], time=args.time)
        sun = S.TIMES.get(args.time, {})
        L["sun"] = {**L["sun"], **{k: sun[k] for k in ("azimuth", "elevation") if k in sun}}
        out = out / args.time
    if args.samples:
        L["samples"] = args.samples
    out.mkdir(parents=True, exist_ok=True)
    timings_path = out / "timings.json"
    timings = json.loads(timings_path.read_text()) if timings_path.exists() else {}
    timings["samples"] = L["samples"]
    if args.part in ("scene", "all"):
        render_scene(out, timings)
    if args.part in ("sprites", "all"):
        render_sprites(out, timings)
    if args.part in ("walk", "all"):
        render_walk(out, timings)
    if args.part in ("objects", "all"):
        render_objects(out, timings)
    if args.part == "lightmap" or (args.part == "all" and args.time in S.TIMES):
        render_lightmap(out, timings)
    timings_path.write_text(json.dumps(timings, indent=2))
    print("TIMINGS", json.dumps(timings))


main()
