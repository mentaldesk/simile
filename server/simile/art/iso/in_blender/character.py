"""Inside Blender: a resident from primitives on the armature, replaceable by a skinned mesh."""

import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

from simile.art.iso.in_blender.common import (
    L,
    blob,
    box,
    cyl,
    ellipsoid,
    link,
    material,
    mesh_object,
    rod,
)

BONES = {
    "hips": ((0, 0, 0.93), (0, 0, 1.05), None),
    "spine": ((0, 0, 1.05), (0, 0, 1.47), "hips"),
    "head": ((0, 0, 1.47), (0, 0, 1.8), "spine"),
    "thigh.L": ((0.1, 0, 0.93), (0.1, 0, 0.5), "hips"),
    "thigh.R": ((-0.1, 0, 0.93), (-0.1, 0, 0.5), "hips"),
    "shin.L": ((0.1, 0, 0.5), (0.1, 0, 0.06), "thigh.L"),
    "shin.R": ((-0.1, 0, 0.5), (-0.1, 0, 0.06), "thigh.R"),
    "arm.L": ((0.22, 0, 1.42), (0.24, 0, 1.13), "spine"),
    "arm.R": ((-0.22, 0, 1.42), (-0.24, 0, 1.13), "spine"),
    "forearm.L": ((0.24, 0, 1.13), (0.25, 0, 0.86), "arm.L"),
    "forearm.R": ((-0.24, 0, 1.13), (-0.25, 0, 0.86), "arm.R"),
}
WIDTH = {"slim": 0.17, "average": 0.2, "broad": 0.24}
DEPTH = {"slim": 0.11, "average": 0.13, "broad": 0.15}


def build_rig(name: str, shoulder: float):
    arm = bpy.data.armatures.new(name)
    rig = link(bpy.data.objects.new(name, arm))
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    for bone, (head, tail, parent) in BONES.items():
        k = shoulder / 0.22 if bone.startswith(("arm", "forearm")) else 1.0
        eb = arm.edit_bones.new(bone)
        eb.head = (head[0] * k, head[1], head[2])
        eb.tail = (tail[0] * k, tail[1], tail[2])
        if parent:
            eb.parent = arm.edit_bones[parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    return rig


def attach(rig, bone: str, objs) -> None:
    bpy.context.view_layer.update()
    for obj in objs:
        mw = obj.matrix_world.copy()
        obj.parent = rig
        obj.parent_type = "BONE"
        obj.parent_bone = bone
        bpy.context.view_layer.update()
        obj.matrix_world = mw


def build(spec: dict):
    """A character from its job spec: `key`, `appearance` (F2's Appearance) and `colours`."""
    key, a, cl = spec["key"], spec["appearance"], spec["colours"]

    def m(base, rough=0.7, name=None):
        return material(name or f"{key}_{base}", base, rough, sat=0.9)

    skin = m(a["skin"], 0.55)
    hair = m(a["hair_colour"], 0.6)
    top = m(a["top_colour"], 0.8)
    bottom = m(a["bottom_colour"], 0.8)
    shoe = m(a["shoe_colour"], 0.5)
    accent = m(cl["accent"], 0.6)
    apron = m(cl["apron"], 0.8)
    ink = material("ink", "ink", 0.4, sat=1.0)

    sw, depth = WIDTH[a["build"]], DEPTH[a["build"]]
    rig = build_rig(key, sw + 0.04)
    parts: dict[str, list] = {b: [] for b in BONES}

    parts["spine"].append(ellipsoid("shoulders", (0, 0, 1.36), (sw * 1.02, depth, 0.09), top))
    chest = cyl("chest", 0, 0, 1.0, 1.37, sw * 0.86, top, r_top=sw * 1.02)
    chest.scale = (1, depth / sw, 1)
    parts["spine"].append(chest)
    parts["hips"].append(ellipsoid("pelvis", (0, 0, 0.95), (sw * 0.85, depth * 0.95, 0.13), bottom))
    parts["spine"].append(cyl("neck", 0, 0, 1.4, 1.52, 0.055, skin))
    parts["head"].append(ellipsoid("head", (0, 0, 1.63), (0.105, 0.115, 0.13), skin))
    for ex in (-0.04, 0.04):
        parts["head"].append(blob("eye", ex, -0.1, 1.645, 0.014, ink, subdiv=1))
    parts["head"].append(blob("nose", 0, -0.115, 1.6, 0.018, skin, subdiv=1))

    for side, sx in (("L", 1), ("R", -1)):
        x = 0.1 * sx
        parts[f"thigh.{side}"].append(cyl("thigh", x, 0, 0.5, 0.95, 0.07, bottom, r_top=0.085))
        parts[f"shin.{side}"].append(cyl("shin", x, 0, 0.08, 0.52, 0.055, bottom, r_top=0.068))
        parts[f"shin.{side}"].append(
            box("shoe", x - 0.055, -0.15, 0, x + 0.055, 0.07, 0.09, shoe, bevel=0.025)
        )
        ax = (sw + 0.035) * sx
        parts[f"arm.{side}"].append(cyl("sleeve", ax, 0, 1.12, 1.43, 0.05, top, r_top=0.06))
        parts[f"forearm.{side}"].append(cyl("forearm", ax, 0, 0.88, 1.13, 0.04, skin))
        parts[f"forearm.{side}"].append(blob("hand", ax, 0, 0.84, 0.045, skin, subdiv=1))

    hair_parts(a["hair_style"], hair, parts["head"])
    accessories(set(a["accessories"]), parts, sw, depth, accent, apron, ink)

    for bone, objs in parts.items():
        if objs:
            attach(rig, bone, objs)
    return rig


def accessories(acc: set, parts: dict, sw: float, depth: float, accent, apron, ink) -> None:
    hp = parts["head"]
    if "cap" in acc:
        hp.append(
            ellipsoid("cap", (0, 0, 1.68), (0.118, 0.128, 0.11), accent, cut=((0, 0, 0), (0, 0, 1)))
        )
        hp.append(box("brim", -0.09, -0.24, 1.69, 0.09, -0.06, 1.71, accent))
    if "beanie" in acc:
        hp.append(
            ellipsoid(
                "beanie", (0, 0, 1.67), (0.12, 0.128, 0.15), accent, cut=((0, 0, -0.02), (0, 0, 1))
            )
        )
    if "headphones" in acc:
        for ex in (-0.115, 0.115):
            cup = cyl("earcup", 0, 0, -0.025, 0.025, 0.045, accent, seg=max(L["segments"] // 2, 6))
            cup.rotation_euler.y = math.radians(90)
            cup.location = (ex, 0, 1.62)
            hp.append(cup)
        hp.append(rod("band", (-0.11, 0, 1.66), (0, 0, 1.79), 0.015, accent))
        hp.append(rod("band", (0, 0, 1.79), (0.11, 0, 1.66), 0.015, accent))
    if "sunglasses" in acc:
        hp.append(visor("sunglasses", 1.627, 1.667, ink))
    elif "glasses" in acc:
        hp.append(visor("glasses", 1.638, 1.656, material("frames", "steel", 0.3, 0.6, sat=0.8)))
    if "scarf" in acc:
        parts["spine"].append(cyl("scarf", 0, 0, 1.38, 1.48, 0.09, accent, r_top=0.08))
        parts["spine"].append(box("scarf_tail", 0.02, -0.15, 1.15, 0.09, -0.11, 1.4, accent))
    if "backpack" in acc:
        parts["spine"].append(
            box("backpack", -sw * 0.7, depth * 0.7, 1.0, sw * 0.7, depth + 0.16, 1.4, accent, 0.04)
        )
    if "apron" in acc:
        y0, y1, half = -depth - 0.02, -depth + 0.01, sw * 0.7
        parts["spine"].append(box("apron", -half, y0, 0.9, half, y1, 1.3, apron))
        for side, sx in (("L", 1), ("R", -1)):
            x0, x1 = sorted((0.0, half * sx))
            parts[f"thigh.{side}"].append(box("apron", x0, y0, 0.6, x1, y1, 0.92, apron))


def visor(name: str, z0: float, z1: float, mat):
    """A band across the front of the head, just proud of the face, so no end shows behind."""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=1.0)
    bmesh.ops.scale(bm, vec=(0.111, 0.121, 0.136), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(0, 0, 1.63), verts=bm.verts)
    cuts = (((0, 0, z0), (0, 0, 1)), ((0, 0, z1), (0, 0, -1)), ((0, -0.05, 0), (0, -1, 0)))
    for point, normal in cuts:
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=point, plane_no=normal, clear_inner=True)
    bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary])
    return mesh_object(name, bm, mat, smooth=True)


def hair_parts(style: str, mat, out: list) -> None:
    if style == "bald":
        return
    thick = {"buzz": 1.04, "short": 1.1}.get(style, 1.12)
    out.append(
        ellipsoid(
            "hair_cap",
            (0, 0.005, 1.645),
            (0.105 * thick, 0.115 * thick, 0.13 * thick),
            mat,
            cut=((0, 0, -0.005), (0, 0.565, 1)),
        )
    )
    if style == "curly":
        rnd = random.Random(7)
        for _ in range(14):
            th, ph = rnd.uniform(0, math.tau), rnd.uniform(0.1, 1.2)
            x, y = 0.12 * math.sin(ph) * math.cos(th), 0.13 * math.sin(ph) * math.sin(th)
            y = max(y, -0.07)
            out.append(blob("curl", x, y + 0.01, 1.65 + 0.13 * math.cos(ph), 0.055, mat, subdiv=1))
    elif style == "bob":
        out.append(
            ellipsoid(
                "bob", (0, 0.02, 1.6), (0.13, 0.135, 0.13), mat, cut=((0, -0.05, 0), (0, 1, 0.15))
            )
        )
    elif style == "long":
        out.append(box("long", -0.11, 0.02, 1.25, 0.11, 0.12, 1.66, mat, bevel=0.04))
    elif style == "ponytail":
        out.append(blob("tie", 0, 0.12, 1.68, 0.05, mat, subdiv=1))
        out.append(rod("tail", (0, 0.14, 1.67), (0, 0.2, 1.38), 0.045, mat))
    elif style == "bun":
        out.append(blob("bun", 0, 0.09, 1.76, 0.07, mat))


def _swing(rig, bone: str, angle: float, axis=(1, 0, 0)) -> None:
    pb = rig.pose.bones[bone]
    local = pb.bone.matrix_local.to_3x3().inverted() @ Vector(axis)
    pb.matrix_basis = Matrix.Rotation(-angle, 4, local) @ pb.matrix_basis


def _lift(rig, bone: str, metres: float) -> None:
    pb = rig.pose.bones[bone]
    local = pb.bone.matrix_local.to_3x3().inverted() @ Vector((0, 0, metres))
    pb.matrix_basis = Matrix.Translation(local) @ pb.matrix_basis


def pose(rig, animation: str, frame: int, params: dict) -> None:
    """Frame `frame` of a looping animation, "walk" or "idle", with its job `params`."""
    for pb in rig.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    phase = math.tau * frame / params["frames"]
    if animation == "walk":
        walk(rig, phase, math.radians(params["stride"]), params["leg"])
    elif animation == "idle":
        idle(rig, phase)
    else:
        raise ValueError(f"unknown animation {animation!r}")
    bpy.context.view_layer.update()


def walk(rig, phase: float, stride: float, leg: float) -> None:
    """Thigh and arm swing, a knee bend and a hip drop that keeps the feet on the ground."""
    s = math.sin(phase)
    _swing(rig, "thigh.L", stride * s)
    _swing(rig, "thigh.R", -stride * s)
    _swing(rig, "shin.L", -math.radians(45) * max(0.0, math.cos(phase)) ** 1.5)
    _swing(rig, "shin.R", -math.radians(45) * max(0.0, -math.cos(phase)) ** 1.5)
    _swing(rig, "arm.L", -0.6 * stride * s)
    _swing(rig, "arm.R", 0.6 * stride * s)
    _swing(rig, "forearm.L", math.radians(18))
    _swing(rig, "forearm.R", math.radians(18))
    _lift(rig, "hips", -0.8 * leg * (1 - math.cos(stride * s)))


def idle(rig, phase: float) -> None:
    """A slow breath: the shoulders rise and the arms ease out from the body."""
    breath = (1 - math.cos(phase)) / 2
    _lift(rig, "spine", 0.018 * breath)
    _swing(rig, "arm.L", math.radians(3) * breath, axis=(0, 1, 0))
    _swing(rig, "arm.R", -math.radians(3) * breath, axis=(0, 1, 0))
    _swing(rig, "forearm.L", math.radians(6) + math.radians(2) * breath)
    _swing(rig, "forearm.R", math.radians(6) + math.radians(2) * breath)
    _swing(rig, "head", math.radians(2) * breath)
