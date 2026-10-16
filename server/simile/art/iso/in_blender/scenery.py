"""Inside Blender: the village's models, ported from docs/style-study/render3d.py."""

import math
import random

import bmesh
import bpy
from mathutils import Vector

from simile.art.iso import camera as cam
from simile.art.iso.in_blender.common import (
    W,
    blob,
    box,
    cjk_font,
    cyl,
    emit,
    link,
    material,
    mesh_object,
    rod,
    text,
    tilt,
)

T = cam.TILE_M
STOREY_M = 3.0
GROUND_MARKINGS = ("inlay", "tactile", "line", "zebra")


def mats() -> dict:
    return {
        "pavement": material("pavement", "pavement", 0.85, pattern="pavers", sat=0.4, val=0.78),
        "plaza": material("plaza", "sand", 0.7, pattern="pavers", alt="grid", val=0.8, sat=0.4),
        "inlay": material("inlay", "amber", 0.35, 0.9, sat=0.45, val=0.6),
        "grass": material("grass", "green", 0.95, pattern="grass", alt="forest", sat=0.6, val=0.85),
        "curb": material("curb", "concrete", 0.8, pattern="noise", sat=0.3, val=0.9),
        "road": material("road", "slate", 0.9, pattern="noise", sat=0.25, val=0.55),
        "line": material("line", "pavement", 0.7, sat=0.2, val=1.1),
        "tactile": material("tactile", "amber", 0.7, sat=0.85),
        "water": material(
            "water", "blue", 0.05, sat=0.7, val=0.6, emit="cyan", strength=emit("water", 0.08)
        ),
        "bark": material("bark", "umber", 0.9, sat=0.6),
        "leaf": material("leaf", "green", 0.85, sat=0.65, val=0.9),
        "leaf2": material("leaf2", "forest", 0.85, sat=0.65, val=1.0),
        "leaf3": material("leaf3", "lime", 0.85, sat=0.5, val=0.7),
        "palm": material("palm", "lime", 0.8, sat=0.55, val=0.8),
        "steel": material("steel", "steel", 0.35, 0.8, sat=0.4),
        "dark": material("dark", "night", 0.5, 0.3, sat=0.4),
        "wood": material("wood", "brown", 0.7, sat=0.6),
        "concrete": material("concrete", "concrete", 0.85, pattern="noise", sat=0.3),
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
        "bike_yellow": material("bike_yellow", "amber", 0.5, sat=0.8),
        "cream_wall": material("cream_wall", "cream", 0.9, pattern="wall", sat=0.55),
        "slate_wall": material("slate_wall", "slate", 0.8, pattern="wall", sat=0.5),
        "band": material("band", "concrete", 0.85, pattern="noise", sat=0.3, val=0.8),
        "tank": material("tank", "pavement", 0.4, 0.6, sat=0.3),
        "cafe_wall": material(
            "cafe_wall", "umber", 0.7, pattern="stripes", alt="espresso", sat=0.6
        ),
        "roof": material("roof", "steel", 0.95, pattern="noise", sat=0.3),
        "roof_green": material("roof_green", "green", 0.95, pattern="grass", alt="forest", sat=0.6),
        "solar": material("solar", "navy", 0.15, 0.4, sat=0.7, val=0.7),
        "awning_blue": material(
            "awning_blue", "blue", 0.8, pattern="stripes", alt="white", sat=0.7
        ),
        "awning_red": material("awning_red", "red", 0.8, pattern="stripes", alt="white", sat=0.7),
        "awning_cafe": material(
            "awning_cafe", "umber", 0.8, pattern="stripes", alt="cream", sat=0.7
        ),
    }


def build_ground(cells: list[list[str]], heights: list[list[float]]) -> None:
    M = mats()
    groups: dict[str, list] = {}
    raised = {}
    for y, row in enumerate(cells):
        for x, name in enumerate(row):
            z = heights[y][x]
            kinds = ("grass", "water", "road", "plaza")
            kind = next((k for k in kinds if name.startswith(k)), "pavement")
            kind = "road" if name.startswith("crosswalk") else kind
            raised[(x, y)] = z
            groups.setdefault(kind, []).append((x, y, z))
            markings(name, x, y, z, M)

    for kind, group_cells in groups.items():
        bm = bmesh.new()
        for x, y, z in group_cells:
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
                nz = raised.get((nx, ny), 0.0)
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


def markings(name: str, x: int, y: int, z: float, M: dict) -> None:
    if name == "plaza_inlay":
        c = W(x + 0.5, y + 0.5)
        cyl("inlay", c.x, c.y, 0, 0.012, 0.42, M["inlay"], seg=32)
        cyl("inlay_core", c.x, c.y, 0, 0.016, 0.3, M["plaza"], seg=32)
    elif name.startswith("tactile"):
        c = W(x + 0.5, y + 0.5)
        if name.endswith("_v"):
            box("tactile", c.x - 0.15, c.y - T / 2, 0, c.x + 0.15, c.y + T / 2, 0.012, M["tactile"])
        else:
            box("tactile", c.x - T / 2, c.y - 0.15, 0, c.x + T / 2, c.y + 0.15, 0.012, M["tactile"])
    elif name.startswith("road_line"):
        c = W(x + 0.5, y + 0.5, z)
        box("line", c.x - 0.3, c.y - 0.05, c.z, c.x + 0.3, c.y + 0.05, c.z + 0.01, M["line"])
    elif name.startswith("crosswalk"):
        c = W(x + 0.5, y + 0.5, z)
        for i in range(3):
            yy = c.y - 0.4 + i * 0.36
            box("zebra", c.x - 0.5, yy, c.z, c.x + 0.5, yy + 0.16, c.z + 0.01, M["line"])


def ground_plane(x: float, y: float, half: float = 40.0) -> None:
    """Pavement under a sprite, out of the camera's sight, so the object gets light bounced up."""
    c = W(x, y)
    bm = bmesh.new()
    corners = ((-half, -half), (half, -half), (half, half), (-half, half))
    bm.faces.new([bm.verts.new((c.x + dx, c.y + dy, 0.0)) for dx, dy in corners])
    plane = mesh_object("plane", bm, mats()["pavement"])
    plane.visible_camera = False


def build_building(b: dict) -> None:
    M = mats()
    x0, x1, y0, y1 = b["x0"], b["x1"], b["y0"], b["y1"]
    storeys = b["storeys"]
    height = storeys * STOREY_M
    wall = {"cafe": M["cafe_wall"], "slate": M["slate_wall"], "cream": M["cream_wall"]}
    a, c = W(x0, y1), W(x1, y0)
    box("building", a.x, a.y, 0, c.x, c.y, height, wall[b["material"]], bevel=0.03)
    for k in range(1, storeys):
        z = k * STOREY_M
        box("band", a.x - 0.06, a.y - 0.06, z - 0.08, c.x + 0.06, c.y + 0.06, z + 0.08, M["band"])
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
    roof = M["roof_green"] if b["green_roof"] else M["roof"]
    box("roof", a.x + par, a.y + par, height, c.x - par, c.y - par, height + 0.06, roof)
    rnd = random.Random(x0 * 100 + y0)
    if not b["green_roof"]:
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
    else:
        for _ in range(6):
            p = W(rnd.uniform(x0 + 0.8, x1 - 0.8), rnd.uniform(y0 + 0.8, y1 - 0.8), height)
            blob("roofbush", p.x, p.y, p.z + 0.2, rnd.uniform(0.25, 0.45), M["leaf2"], squash=0.7)
    for tx, ty, item in b["roof_items"]:
        roof_item(item, W(tx + 0.5, ty + 0.5, height + 0.06), M)

    rows = b["facade"]
    for i, row in enumerate(rows):
        k = storeys - 1 - i
        for col, (tile, deco) in enumerate(row):
            facade_item(tile or "", deco, (x0 + col + 0.5) * T, a.y, k * STOREY_M, k, M, rnd)
    if rows:
        signs(b, rows, a.y, M)


def roof_item(item: str, p: Vector, M: dict) -> None:
    if item == "solar":
        for i in range(2):
            yy = p.y - 0.25 + i * 0.5
            panel = box(
                "solar", p.x - 0.5, yy - 0.2, p.z + 0.25, p.x + 0.5, yy + 0.2, p.z + 0.3, M["solar"]
            )
            tilt(panel, math.radians(-20), (0, yy, p.z + 0.27))
            cyl("solar_leg", p.x, yy + 0.1, p.z, p.z + 0.3, 0.03, M["steel"])
    elif item == "ac":
        box("ac", p.x - 0.4, p.y - 0.3, p.z, p.x + 0.4, p.y + 0.3, p.z + 0.6, M["white"], 0.03)
        cyl("fan", p.x, p.y, p.z + 0.6, p.z + 0.63, 0.22, M["dark"])
    elif item == "skylight":
        box(
            "skylight", p.x - 0.4, p.y - 0.4, p.z, p.x + 0.4, p.y + 0.4, p.z + 0.35, M["glass_cool"]
        )


def facade_item(tile, deco, cx, fy, z, k, M, rnd):
    half = T / 2
    if tile.startswith(("window_", "base_window_")):
        lit = rnd.random() < 0.45
        g = M["glass_lit"] if lit else M["glass"]
        box("window", cx - 0.36, fy - 0.04, z + 0.9, cx + 0.36, fy + 0.02, z + 2.3, g)
        if k > 0 and rnd.random() < 0.4:
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
        for zz in (z + 0.86, z + 2.3):
            box("frame", cx - 0.42, fy - 0.07, zz, cx + 0.42, fy + 0.01, zz + 0.06, M["concrete"])
        box("mullion", cx - 0.02, fy - 0.06, z + 0.9, cx + 0.02, fy, z + 2.3, M["dark"])
    elif tile.startswith("door_") and not tile.endswith("_top"):
        box("door", cx - 0.42, fy - 0.05, z, cx + 0.42, fy + 0.02, z + 2.3, M["wood"])
        box("doorframe", cx - 0.5, fy - 0.08, z + 2.3, cx + 0.5, fy, z + 2.4, M["concrete"])
    elif tile.startswith(("shopfront", "cafe_window")):
        warm = tile.startswith("cafe") or rnd.random() < 0.5
        glass = M["glass_lit"] if warm else M["glass_cool"]
        box(
            "shopglass",
            cx - half + 0.04,
            fy - 0.04,
            z + 0.35,
            cx + half - 0.04,
            fy + 0.02,
            z + 2.5,
            glass,
        )
        box("mullion", cx - half, fy - 0.07, z + 0.3, cx - half + 0.06, fy, z + 2.55, M["dark"])
        box("transom", cx - half, fy - 0.07, z + 2.5, cx + half, fy, z + 2.58, M["dark"])
        box("sill", cx - half, fy - 0.09, z + 0.3, cx + half, fy, z + 0.36, M["dark"])
    elif tile in ("shop_door", "cafe_door"):
        glass = M["glass_lit"] if tile == "cafe_door" else M["glass_cool"]
        box("door_glass", cx - 0.42, fy - 0.04, z, cx + 0.42, fy + 0.02, z + 2.4, glass)
        box("door_frame", cx - 0.48, fy - 0.08, z + 2.4, cx + 0.48, fy, z + 2.5, M["dark"])
    if deco:
        wall_decor(deco, cx, fy, z, M)


def wall_decor(deco, cx, fy, z, M):
    half = T / 2
    if deco.startswith(("awning", "cafe_awning")):
        if deco.startswith("cafe"):
            m = M["awning_cafe"]
        else:
            m = M["awning_red"] if "red" in deco else M["awning_blue"]
        aw = box("awning", cx - half, fy - 0.9, z + 2.6, cx + half, fy, z + 2.66, m)
        tilt(aw, math.radians(22), (0, fy, z + 2.9))
    elif deco == "ac_unit":
        box("ac_unit", cx - 0.35, fy - 0.35, z + 2.0, cx + 0.35, fy, z + 2.5, M["white"], 0.03)
    elif deco == "screen_l":
        x0, x1 = cx - half + 0.1, cx + T + half - 0.1
        box("screen_back", x0, fy - 0.12, z + 0.5, x1, fy, z + 2.6, M["dark"])
        box("screen", x0 + 0.08, fy - 0.14, z + 0.6, x1 - 0.08, fy - 0.1, z + 2.5, M["screen_pink"])
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
        font = cjk_font()
        body = "面" if font else "NOODLE"
        text("neon_bowl", body, cx, fy - 0.1, z + 1.5, 0.7, M["neon_amber"], font=font)
    elif deco.startswith("neon_vertical_top"):
        font = cjk_font()
        box("vsign", cx - 0.3, fy - 0.4, z - 2.0, cx + 0.3, fy - 0.3, z + 2.4, M["dark"])
        body = "面\n馆" if font else "N\nO\nO\nD"
        text("vsign_text", body, cx, fy - 0.42, z + 0.2, 0.9, M["neon_violet"], font=font)
    elif deco.startswith("neon_"):
        text(deco, "*", cx, fy - 0.1, z + 1.5, 0.6, M["neon_pink"])


def bolt(cx, fy, z, mat):
    pts = [(-0.1, 0.45), (0.22, 0.45), (0.05, 0.08), (0.25, 0.08), (-0.18, -0.5), (-0.02, -0.08)]
    pts.append((-0.22, -0.08))
    bm = bmesh.new()
    face = bm.faces.new([bm.verts.new((cx + px, fy, z + pz)) for px, pz in pts])
    ext = bmesh.ops.extrude_face_region(bm, geom=[face])
    moved = [v for v in ext["geom"] if isinstance(v, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, -0.05, 0), verts=moved)
    mesh_object("bolt", bm, mat)


def signs(b, rows, fy, M):
    names = [t or "" for t, _ in rows[0]]
    if "cafe_sign_l" in names:
        cx = (b["x0"] + names.index("cafe_sign_l") + 1.0) * T
        z = (b["storeys"] - 1) * STOREY_M
        box("sign_board", cx - 1.05, fy - 0.12, z + 1.0, cx + 1.05, fy, z + 2.0, M["dark"], 0.02)
        text("sign", "COFFEE", cx, fy - 0.14, z + 1.5, 0.55, M["neon_amber"])


def build_prop(spec: dict) -> list:
    """A prop at the origin, then moved to (x, y, z) if the spec has a place."""
    before = set(bpy.context.scene.objects)
    prop(spec["kind"], random.Random(spec["variant"]))
    made = [o for o in bpy.context.scene.objects if o not in before]
    if "x" in spec:
        offset = W(spec["x"], spec["y"], spec["z"])
        for obj in made:
            if obj.parent is None:
                obj.location += offset
    return made


def prop(kind: str, rnd: random.Random) -> None:
    M = mats()
    if kind == "tree":
        cyl("trunk", 0, 0, 0, 2.4, 0.16, M["bark"], r_top=0.09)
        crowns = [
            (0, 0, 3.0, 1.05),
            (0.55, 0.2, 2.6, 0.75),
            (-0.5, -0.25, 2.7, 0.8),
            (0.15, -0.5, 3.3, 0.7),
            (-0.2, 0.45, 3.5, 0.65),
        ]
        for i, (dx, dy, dz, r) in enumerate(crowns):
            m = (M["leaf"], M["leaf2"], M["leaf3"])[i % 3]
            crown = blob("crown", dx, dy, dz, r * rnd.uniform(0.9, 1.1), m, 3, 0.85, smooth=True)
            lumpy(crown)
    elif kind == "bush":
        for dx, dy, r in ((0, 0, 0.4), (0.3, 0.15, 0.3), (-0.25, -0.1, 0.28)):
            blob("bush", dx, dy, r * 0.7, r, M["leaf2"], squash=0.8)
    elif kind == "palm":
        prev = Vector((0, 0, 0))
        for i in range(6):
            t = (i + 1) / 6
            nxt = Vector((0.35 * t * t, -0.15 * t * t, 4.0 * t))
            rod("palm_trunk", prev, nxt, 0.13 - 0.04 * t, M["bark"])
            prev = nxt
        for j in range(8):
            frond(prev, j / 8 * math.tau, M["palm"])
    elif kind == "lamp":
        cyl("lamp_pole", 0, 0, 0, 4.0, 0.06, M["steel"], r_top=0.045)
        box("lamp_arm", -0.05, -0.05, 3.9, 0.65, 0.05, 3.98, M["steel"])
        box("lamp_head", 0.3, -0.14, 3.78, 0.8, 0.14, 3.9, M["dark"])
        box("lamp_glow", 0.34, -0.11, 3.7, 0.76, 0.11, 3.78, M["lamp"])
        if emit("lamp", 1.0):
            light = bpy.data.lights.new("lamp", "POINT")
            light.energy = emit("lamp", 900)
            light.color = (1.0, 0.82, 0.6)
            light.shadow_soft_size = 0.2
            link(bpy.data.objects.new("lamp_light", light)).location = (0.55, 0, 3.5)
    elif kind == "bench":
        for i in range(3):
            yy = -0.22 + i * 0.16
            box("slat", -0.95, yy, 0.42, 0.95, yy + 0.12, 0.47, M["wood"], bevel=0.01)
        for dx in (-0.7, 0.7):
            box("bench_leg", dx - 0.04, -0.25, 0, dx + 0.04, 0.25, 0.42, M["dark"])
    elif kind in ("planter_flowers", "planter"):
        box("planter", -0.45, -0.45, 0, 0.45, 0.45, 0.5, M["concrete"], bevel=0.03)
        box("soil", -0.38, -0.38, 0.5, 0.38, 0.38, 0.52, M["soil"])
        blob("planter_bush", 0, 0, 0.7, 0.36, M["leaf2"], squash=0.7)
        if kind == "planter_flowers":
            for i in range(9):
                a = i * 2.4
                m = M["flower_pink"] if i % 2 else M["flower_yellow"]
                blob("flower", 0.26 * math.cos(a), 0.26 * math.sin(a), 0.82, 0.07, m, subdiv=1)
    elif kind == "fountain":
        cyl("basin", 0, 0, 0, 0.5, 1.15, M["concrete"], bevel=0.02)
        cyl("water", 0, 0, 0.5, 0.51, 1.0, M["water"])
        cyl("pedestal", 0, 0, 0.5, 1.2, 0.18, M["concrete"])
        cyl("bowl", 0, 0, 1.2, 1.35, 0.5, M["concrete"], r_top=0.55)
        cyl("bowl_water", 0, 0, 1.35, 1.36, 0.47, M["water"])
        cyl("jet", 0, 0, 1.35, 2.1, 0.05, M["screen_cyan"], r_top=0.02)
    elif kind == "terminal":
        box("terminal", -0.3, -0.18, 0, 0.3, 0.18, 2.1, M["dark"], bevel=0.03)
        box("terminal_screen", -0.24, -0.2, 0.9, 0.24, -0.17, 1.8, M["screen_cyan"])
        box("terminal_band", -0.31, -0.19, 1.92, 0.31, 0.19, 2.02, M["screen_pink"])
    elif kind == "vending":
        box("vending", -0.45, -0.35, 0, 0.45, 0.35, 1.95, M["red_box"], bevel=0.03)
        box("vending_front", -0.36, -0.37, 0.7, 0.36, -0.34, 1.8, M["glass_cool"])
    elif kind == "bins":
        for dx, m in ((-0.24, M["bin_green"]), (0.24, M["bin_blue"])):
            box("bin", dx - 0.2, -0.25, 0, dx + 0.2, 0.25, 0.95, m, bevel=0.03)
    elif kind.startswith("bike"):
        frame_m = M["bin_blue"] if "blue" in kind else M["bike_yellow"]
        for dx in (-0.45, 0.45):
            wheel = cyl("wheel", 0, 0, -0.03, 0.03, 0.32, M["dark"])
            wheel.rotation_euler.x = math.radians(90)
            wheel.location = (dx, 0, 0.33)
        rod("bike_frame", (-0.45, 0, 0.33), (0, 0, 0.75), 0.025, frame_m)
        rod("bike_frame", (0, 0, 0.75), (0.45, 0, 0.33), 0.025, frame_m)
        rod("bike_frame", (-0.1, 0, 0.33), (0.45, 0, 0.85), 0.025, frame_m)
    elif kind == "cafe_table":
        cyl("table_top", 0, 0, 0.72, 0.76, 0.36, M["white"])
        cyl("table_leg", 0, 0, 0, 0.72, 0.04, M["dark"])
        for dx in (-0.55, 0.55):
            box("chair", dx - 0.2, -0.2, 0.42, dx + 0.2, 0.2, 0.47, M["wood"])
            bx = dx + (0.18 if dx > 0 else -0.22)
            box("chair_back", bx, -0.2, 0.47, bx + 0.04, 0.2, 0.9, M["wood"])
            for ddx in (-0.16, 0.16):
                box("chair_leg", dx + ddx - 0.02, -0.02, 0, dx + ddx + 0.02, 0.02, 0.42, M["dark"])
    elif kind == "cafe_menu":
        for s in (-1, 1):
            board = box("aboard", -0.28, -0.02, 0, 0.28, 0.02, 0.95, M["dark"])
            tilt(board, math.radians(12 * s), (0, 0, 0.95))
    elif kind == "bollard":
        cyl("bollard", 0, 0, 0, 0.9, 0.09, M["steel"])
    else:
        raise ValueError(f"no model for prop {kind!r}")


def lumpy(obj) -> None:
    tex = bpy.data.textures.get("leafy") or bpy.data.textures.new("leafy", "CLOUDS")
    tex.noise_scale = 0.35
    mod = obj.modifiers.new("lumps", "DISPLACE")
    mod.texture = tex
    mod.strength = 0.35
    mod.mid_level = 0.5
    mod.texture_coords = "LOCAL"


def frond(top, ang, mat) -> None:
    bm = bmesh.new()
    d = Vector((math.cos(ang), math.sin(ang), 0))
    side = Vector((-d.y, d.x, 0))
    prev = None
    for i in range(7):
        t = i / 6
        c = top + d * (1.6 * t) + Vector((0, 0, 0.5 * t - 1.3 * t * t))
        w = 0.28 * math.sin(math.pi * min(t * 1.1, 1.0)) + 0.02
        pair = (bm.verts.new(c + side * w), bm.verts.new(c - side * w))
        if prev:
            bm.faces.new((prev[0], prev[1], pair[1], pair[0]))
        prev = pair
    mesh_object("frond", bm, mat)
