"""Inside Blender: an interior's floor, walls, fittings, frames and ceiling lights."""

import math
import random

import bmesh
import bpy

from simile.art.iso import camera as cam
from simile.art.iso.in_blender import scenery as S
from simile.art.iso.in_blender.common import (
    STATE,
    W,
    blob,
    box,
    cjk_font,
    colour,
    cyl,
    ellipsoid,
    emit,
    link,
    material,
    mesh_object,
    rod,
    text,
    tilt,
    tree_of,
)

T = cam.TILE_M
CAP_M = 0.04
WAINSCOT_M = 1.0


def surface(name: str, base: str, alt: str, kind: str, size: tuple, rough: float = 0.8, **kw):
    """A tiled surface: planks, bricks, checks or speckle, laid on (x + y, z) or (x, y)."""
    key = ("surface", name)
    if key in STATE["materials"]:
        return STATE["materials"][key]
    mat = bpy.data.materials.new(name)
    nt = tree_of(mat)
    nodes, links = nt.nodes, nt.links
    bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Roughness"].default_value = rough
    sat, val = kw.get("sat", 0.6), kw.get("val", 1.0)
    coord = nodes.new("ShaderNodeTexCoord")
    xyz = nodes.new("ShaderNodeSeparateXYZ")
    links.new(coord.outputs["Object"], xyz.inputs[0])
    vec = nodes.new("ShaderNodeCombineXYZ")
    if kw.get("upright"):
        add = nodes.new("ShaderNodeMath")
        add.operation = "ADD"
        links.new(xyz.outputs["X"], add.inputs[0])
        links.new(xyz.outputs["Y"], add.inputs[1])
        links.new(add.outputs[0], vec.inputs["X"])
        links.new(xyz.outputs["Z"], vec.inputs["Y"])
    else:
        links.new(xyz.outputs["X"], vec.inputs["X"])
        links.new(xyz.outputs["Y"], vec.inputs["Y"])
    c1, c2 = colour(base, sat, val), colour(alt, sat, val)
    if kind == "check":
        tex = nodes.new("ShaderNodeTexChecker")
        tex.inputs["Color1"].default_value = c1
        tex.inputs["Color2"].default_value = c2
        tex.inputs["Scale"].default_value = 0.5 / size[0]
        out, fac = tex.outputs["Color"], None
    elif kind == "speckle":
        tex = nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = size[0]
        tex.inputs["Detail"].default_value = 8.0
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.42
        ramp.color_ramp.elements[0].color = c2
        ramp.color_ramp.elements[1].position = 0.58
        ramp.color_ramp.elements[1].color = c1
        links.new(vec.outputs[0], tex.inputs["Vector"])
        links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        out, fac = ramp.outputs["Color"], None
    else:
        tex = nodes.new("ShaderNodeTexBrick")
        tex.offset = 0.5
        tex.offset_frequency = 2
        tex.inputs["Color1"].default_value = c1
        tex.inputs["Color2"].default_value = colour(base, sat, val * 0.88)
        tex.inputs["Mortar"].default_value = colour(alt, sat, val)
        tex.inputs["Scale"].default_value = 1.0
        tex.inputs["Mortar Size"].default_value = kw.get("mortar", 0.008)
        tex.inputs["Brick Width"].default_value = size[0]
        tex.inputs["Row Height"].default_value = size[1]
        out, fac = tex.outputs["Color"], tex.outputs["Fac"]
    if kind != "speckle":
        links.new(vec.outputs[0], tex.inputs["Vector"])
    ao = nodes.new("ShaderNodeAmbientOcclusion")
    ao.inputs["Distance"].default_value = 0.6
    ao.samples = 8
    shade = nodes.new("ShaderNodeMath")
    shade.operation = "MULTIPLY_ADD"
    shade.inputs[1].default_value = 0.4
    shade.inputs[2].default_value = 0.6
    links.new(ao.outputs["AO"], shade.inputs[0])
    mul = nodes.new("ShaderNodeVectorMath")
    mul.operation = "SCALE"
    links.new(out, mul.inputs[0])
    links.new(shade.outputs[0], mul.inputs["Scale"])
    links.new(mul.outputs[0], bsdf.inputs["Base Color"])
    if fac is not None:
        bump = nodes.new("ShaderNodeBump")
        bump.invert = True
        bump.inputs["Strength"].default_value = 0.4
        bump.inputs["Distance"].default_value = 0.01
        links.new(fac, bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    STATE["materials"][key] = mat
    return mat


def glass(name: str):
    """Mostly see-through, with a gloss: transparency keeps camera rays, so what's inside shows."""
    key = ("glass", name)
    if key not in STATE["materials"]:
        mat = bpy.data.materials.new(name)
        nt = tree_of(mat)
        out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
        bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        bsdf.inputs["Base Color"].default_value = colour("ice", 0.4, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.08
        clear = nt.nodes.new("ShaderNodeBsdfTransparent")
        mix = nt.nodes.new("ShaderNodeMixShader")
        mix.inputs["Fac"].default_value = 0.3
        nt.links.new(clear.outputs[0], mix.inputs[1])
        nt.links.new(bsdf.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs["Surface"])
        STATE["materials"][key] = mat
    return STATE["materials"][key]


def mats() -> dict:
    M = S.mats()
    M.update(
        {
            "floor_wood": surface(
                "floor_wood", "tan", "umber", "brick", (1.1, 0.16), 0.55, sat=0.55, val=0.95
            ),
            "floor_tiles": surface("floor_tiles", "cream", "peach", "check", (T / 2,), 0.4),
            "floor_concrete": surface(
                "floor_concrete", "concrete", "steel", "speckle", (40.0,), 0.9, sat=0.3, val=1.05
            ),
            "floor_gallery": surface(
                "floor_gallery", "cream", "sand", "brick", (0.6, 0.3), 0.5, sat=0.45, val=1.05
            ),
            "wall_panel": material("wall_panel", "cream", 0.9, pattern="wall", sat=0.5, val=1.05),
            "wainscot": material(
                "wainscot", "umber", 0.6, pattern="stripes", alt="espresso", sat=0.6
            ),
            "wall_brick": surface(
                "wall_brick", "maroon", "tan", "brick", (0.24, 0.075), 0.9, sat=0.6, upright=True
            ),
            "wall_block": surface(
                "wall_block",
                "pavement",
                "steel",
                "brick",
                (0.4, 0.2),
                0.9,
                sat=0.3,
                upright=True,
                mortar=0.012,
            ),
            "wall_plaster": material("wall_plaster", "white", 0.9, sat=0.3, val=1.0),
            "cap": material("cap", "slate", 0.8, sat=0.5),
            "skirting": material("skirting", "concrete", 0.6, sat=0.3),
            "mat": material("mat", "maroon", 0.95, pattern="stripes", alt="red", sat=0.7),
            "stone": material("stone", "cream", 0.35, sat=0.4, val=1.05),
            "cabinet": material("cabinet", "umber", 0.6, sat=0.6),
            "counter_wood": material("counter_wood", "brown", 0.55, sat=0.6),
            "board": material("board", "espresso", 0.8, sat=0.5, val=0.8),
            "chalk": material("chalk", "white", 0.9, sat=0.2, val=0.9),
            "frame": material("frame", "steel", 0.35, 0.5, sat=0.4, val=0.9),
            "red_seat": material("red_seat", "red", 0.5, sat=0.8),
            "lantern": material(
                "lantern", "red", 0.6, emit="red", strength=emit("neon", 0.5), sat=1.0
            ),
            "chrome": material("chrome", "pavement", 0.3, 0.6, sat=0.3, val=1.1),
            "gold": material("gold", "amber", 0.35, 0.8, sat=0.7),
            "flame": material(
                "flame", "orange", 0.5, emit="orange", strength=emit("neon", 8.0), sat=1.0
            ),
            "pegboard": material("pegboard", "sand", 0.9, sat=0.55),
            "cork": material("cork", "tan", 0.9, sat=0.5),
            "loom_threads": material(
                "loom_threads", "magenta", 0.8, pattern="stripes", alt="amber", sat=0.75
            ),
            "print": material("print", "orange", 0.5, sat=0.85),
            "glass_case": glass("glass_case"),
            "pastry": material("pastry", "amber", 0.7, sat=0.7),
            "pastry_pink": material("pastry_pink", "pink", 0.7, sat=0.7),
            "cup": material("cup", "white", 0.4, sat=0.3),
            "bowl": material("bowl", "white", 0.4, sat=0.3),
            "plinth": material("plinth", "white", 0.6, sat=0.2),
            "sculpture": material("sculpture", "orange", 0.3, 0.4, sat=0.85),
        }
    )
    return M


def mbox(name, x0, y0, x1, y1, z0, z1, mat, bevel=0.0):
    """A box from map tiles (x0, y0)–(x1, y1) and metres z0–z1."""
    a, c = W(x0, y1), W(x1, y0)
    return box(name, a.x, a.y, z0, c.x, c.y, z1, mat, bevel=bevel)


def build_floor(room: dict, ground: list[list[str]], visible: bool = True) -> None:
    M = mats()
    groups: dict[str, list[tuple[int, int]]] = {}
    for y, row in enumerate(ground):
        for x, name in enumerate(row):
            if name != "void":
                groups.setdefault(name, []).append((x, y))
    made = []
    for name, cells in groups.items():
        bm = bmesh.new()
        for x, y in cells:
            a, b = W(x, y + 1), W(x + 1, y)
            corners = ((a.x, a.y), (b.x, a.y), (b.x, b.y), (a.x, b.y))
            bm.faces.new([bm.verts.new((px, py, 0.0)) for px, py in corners])
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
        made.append(mesh_object(f"floor_{name}", bm, M.get(name, M["floor_wood"])))
    for x, y in room["mats"]:
        made.append(mbox("mat", x + 0.12, y + 0.18, x + 0.88, y + 0.82, 0, 0.015, M["mat"]))
    for obj in made:
        obj.visible_camera = visible


def room_lights(room: dict) -> None:
    for x, y, z in room["lights"]:
        light = bpy.data.lights.new("lamp_ceiling", "POINT")
        light.energy = emit("lamp", room["light_energy"])
        light.color = room["light_colour"]
        light.shadow_soft_size = 0.35
        link(bpy.data.objects.new("lamp_ceiling", light)).location = W(x, y, z)


def build_piece(spec: dict) -> None:
    kind = spec["kind"]
    if kind == "wall":
        wall(spec)
    elif kind == "frame":
        frame(spec)
    else:
        FITTINGS[kind](spec, mats(), random.Random(spec["id"]))


def wall(spec: dict) -> None:
    M = mats()
    x0, y0, x1, y1 = spec["footprint"]
    h = spec["height_m"]
    finish = spec["finish"]
    body = M[f"wall_{finish}"]
    mbox("wall", x0, y0, x1, y1, 0, h - CAP_M, body)
    mbox("wall_cap", x0 - 0.01, y0 - 0.01, x1 + 0.01, y1 + 0.01, h - CAP_M, h, M["cap"])
    face = spec["face"]
    if face not in ("south", "east", "partition"):
        return
    d = 0.02 / T
    lo, hi = (y0, y1) if face == "east" else (x0, x1)

    def strip(a, b, z0, z1, m):
        if face == "east":
            mbox("trim", x1, a, x1 + d, b, z0, z1, m)
        else:
            mbox("trim", a, y1, b, y1 + d, z0, z1, m)

    if finish == "panel":
        strip(lo, hi, 0, WAINSCOT_M, M["wainscot"])
        strip(lo, hi, WAINSCOT_M, WAINSCOT_M + 0.06, M["counter_wood"])
    else:
        strip(lo, hi, 0, 0.12, M["skirting"])
    for kind, a, b in spec.get("decor", []):
        WALL_DECOR[kind]((a + b) / 2, y1, M)


def frame(spec: dict) -> None:
    M = mats()
    x0, x1, y = spec["x0"], spec["x1"], spec["face_y"]
    z0, z1, m = spec["z0"], spec["z1"], spec["moulding"]
    d = spec["depth"]
    mi = m / T
    mbox("frame_top", x0, y, x1, y + d, z1 - m, z1, M["frame"], bevel=0.01)
    mbox("frame_bottom", x0, y, x1, y + d, z0, z0 + m, M["frame"], bevel=0.01)
    mbox("frame_left", x0, y, x0 + mi, y + d, z0 + m, z1 - m, M["frame"], bevel=0.01)
    mbox("frame_right", x1 - mi, y, x1, y + d, z0 + m, z1 - m, M["frame"], bevel=0.01)


def shelf(cx, fy, M):
    half = 0.42 / T
    d = 0.24 / T
    mbox("shelf", cx - half, fy, cx + half, fy + d, 1.52, 1.56, M["counter_wood"])
    for s in (-1, 1):
        mbox(
            "bracket",
            cx + s * 0.6 * half,
            fy,
            cx + s * 0.6 * half + 0.03,
            fy + d * 0.8,
            1.4,
            1.52,
            M["dark"],
        )
    rnd = random.Random(int(cx * 10))
    for i in range(5):
        px = cx - half * 0.8 + i * half * 0.4
        c = W(px, fy + d / 2)
        m = M["cup"] if rnd.random() < 0.6 else M["flower_yellow"] if i % 2 else M["bin_blue"]
        cyl("jar", c.x, c.y, 1.56, 1.56 + rnd.uniform(0.1, 0.2), 0.05, m)


def menu_board(cx, fy, M):
    half = 0.85 / T
    d = 0.04 / T
    mbox("menu_board", cx - half, fy, cx + half, fy + d, 1.35, 2.3, M["board"], bevel=0.01)
    mbox(
        "menu_trim",
        cx - half - 0.02,
        fy,
        cx + half + 0.02,
        fy + d * 0.8,
        2.3,
        2.34,
        M["counter_wood"],
    )
    c = W(cx, fy + d + 0.005)
    text("menu_text", "MENU", c.x, c.y, 2.12, 0.22, M["chalk"], depth=0.0)
    for i in range(4):
        z = 1.95 - i * 0.14
        for s in (-1, 1):
            a = cx + s * half * 0.5
            mbox(
                "menu_line",
                a - half * 0.35,
                fy + d,
                a + half * 0.35,
                fy + d * 1.3,
                z,
                z + 0.025,
                M["chalk"] if i % 2 else M["neon_amber"],
            )


def neon_cup(cx, fy, M):
    c = W(cx, fy + 0.06 / T)
    font = cjk_font()
    if font:
        text("neon_cup", "咖\n啡", c.x, c.y, 1.85, 0.75, M["neon_pink"], font=font)
    else:
        cyl("neon_cup", c.x, c.y, 1.7, 2.1, 0.2, M["neon_pink"])


def lantern(cx, fy, M):
    c = W(cx, fy + 0.35 / T)
    base = W(cx, fy)
    box("lantern_arm", c.x - 0.015, c.y, 2.6, c.x + 0.015, base.y, 2.63, M["dark"])
    rod("lantern_cord", (c.x, c.y, 2.6), (c.x, c.y, 2.42), 0.006, M["dark"])
    ellipsoid("lantern", (c.x, c.y, 2.22), (0.2, 0.2, 0.24), M["lantern"])
    cyl("lantern_cap", c.x, c.y, 2.42, 2.46, 0.09, M["gold"])
    cyl("lantern_foot", c.x, c.y, 1.96, 2.0, 0.09, M["gold"])
    rod("lantern_tassel", (c.x, c.y, 1.96), (c.x, c.y, 1.78), 0.012, M["red_box"])


def neon_bowl(cx, fy, M):
    half = 0.5 / T
    d = 0.04 / T
    mbox("bowl_board", cx - half, fy, cx + half, fy + d, 1.55, 2.4, M["dark"], bevel=0.01)
    c = W(cx, fy + d + 0.02)
    z, r = 1.95, 0.24
    arc = [
        (c.x + r * math.cos(a), c.y, z + r * math.sin(a))
        for a in (math.pi + math.pi * i / 8 for i in range(9))
    ]
    for a, b in zip(arc, arc[1:], strict=False):
        rod("neon_bowl", a, b, 0.018, M["neon_amber"])
    rod("neon_bowl", (c.x - 0.3, c.y, z), (c.x + 0.3, c.y, z), 0.018, M["neon_amber"])
    for dx in (0.0, 0.08):
        rod(
            "chopstick",
            (c.x + dx, c.y, z + 0.06),
            (c.x + dx + 0.18, c.y, z + 0.32),
            0.014,
            M["neon_pink"],
        )


def pegboard(cx, fy, M):
    half = 0.9 / T
    d = 0.03 / T
    mbox("pegboard", cx - half, fy, cx + half, fy + d, 1.15, 2.2, M["pegboard"], bevel=0.01)
    c = W(cx, fy + d)
    y = c.y - 0.02
    for i, (dx, m) in enumerate(
        ((-0.6, M["red_box"]), (-0.25, M["steel"]), (0.15, M["bike_yellow"]), (0.5, M["steel"]))
    ):
        x = c.x + dx
        if i % 2:
            box("wrench", x - 0.02, y - 0.02, 1.45, x + 0.02, y, 1.95, m)
            box("wrench_head", x - 0.06, y - 0.02, 1.9, x + 0.06, y, 1.98, m)
        else:
            box("handle", x - 0.025, y - 0.03, 1.35, x + 0.025, y, 1.75, M["wood"])
            box("tool_head", x - 0.09, y - 0.04, 1.75, x + 0.09, y, 1.85, m)
    box("tape", c.x + 0.75 - 0.08, y - 0.06, 1.5, c.x + 0.75 + 0.08, y, 1.66, M["bike_yellow"])


WALL_DECOR = {
    "shelf": shelf,
    "menu_board": menu_board,
    "neon_cup": neon_cup,
    "lantern": lantern,
    "neon_bowl": neon_bowl,
    "pegboard": pegboard,
}


def centre(spec: dict):
    x0, y0, x1, y1 = spec["footprint"]
    return (x0 + x1) / 2, (y0 + y1) / 2


def grow(bx, cell, by):
    """A box grown by `by` on each side that doesn't meet a neighbour (negative shrinks it)."""
    x0, y0, x1, y1 = bx
    cx, cy = cell
    return (
        x0 - by * (x0 > cx),
        y0 - by * (y0 > cy),
        x1 + by * (x1 < cx + 1),
        y1 + by * (y1 < cy + 1),
    )


def run(spec, M, rnd, body, top, height, items):
    """Counter boxes cell by cell, a top over each, and what stands on each cell."""
    for bx, (cx, cy, name) in zip(spec["boxes"], spec["cells"], strict=True):
        x0, y0, x1, y1 = bx
        mbox("counter_body", x0, y0, x1, y1, 0.1, height - 0.05, body)
        mbox("counter_kick", *grow(bx, (cx, cy), -0.04), 0.0, 0.1, M["dark"])
        mbox("counter_top", *grow(bx, (cx, cy), 0.025), height - 0.05, height, top)
        if name in items:
            items[name]((x0 + x1) / 2, (y0 + y1) / 2, height, M, rnd)


def espresso(x, y, z, M, rnd):
    c = W(x, y)
    box("espresso", c.x - 0.28, c.y - 0.2, z, c.x + 0.28, c.y + 0.2, z + 0.42, M["chrome"], 0.02)
    box("espresso_top", c.x - 0.3, c.y - 0.22, z + 0.42, c.x + 0.3, c.y + 0.22, z + 0.45, M["dark"])
    for dx in (-0.12, 0.12):
        cyl("group_head", c.x + dx, c.y - 0.24, z + 0.18, z + 0.26, 0.04, M["dark"])
        cyl("espresso_cup", c.x + dx, c.y - 0.24, z, z + 0.07, 0.035, M["cup"])
    box(
        "espresso_light",
        c.x - 0.2,
        c.y - 0.21,
        z + 0.33,
        c.x - 0.12,
        c.y - 0.2,
        z + 0.37,
        M["neon_amber"],
    )


def grinder(x, y, z, M, rnd):
    c = W(x, y)
    box("grinder", c.x - 0.1, c.y - 0.12, z, c.x + 0.1, c.y + 0.12, z + 0.3, M["dark"], 0.02)
    cyl("hopper", c.x, c.y, z + 0.3, z + 0.52, 0.06, M["glass_case"], r_top=0.12)
    cyl("beans", c.x, c.y, z + 0.3, z + 0.4, 0.06, M["soil"], r_top=0.09)


def cups(x, y, z, M, rnd):
    c = W(x, y)
    for i in range(rnd.randint(1, 3)):
        dx = -0.25 + i * 0.22
        cyl("cup_stack", c.x + dx, c.y, z, z + rnd.uniform(0.12, 0.25), 0.045, M["cup"])


def till(x, y, z, M, rnd):
    c = W(x, y)
    box("till", c.x - 0.18, c.y - 0.14, z, c.x + 0.18, c.y + 0.14, z + 0.1, M["dark"], 0.01)
    scr = box(
        "till_screen", c.x - 0.15, c.y - 0.02, z + 0.1, c.x + 0.15, c.y, z + 0.3, M["screen_cyan"]
    )
    tilt(scr, math.radians(-15), (0, c.y, z + 0.1))


def case(x, y, z, M, rnd):
    c = W(x, y)
    box("case_base", c.x - 0.45, c.y - 0.25, z, c.x + 0.45, c.y + 0.25, z + 0.04, M["stone"])
    box(
        "case_glass",
        c.x - 0.44,
        c.y - 0.24,
        z + 0.04,
        c.x + 0.44,
        c.y + 0.24,
        z + 0.34,
        M["glass_case"],
    )
    for i in range(6):
        px = c.x - 0.33 + (i % 3) * 0.33
        py = c.y - 0.1 + (i // 3) * 0.2
        m = M["pastry"] if (i + int(x)) % 2 else M["pastry_pink"]
        blob("pastry", px, py, z + 0.09, 0.06, m, subdiv=1, squash=0.6)


def stove(x, y, z, M, rnd):
    c = W(x, y)
    box("hob", c.x - 0.4, c.y - 0.25, z, c.x + 0.4, c.y + 0.25, z + 0.03, M["dark"])
    cyl("flame", c.x, c.y, z + 0.03, z + 0.05, 0.16, M["flame"], r_top=0.12)
    cyl("pot", c.x, c.y, z + 0.05, z + 0.32, 0.2, M["steel"])
    cyl("broth", c.x, c.y, z + 0.32, z + 0.325, 0.18, M["pastry"])
    box("hood_light", c.x - 0.05, c.y - 0.27, z - 0.25, c.x + 0.05, c.y - 0.25, z - 0.2, M["flame"])


def bowls(x, y, z, M, rnd):
    c = W(x, y)
    for i in range(rnd.randint(1, 3)):
        dx = -0.28 + i * 0.26
        cyl("bowl", c.x + dx, c.y, z, z + 0.08, 0.06, M["bowl"], r_top=0.1)


def back_counter(spec, M, rnd):
    items = {"espresso_machine": espresso, "grinder": grinder, "back_counter": cups}
    run(spec, M, rnd, M["cabinet"], M["stone"], 0.92, items)


def kitchen(spec, M, rnd):
    run(spec, M, rnd, M["chrome"], M["tank"], 0.92, {"stove": stove, "kitchen_counter": bowls})


def counter(spec, M, rnd):
    run(
        spec,
        M,
        rnd,
        M["counter_wood"],
        M["stone"],
        1.05,
        {"counter_till": till, "counter_case": case},
    )


def chair(cx, cy, side, M, seat):
    box("chair", cx - 0.19, cy - 0.19, 0.44, cx + 0.19, cy + 0.19, 0.48, seat)
    bx = cx + side * 0.17
    box("chair_back", bx - 0.02, cy - 0.18, 0.48, bx + 0.02, cy + 0.18, 0.88, seat)
    for dx in (-0.15, 0.15):
        for dy in (-0.15, 0.15):
            box(
                "chair_leg",
                cx + dx - 0.015,
                cy + dy - 0.015,
                0,
                cx + dx + 0.015,
                cy + dy + 0.015,
                0.44,
                M["dark"],
            )


def cafe_table(spec, M, rnd):
    c = W(*centre(spec))
    cyl("table_top", c.x, c.y, 0.72, 0.75, 0.3, M["stone"])
    cyl("table_leg", c.x, c.y, 0.02, 0.72, 0.035, M["dark"])
    cyl("table_foot", c.x, c.y, 0, 0.02, 0.18, M["dark"])
    for s in (-1, 1):
        chair(c.x + s * 0.42, c.y, s, M, M["wood"])
    cyl("table_cup", c.x + 0.08, c.y - 0.05, 0.75, 0.83, 0.04, M["cup"])


def noodle_table(spec, M, rnd):
    c = W(*centre(spec))
    box(
        "table_top", c.x - 0.3, c.y - 0.3, 0.68, c.x + 0.3, c.y + 0.3, 0.72, M["counter_wood"], 0.01
    )
    for dx in (-0.25, 0.25):
        for dy in (-0.25, 0.25):
            box(
                "table_leg",
                c.x + dx - 0.02,
                c.y + dy - 0.02,
                0,
                c.x + dx + 0.02,
                c.y + dy + 0.02,
                0.68,
                M["dark"],
            )
    for s in (-1, 1):
        chair(c.x + s * 0.45, c.y, s, M, M["red_seat"])
    cyl("table_bowl", c.x, c.y, 0.72, 0.8, 0.06, M["bowl"], r_top=0.1)


def stool(spec, M, rnd):
    c = W(*centre(spec))
    cyl("stool_seat", c.x, c.y, 0.68, 0.74, 0.17, M["red_seat"], bevel=0.01)
    cyl("stool_post", c.x, c.y, 0.03, 0.68, 0.03, M["steel"])
    cyl("stool_ring", c.x, c.y, 0.28, 0.3, 0.12, M["steel"])
    cyl("stool_base", c.x, c.y, 0, 0.03, 0.17, M["dark"])


def prop_at(kind, spec, rnd):
    x, y = centre(spec)
    S.build_prop({"kind": kind, "variant": 0, "x": x, "y": y, "z": 0.0})


def planter(spec, M, rnd):
    prop_at("planter", spec, rnd)


def planter_flowers(spec, M, rnd):
    prop_at("planter_flowers", spec, rnd)


def bench(spec, M, rnd):
    prop_at("bench", spec, rnd)


def workbench(spec, M, rnd):
    x0, y0, x1, y1 = spec["footprint"]
    mbox("bench_top", x0, y0, x1, y1, 0.86, 0.92, M["wood"], bevel=0.01)
    mbox("bench_shelf", x0 + 0.08, y0 + 0.08, x1 - 0.08, y1 - 0.08, 0.2, 0.24, M["wood"])
    for x in (x0 + 0.06, x1 - 0.1):
        for y in (y0 + 0.06, y1 - 0.1):
            mbox("bench_leg", x, y, x + 0.04, y + 0.04, 0, 0.86, M["steel"])
    c = W((x0 + x1) / 2, (y0 + y1) / 2)
    box("toolbox", c.x - 0.75, c.y - 0.1, 0.92, c.x - 0.4, c.y + 0.12, 1.08, M["red_box"], 0.01)
    box("vise", c.x + 0.55, c.y - 0.08, 0.92, c.x + 0.75, c.y + 0.08, 1.04, M["steel"])
    box("drill", c.x + 0.05, c.y - 0.04, 0.92, c.x + 0.3, c.y + 0.04, 1.0, M["bike_yellow"], 0.01)
    box("plank", c.x - 0.3, c.y - 0.2, 0.92, c.x + 0.15, c.y + 0.05, 0.94, M["cork"])


def laser_cutter(spec, M, rnd):
    x0, y0, x1, y1 = spec["footprint"]
    mbox("laser_body", x0, y0, x1, y1, 0.0, 0.92, M["dark"], bevel=0.02)
    mbox("laser_lid", x0 + 0.05, y0 + 0.05, x1 - 0.05, y1 - 0.05, 0.92, 1.0, M["glass_cool"])
    mbox("laser_rim", x0, y1 - 0.06, x1, y1, 0.92, 1.12, M["steel"])
    mbox("laser_screen", x1 - 0.45, y1, x1 - 0.1, y1 + 0.02, 0.62, 0.82, M["screen_cyan"])
    mbox("laser_stripe", x0 + 0.1, y1, x0 + 0.9, y1 + 0.02, 0.1, 0.15, M["neon_amber"])


def loom(spec, M, rnd):
    x0, y0, x1, y1 = spec["footprint"]
    p = 0.07
    ym = (y0 + y1) / 2
    for x in (x0, x1 - p):
        mbox("loom_post", x, y0, x + p, y0 + p, 0, 1.6, M["wood"])
        mbox("loom_post", x, y1 - p, x + p, y1, 0, 0.9, M["wood"])
        mbox("loom_rail", x, y0, x + p, y1, 0.78, 0.84, M["wood"])
        mbox("heddle_post", x, ym - p / 2, x + p, ym + p / 2, 0.84, 1.55, M["wood"])
    mbox("loom_beam", x0, y0, x1, y0 + p, 1.52, 1.6, M["wood"])
    mbox("heddle_beam", x0, ym - p / 2, x1, ym + p / 2, 1.48, 1.55, M["wood"])
    mbox("heddles", x0 + p, ym - 0.01, x1 - p, ym + 0.01, 0.9, 1.48, M["loom_threads"])
    mbox("warp", x0 + p, y0 + p, x1 - p, y1 - p, 0.86, 0.87, M["loom_threads"])
    front = W((x0 + x1) / 2, y1 - 0.12)
    roll = cyl(
        "cloth_roll",
        0,
        0,
        -(x1 - x0) * T / 2 + 0.1,
        (x1 - x0) * T / 2 - 0.1,
        0.08,
        M["neon_violet"],
    )
    roll.rotation_euler.y = math.radians(90)
    roll.location = (front.x, front.y, 0.92)


def printer_3d(spec, M, rnd):
    x0, y0, x1, y1 = spec["footprint"]
    mbox("printer_stand", x0, y0, x1, y1, 0.68, 0.72, M["wood"])
    for x in (x0 + 0.03, x1 - 0.07):
        for y in (y0 + 0.03, y1 - 0.07):
            mbox("stand_leg", x, y, x + 0.04, y + 0.04, 0, 0.68, M["steel"])
            mbox("printer_post", x, y, x + 0.04, y + 0.04, 0.72, 1.42, M["dark"])
    mbox("printer_top", x0 + 0.03, y0 + 0.03, x1 - 0.03, y1 - 0.03, 1.38, 1.45, M["dark"])
    mbox("printer_bed", x0 + 0.1, y0 + 0.1, x1 - 0.1, y1 - 0.1, 0.78, 0.8, M["steel"])
    c = W((x0 + x1) / 2, (y0 + y1) / 2)
    cyl("print", c.x, c.y, 0.8, 1.0, 0.1, M["print"], r_top=0.05)
    box("printer_head", c.x - 0.06, c.y - 0.06, 1.2, c.x + 0.06, c.y + 0.06, 1.3, M["bike_yellow"])
    mbox("printer_screen", x1 - 0.3, y1, x1 - 0.1, y1 + 0.02, 0.6, 0.66, M["screen_cyan"])


def sewing_machine(spec, M, rnd):
    x0, y0, x1, y1 = spec["footprint"]
    mbox("sewing_table", x0, y0, x1, y1, 0.7, 0.74, M["wood"])
    for x in (x0 + 0.03, x1 - 0.07):
        for y in (y0 + 0.03, y1 - 0.07):
            mbox("sewing_leg", x, y, x + 0.04, y + 0.04, 0, 0.7, M["dark"])
    c = W((x0 + x1) / 2, (y0 + y1) / 2)
    box("sewing_base", c.x - 0.22, c.y - 0.1, 0.74, c.x + 0.22, c.y + 0.1, 0.8, M["white"], 0.02)
    box("sewing_arm", c.x + 0.12, c.y - 0.08, 0.8, c.x + 0.2, c.y + 0.08, 1.0, M["white"], 0.02)
    box("sewing_top", c.x - 0.2, c.y - 0.08, 0.94, c.x + 0.2, c.y + 0.08, 1.02, M["white"], 0.02)
    box("sewing_trim", c.x - 0.2, c.y - 0.09, 0.96, c.x + 0.05, c.y - 0.08, 0.99, M["red_box"])
    cyl("thread", c.x - 0.05, c.y, 1.02, 1.07, 0.025, M["neon_cyan"])


def plinth(spec, M, rnd):
    x0, y0, x1, y1 = spec["footprint"]
    mbox("plinth", x0, y0, x1, y1, 0, 1.0, M["plinth"], bevel=0.01)
    c = W((x0 + x1) / 2, (y0 + y1) / 2)
    cyl("sculpture_base", c.x, c.y, 1.0, 1.08, 0.12, M["dark"])
    cyl("sculpture", c.x, c.y, 1.08, 1.32, 0.08, M["sculpture"], r_top=0.02)
    blob("sculpture_top", c.x + 0.02, c.y, 1.36, 0.08, M["sculpture"], subdiv=2, smooth=True)


FITTINGS = {
    "back_counter": back_counter,
    "kitchen": kitchen,
    "counter": counter,
    "cafe_table": cafe_table,
    "noodle_table": noodle_table,
    "stool": stool,
    "planter": planter,
    "planter_flowers": planter_flowers,
    "bench": bench,
    "workbench": workbench,
    "laser_cutter": laser_cutter,
    "loom": loom,
    "printer_3d": printer_3d,
    "sewing_machine": sewing_machine,
    "plinth": plinth,
}
