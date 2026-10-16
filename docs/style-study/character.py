"""The residents, built from primitives on an 11-bone armature.

A replacement (a skinned body mesh, say) only has to keep build_character's contract: a rig named
after the resident, feet at the origin, facing -Y, with BONES' names, so pose() still animates it.
"""

import math
import random

import bpy
import render3d as R
import scene as S
from mathutils import Matrix, Vector

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


def build_rig(name: str, shoulder: float):
    arm = bpy.data.armatures.new(name)
    rig = R.link(bpy.data.objects.new(name, arm))
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    knees = R.L["knees"]
    for bone, (head, tail, parent) in BONES.items():
        if not knees and bone.startswith(("shin", "forearm")):
            continue
        eb = arm.edit_bones.new(bone)
        hx = head[0] * shoulder / 0.22 if bone.startswith(("arm", "forearm")) else head[0]
        tx = tail[0] * shoulder / 0.22 if bone.startswith(("arm", "forearm")) else tail[0]
        eb.head = (hx, head[1], head[2])
        eb.tail = (tx, tail[1], tail[2])
        if not knees and bone.startswith(("thigh", "arm")):
            eb.tail = (tx, tail[1], 0.06 if bone.startswith("thigh") else 0.86)
        if parent:
            eb.parent = arm.edit_bones[parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    return rig


def attach(rig, bone: str, objs):
    bpy.context.view_layer.update()
    for obj in objs:
        mw = obj.matrix_world.copy()
        obj.parent = rig
        obj.parent_type = "BONE"
        obj.parent_bone = bone
        bpy.context.view_layer.update()
        obj.matrix_world = mw


def bone_of(part: str) -> str:
    if R.L["knees"]:
        return part
    return {
        "shin.L": "thigh.L",
        "shin.R": "thigh.R",
        "forearm.L": "arm.L",
        "forearm.R": "arm.R",
    }.get(part, part)


def build_character(npc_id: str):
    a = S.appearance(npc_id)
    cl = S.colours(npc_id)
    raw = {k: a[k] for k in ("skin", "hair_colour", "top_colour", "bottom_colour", "shoe_colour")}
    box, cyl, rod, blob, ellipsoid = R.box, R.cyl, R.rod, R.blob, R.ellipsoid

    def m(hexv, rough=0.7, name=None):
        return R.material(name or f"{npc_id}_{hexv}", hexv, rough, sat=0.9)

    skin = m(raw["skin"], 0.55)
    hair = m(raw["hair_colour"], 0.6)
    top = m(raw["top_colour"], 0.8)
    bottom = m(raw["bottom_colour"], 0.8)
    shoe = m(raw["shoe_colour"], 0.5)
    accent = m(R.PAL.PALETTE[cl["accent"]], 0.6)
    apron = m(R.PAL.PALETTE[cl["apron"]], 0.8)
    ink = R.material("ink", "ink", 0.4, sat=1.0)

    build = a["build"]
    sw = {"slim": 0.17, "average": 0.2, "broad": 0.24}[build]
    depth = {"slim": 0.11, "average": 0.13, "broad": 0.15}[build]
    rig = build_rig(npc_id, sw + 0.04)
    seg = R.L["seg"]
    detail = R.L["detail"]
    parts: dict[str, list] = {b: [] for b in BONES}

    parts["spine"].append(
        ellipsoid("shoulders", (0, 0, 1.36), (sw * 1.02, depth, 0.09), top, seg=seg)
    )
    chest = cyl("chest", 0, 0, 1.0, 1.37, sw * 0.86, top, r_top=sw * 1.02, seg=seg)
    chest.scale = (1, depth / sw, 1)
    parts["spine"].append(chest)
    parts["hips"].append(ellipsoid("pelvis", (0, 0, 0.95), (sw * 0.85, depth * 0.95, 0.13), bottom))
    parts["spine"].append(cyl("neck", 0, 0, 1.4, 1.52, 0.055, skin))
    head = ellipsoid("head", (0, 0, 1.63), (0.105, 0.115, 0.13), skin)
    parts["head"].append(head)
    if detail:
        for ex in (-0.04, 0.04):
            parts["head"].append(blob("eye", ex, -0.1, 1.645, 0.014, ink, subdiv=1))
        parts["head"].append(blob("nose", 0, -0.115, 1.6, 0.018, skin, subdiv=1))

    for side, sx in (("L", 1), ("R", -1)):
        x = 0.1 * sx
        if R.L["knees"]:
            parts[f"thigh.{side}"].append(cyl("thigh", x, 0, 0.5, 0.95, 0.07, bottom, r_top=0.085))
            parts[f"shin.{side}"].append(cyl("shin", x, 0, 0.08, 0.52, 0.055, bottom, r_top=0.068))
        else:
            parts[f"thigh.{side}"].append(cyl("leg", x, 0, 0.08, 0.95, 0.065, bottom, r_top=0.085))
        parts[bone_of(f"shin.{side}")].append(
            box("shoe", x - 0.055, -0.15, 0, x + 0.055, 0.07, 0.09, shoe, bevel=0.025)
        )
        ax = (sw + 0.035) * sx
        parts[f"arm.{side}"].append(cyl("sleeve", ax, 0, 1.12, 1.43, 0.05, top, r_top=0.06))
        parts[bone_of(f"forearm.{side}")].append(cyl("forearm", ax, 0, 0.88, 1.13, 0.04, skin))
        parts[bone_of(f"forearm.{side}")].append(blob("hand", ax, 0, 0.84, 0.045, skin, subdiv=1))

    hair_parts(a["hair_style"], hair, parts["head"])
    acc = set(a["accessories"])
    hp = parts["head"]
    if "cap" in acc:
        hp.append(
            ellipsoid(
                "cap", (0, 0, 1.68), (0.118, 0.128, 0.11), accent, cut=((0, 0, 0.0), (0, 0, 1))
            )
        )
        brim = box("brim", -0.09, -0.24, 1.69, 0.09, -0.06, 1.71, accent)
        hp.append(brim)
    if "beanie" in acc:
        hp.append(
            ellipsoid(
                "beanie", (0, 0, 1.67), (0.12, 0.128, 0.15), accent, cut=((0, 0, -0.02), (0, 0, 1))
            )
        )
    if "headphones" in acc:
        band = R.material("headphones", "night", 0.4, sat=0.8)
        for ex in (-0.115, 0.115):
            hp.append(cyl("earcup", 0, 0, -0.025, 0.025, 0.045, band, seg=max(seg // 2, 6)))
            hp[-1].rotation_euler.y = math.radians(90)
            hp[-1].location = (ex, 0, 1.62)
        hp.append(rod("band", (-0.11, 0, 1.66), (0, 0, 1.79), 0.015, band))
        hp.append(rod("band", (0, 0, 1.79), (0.11, 0, 1.66), 0.015, band))
    if "glasses" in acc or "sunglasses" in acc:
        lens = ink if "sunglasses" in acc else R.material("frames", "night", 0.3, sat=0.8)
        hp.append(box("glasses", -0.085, -0.125, 1.635, 0.085, -0.11, 1.665, lens))
    if "scarf" in acc:
        parts["spine"].append(cyl("scarf", 0, 0, 1.38, 1.48, 0.09, accent, r_top=0.08))
        parts["spine"].append(box("scarf_tail", 0.02, -0.15, 1.15, 0.09, -0.11, 1.4, accent))
    if "backpack" in acc:
        parts["spine"].append(
            box(
                "backpack",
                -sw * 0.7,
                depth * 0.7,
                1.0,
                sw * 0.7,
                depth + 0.16,
                1.4,
                accent,
                bevel=0.04,
            )
        )
    if "apron" in acc:
        parts["spine"].append(
            box("apron", -sw * 0.7, -depth - 0.02, 0.6, sw * 0.7, -depth + 0.01, 1.3, apron)
        )

    for bone, objs in parts.items():
        if objs:
            attach(rig, bone if bone in rig.data.bones else bone_of(bone), objs)
    return rig


def hair_parts(style: str, mat, out: list):
    if style == "bald":
        return
    box, rod, blob, ellipsoid = R.box, R.rod, R.blob, R.ellipsoid
    cap_cut = ((0, 0, -0.005), (0, 0.565, 1))
    thick = {"buzz": 1.04, "short": 1.1}.get(style, 1.12)
    out.append(
        ellipsoid(
            "hair_cap",
            (0, 0.005, 1.645),
            (0.105 * thick, 0.115 * thick, 0.13 * thick),
            mat,
            cut=cap_cut,
        )
    )
    if style == "curly":
        rnd = random.Random(7)
        for _ in range(14 if R.L["detail"] else 6):
            th = rnd.uniform(0, math.tau)
            ph = rnd.uniform(0.1, 1.2)
            x, y = 0.12 * math.sin(ph) * math.cos(th), 0.13 * math.sin(ph) * math.sin(th)
            if y < -0.07:
                y = -0.07
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


def pose(rig, phase: float | None):
    """phase in radians along the walk cycle; None stands still."""
    amp = math.radians(24)
    for pb in rig.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    if phase is None:
        return

    def swing(bone, angle):
        if bone not in rig.pose.bones:
            return
        pb = rig.pose.bones[bone]
        axis = pb.bone.matrix_local.to_3x3().inverted() @ Vector((1, 0, 0))
        pb.matrix_basis = Matrix.Rotation(-angle, 4, axis)

    s = math.sin(phase)
    leg = 0.87
    drop = 0.8 * leg * (1 - math.cos(amp * s))
    swing("thigh.L", amp * s)
    swing("thigh.R", -amp * s)
    swing("shin.L", -math.radians(45) * max(0.0, math.cos(phase)) ** 1.5)
    swing("shin.R", -math.radians(45) * max(0.0, -math.cos(phase)) ** 1.5)
    swing("arm.L", -0.6 * amp * s)
    swing("arm.R", 0.6 * amp * s)
    swing("forearm.L", math.radians(18))
    swing("forearm.R", math.radians(18))
    hips = rig.pose.bones["hips"]
    hips.matrix_basis = Matrix.Translation((0, -drop, 0))
