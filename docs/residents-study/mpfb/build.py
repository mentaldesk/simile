"""Approach 3 in Blender: an MPFB human built from a resident's spec, dressed in CC0 MakeHuman
assets and simple accessories, toon-shaded, posed by the 2D rig's joint angles and rendered
side-on, with a flat-colour pass for measuring.

./blender.sh -b -P mpfb/build.py -- spec.json out_folder
"""

import json
import math
import os
import sys
import time
from pathlib import Path

import bmesh
import bpy
from bl_ext.user_default.mpfb.services.humanservice import HumanService
from bl_ext.user_default.mpfb.services.locationservice import LocationService
from mathutils import Quaternion, Vector

FACING = Vector((0.0, -1.0, 0.0))
UP = Vector((0.0, 0.0, 1.0))
LATERAL = FACING.cross(UP)
"""A turn about this by a positive angle swings a hanging limb forward, as the 2D rig's does."""
NEAR, FAR = "_r", "_l"
"""Seen from the side the camera is on: the 2D rig's near limbs are the right ones."""
INK = (46, 32, 28)
CLOTHES = {
    "top": "clothes/elvs_crude_t-shirt_male/elvs_crude_t-shirt_male.mhclo",
    "bottom": "clothes/toigo_wool_pants/toigo_wool_pants.mhclo",
    "shoe": "clothes/shoes06/shoes06.mhclo",
}
EYES = "eyes/low-poly/low-poly.mhclo"
EYEBROWS = "eyebrows/eyebrow001/eyebrow001.mhclo"


def srgb(c) -> tuple[float, float, float, float]:
    def linear(v: float) -> float:
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    return (linear(c[0]), linear(c[1]), linear(c[2]), 1.0)


def toon(name: str, colour, shadow: float = 0.72, grime: str | None = None) -> bpy.types.Material:
    """Flat colour in two tones, light and shadow, by a hard ramp on the diffuse light, with
    FLUX's grime multiplied in if given."""
    mat = bpy.data.materials.new(name)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    diffuse = nodes.new("ShaderNodeBsdfDiffuse")
    to_rgb = nodes.new("ShaderNodeShaderToRGB")
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (shadow, shadow, shadow, 1)
    ramp.color_ramp.elements[1].position = 0.3
    ramp.color_ramp.elements[1].color = (1, 1, 1, 1)
    mix = nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 1.0
    mix.inputs["A"].default_value = srgb(colour)
    if grime:
        texture = nodes.new("ShaderNodeTexImage")
        texture.image = bpy.data.images.load(grime, check_existing=True)
        coords = nodes.new("ShaderNodeTexCoord")
        tiled = nodes.new("ShaderNodeMapping")
        tiled.inputs["Scale"].default_value = (2.0, 2.0, 2.0)
        dirt = nodes.new("ShaderNodeMix")
        dirt.data_type = "RGBA"
        dirt.blend_type = "MULTIPLY"
        dirt.inputs["Factor"].default_value = 0.6
        dirt.inputs["A"].default_value = srgb(colour)
        links.new(coords.outputs["UV"], tiled.inputs["Vector"])
        links.new(tiled.outputs["Vector"], texture.inputs["Vector"])
        links.new(texture.outputs["Color"], dirt.inputs["B"])
        links.new(dirt.outputs["Result"], mix.inputs["A"])
    emit = nodes.new("ShaderNodeEmission")
    links.new(diffuse.outputs["BSDF"], to_rgb.inputs["Shader"])
    links.new(to_rgb.outputs["Color"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], mix.inputs["B"])
    links.new(mix.outputs["Result"], emit.inputs["Color"])
    links.new(emit.outputs["Emission"], out.inputs["Surface"])
    mat["flat"] = list(colour)
    return mat


def flat(colour) -> bpy.types.Material:
    """The colour alone, unlit, for the measuring pass."""
    key = "flat-" + "-".join(str(int(v)) for v in colour)
    if key in bpy.data.materials:
        return bpy.data.materials[key]
    mat = bpy.data.materials.new(key)
    mat.use_fake_user = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    emit = nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = srgb(colour)
    out = nodes.new("ShaderNodeOutputMaterial")
    mat.node_tree.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    return mat


def dress(obj, mat) -> None:
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    for poly in obj.data.polygons:
        poly.material_index = 0


def asset(human, relative: str, kind: str):
    path = os.path.join(LocationService.get_user_data(), relative)
    return HumanService.add_mhclo_asset(path, human, asset_type=kind, subdiv_levels=0)


def head_bone(rig):
    return rig.pose.bones["head"]


def parented(obj, rig, bone: str) -> None:
    """`obj`, placed in armature space at rest, follows `bone`."""
    bpy.context.view_layer.update()
    world = obj.matrix_world.copy()
    obj.parent = rig
    obj.parent_type = "BONE"
    obj.parent_bone = bone
    obj.matrix_world = world


def skull(rig, human) -> tuple[Vector, Vector, Vector]:
    """The head's lowest corner, highest corner and centre, as posed: the body's vertices above
    the neck, with the head grown."""
    hz = (rig.matrix_world @ rig.pose.bones["head"].head).z + 0.02
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = human.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    points = [evaluated.matrix_world @ v.co for v in mesh.vertices]
    evaluated.to_mesh_clear()
    points = [p for p in points if p.z > hz and abs(p.x) < 0.3]
    lo = Vector([min(p[i] for p in points) for i in range(3)])
    hi = Vector([max(p[i] for p in points) for i in range(3)])
    return lo, hi, (lo + hi) / 2


def accessories(spec, rig, human, mats) -> list:
    """Simple shapes for what the CC0 packs have no free asset for: caps, buns, scarves,
    headphones, backpacks and aprons."""
    made = []
    lo, hi, centre = skull(rig, human)
    half_x, half_y, crown = (hi.x - lo.x) / 2, (hi.y - lo.y) / 2, hi.z
    wearing = set(spec["accessories"])

    def add(obj, mat, bone):
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        dress(obj, mat)
        parented(obj, rig, bone)
        bpy.ops.object.shade_smooth()
        made.append(obj)
        return obj

    if spec.get("bun"):
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=half_x * 0.45, location=(centre.x, hi.y - half_x * 0.15, crown - half_x * 0.3)
        )
        add(bpy.context.object, mats["hair"], "head")
    if "cap" in wearing:
        rim = centre.z + (crown - centre.z) * 0.2
        bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=(centre.x, centre.y, rim))
        cap = bpy.context.object
        cap.scale = (half_x * 1.1, half_y * 1.08, (crown - rim) * 1.2)
        bpy.ops.object.transform_apply(scale=True)
        mesh = bmesh.new()
        mesh.from_mesh(cap.data)
        bmesh.ops.delete(mesh, geom=[v for v in mesh.verts if v.co.z < -0.002], context="VERTS")
        mesh.to_mesh(cap.data)
        mesh.free()
        add(cap, mats["accent"], "head")
        bpy.ops.mesh.primitive_cylinder_add(
            radius=half_x * 0.85, depth=0.012, location=(centre.x, lo.y + half_x * 0.1, rim)
        )
        brim = bpy.context.object
        brim.scale = (1.0, 0.7, 1.0)
        bpy.ops.object.transform_apply(scale=True)
        add(brim, mats["accent"], "head")
    if "headphones" in wearing:
        for side in (-1, 1):
            bpy.ops.mesh.primitive_cylinder_add(
                radius=half_y * 0.42,
                depth=half_x * 0.35,
                location=(centre.x + side * half_x * 1.02, centre.y, centre.z - half_x * 0.05),
                rotation=(0, math.pi / 2, 0),
            )
            add(bpy.context.object, mats["accent"], "head")
        bpy.ops.mesh.primitive_torus_add(
            major_radius=half_x * 1.05,
            minor_radius=half_x * 0.08,
            location=(centre.x, centre.y, centre.z + half_x * 0.05),
            rotation=(0, math.pi / 2, math.pi / 2),
        )
        add(bpy.context.object, mats["accent"], "head")
    neck = rig.matrix_world @ rig.data.bones["neck_01"].head_local
    chest = rig.matrix_world @ rig.data.bones["spine_03"].head_local
    if "scarf" in wearing:
        bpy.ops.mesh.primitive_torus_add(
            major_radius=half_x * 0.62,
            minor_radius=half_x * 0.22,
            location=(neck.x, neck.y, neck.z + 0.01),
        )
        ring = bpy.context.object
        ring.scale = (1.0, 0.9, 1.0)
        add(ring, mats["accent"], "spine_03")
        bpy.ops.mesh.primitive_cube_add(
            size=1, location=(neck.x + half_x * 0.25, neck.y - half_y * 0.55, neck.z - 0.12)
        )
        tail = bpy.context.object
        tail.scale = (0.06, 0.03, 0.22)
        add(tail, mats["accent"], "spine_03")
    if "backpack" in wearing:
        bpy.ops.mesh.primitive_cube_add(size=1, location=(chest.x, chest.y + 0.13, chest.z - 0.08))
        pack = bpy.context.object
        pack.scale = (0.3, 0.14, 0.38)
        bevel = pack.modifiers.new("round", "BEVEL")
        bevel.width = 0.05
        bevel.segments = 3
        add(pack, mats["accent"], "spine_03")
    if "apron" in wearing:
        hips = rig.matrix_world @ rig.data.bones["pelvis"].head_local
        bpy.ops.mesh.primitive_cube_add(size=1, location=(hips.x, hips.y - 0.13, hips.z - 0.05))
        apron = bpy.context.object
        apron.scale = (0.34, 0.012, 0.62)
        add(apron, mats["apron"], "spine_01")
    return made


def build(spec: dict):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    human = HumanService.create_human(macro_detail_dict=spec["macro"])
    rig = HumanService.add_builtin_rig(human, "game_engine")
    parts = {"skin": [human]}
    for region, path in CLOTHES.items():
        parts.setdefault(region, []).append(asset(human, path, "Clothes"))
    if spec["hair"]:
        hair = f"hair/{spec['hair']}/{spec['hair']}.mhclo"
        parts.setdefault("hair", []).append(asset(human, hair, "Hair"))
    parts.setdefault("ink", []).append(asset(human, EYES, "Eyes"))
    parts.setdefault("hair", []).append(asset(human, EYEBROWS, "Eyebrows"))
    grime = spec.get("grime")
    mats = {
        name: toon(name, c, grime=None if name in ("skin", "hair") else grime)
        for name, c in spec["colours"].items()
    }
    mats["ink"] = toon("ink", INK, shadow=1.0)
    for mat in mats.values():
        mat.use_fake_user = True
    for region, objects in parts.items():
        for obj in objects:
            dress(obj, mats["ink" if region == "ink" else region])
    for obj in bpy.data.objects:
        for modifier in getattr(obj, "modifiers", []):
            if modifier.type == "ARMATURE":
                modifier.use_deform_preserve_volume = False
    proportioned(rig, spec["proportions"])
    bpy.context.view_layer.update()
    for obj in accessories(spec, rig, human, mats):
        region = next(k for k, m in mats.items() if obj.data.materials[0] == m)
        parts.setdefault(region, []).append(obj)
    marked(human, ("head", "hand", "thumb", "index", "middle", "ring", "pinky"))
    unlined = bpy.data.collections.new("unlined")
    bpy.context.scene.collection.children.link(unlined)
    for obj in parts["hair"] + parts["ink"]:
        for home in obj.users_collection:
            home.objects.unlink(obj)
        unlined.objects.link(obj)
    return human, rig, parts, mats


def marked(human, bones: tuple[str, ...]) -> None:
    """Marks the faces of the head and hands, which draw only their outer edge: the face's and
    fingers' every fold would otherwise get a line."""
    groups = {
        g.index
        for g in human.vertex_groups
        if g.name.removesuffix("_l").removesuffix("_r").split("_0")[0] in bones
    }
    heavy = set()
    for v in human.data.vertices:
        if sum(g.weight for g in v.groups if g.group in groups) > 0.5:
            heavy.add(v.index)
    mesh = human.data
    marks = mesh.attributes.get("freestyle_face") or mesh.attributes.new(
        "freestyle_face", "BOOLEAN", "FACE"
    )
    marks.data.foreach_set("value", [all(i in heavy for i in p.vertices) for p in mesh.polygons])


def proportioned(rig, scales: dict) -> None:
    """Klei-like proportions: the head grown, and the legs, body, neck and arms shortened along
    their length, each bone by its own amount."""
    for bone in rig.data.bones:
        bone.inherit_scale = "NONE"
    for pb in rig.pose.bones:
        name = pb.name.removesuffix("_l").removesuffix("_r")
        if name == "head":
            pb.scale = (scales["head"],) * 3
        elif name in ("thigh", "calf"):
            pb.scale = (1.0, scales["legs"], 1.0)
        elif name.startswith("spine"):
            pb.scale = (1.0, scales["body"], 1.0)
        elif name == "neck_01":
            pb.scale = (1.0, scales["neck"], 1.0)
        elif name in ("upperarm", "lowerarm"):
            pb.scale = (1.0, scales["arms"], 1.0)


def hang(rig, bone: str, outward: float = 8.0) -> Quaternion:
    """The turn that takes an arm bone from MakeHuman's rest pose to hanging at the side."""
    b = rig.data.bones[bone]
    rest = (b.tail_local - b.head_local).normalized()
    side = 1.0 if rest.x > 0 else -1.0
    down = Vector((side * math.sin(math.radians(outward)), 0.0, -math.cos(math.radians(outward))))
    return rest.rotation_difference(down)


def pose(rig, angles: dict) -> None:
    """Sets every bone from the 2D rig's angles, each a turn about `LATERAL` from straight down
    for limbs and straight up for the body, as `rig.ts` measures them."""
    turn = {}
    torso = -angles["lean"]
    for b in ("pelvis",):
        turn[b] = Quaternion()
    for b in ("spine_01", "spine_02", "spine_03", "neck_01", "clavicle_l", "clavicle_r"):
        turn[b] = Quaternion(LATERAL, math.radians(torso))
    turn["head"] = Quaternion(LATERAL, math.radians(torso - angles["nod"]))
    for i, side in enumerate((NEAR, FAR)):
        thigh = angles["thigh"][i]
        shin = thigh - angles["knee"][i]
        foot = shin + angles["foot"][i]
        turn[f"thigh{side}"] = Quaternion(LATERAL, math.radians(thigh))
        turn[f"calf{side}"] = Quaternion(LATERAL, math.radians(shin))
        turn[f"foot{side}"] = Quaternion(LATERAL, math.radians(foot))
        turn[f"ball{side}"] = turn[f"foot{side}"]
        upper = torso + angles["shoulder"][i]
        lower = upper + angles["elbow"][i]
        for bone, angle in (("upperarm", upper), ("lowerarm", lower), ("hand", lower)):
            name = f"{bone}{side}"
            turn[name] = Quaternion(LATERAL, math.radians(angle)) @ hang(rig, name)
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = Quaternion()
    for name, absolute in turn.items():
        pb = rig.pose.bones[name]
        parent = pb.parent
        while parent is not None and parent.name not in turn:
            parent = parent.parent
        relative = turn[parent.name].inverted() @ absolute if parent is not None else absolute
        rest = pb.bone.matrix_local.to_quaternion()
        pb.rotation_quaternion = rest.inverted() @ relative @ rest
    for pb in rig.pose.bones:
        if (
            pb.name not in turn
            and pb.parent is not None
            and any(k in pb.name for k in ("thumb", "index", "middle", "ring", "pinky"))
        ):
            pb.rotation_quaternion = Quaternion()


def lowest(objects) -> float:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    low = math.inf
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        world = evaluated.matrix_world
        for v in mesh.vertices:
            low = min(low, (world @ v.co).z)
        evaluated.to_mesh_clear()
    return low


def camera(view: str, height: float, size: tuple[int, int], ppm: float):
    """An orthographic camera `ppm` pixels a metre: from the character's right side for a side
    view, so it faces right, or from the front or back."""
    cam = bpy.data.objects.get("camera")
    if cam is None:
        cam = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
        bpy.context.scene.collection.objects.link(cam)
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = max(size) / ppm
    centre_z = size[1] / ppm / 2 - 0.12
    if view == "side":
        cam.location = (-10.0, 0.0, centre_z)
        cam.rotation_euler = (math.pi / 2, 0.0, -math.pi / 2)
    elif view == "front":
        cam.location = (0.0, -10.0, centre_z)
        cam.rotation_euler = (math.pi / 2, 0.0, 0.0)
    else:
        cam.location = (0.0, 10.0, centre_z)
        cam.rotation_euler = (math.pi / 2, 0.0, math.pi)
    bpy.context.scene.camera = cam
    return cam


def lights(view: str) -> None:
    for obj in [o for o in bpy.data.objects if o.type == "LIGHT"]:
        bpy.data.objects.remove(obj)
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3.0
    bpy.context.scene.collection.objects.link(sun)
    toward = {"side": -math.pi / 2, "front": 0.0, "back": math.pi}[view]
    sun.rotation_euler = (math.radians(50), 0.0, toward + math.radians(30))


def outline(scene, width: float) -> None:
    """Freestyle lines in the scratchy ink of #329's dolls: every silhouette and hem of the body,
    clothes and accessories, and only the outer edge of the hair, face and hands, whose every
    strand, fold and finger would otherwise get a line."""
    scene.render.use_freestyle = True
    scene.render.line_thickness_mode = "ABSOLUTE"
    layer = bpy.context.view_layer
    layer.use_freestyle = True
    settings = layer.freestyle_settings
    settings.crease_angle = math.radians(120)
    unlined = bpy.data.collections["unlined"]
    if len(settings.linesets) != 2:
        for lineset in list(settings.linesets):
            settings.linesets.remove(lineset)
        body = settings.linesets.new("body")
        body.select_by_collection = True
        body.collection = unlined
        body.collection_negation = "EXCLUSIVE"
        body.select_by_face_marks = True
        body.face_mark_negation = "EXCLUSIVE"
        body.face_mark_condition = "ONE"
        body.select_silhouette = True
        body.select_border = True
        body.select_crease = False
        body.select_external_contour = True
        hair = settings.linesets.new("hair")
        hair.select_silhouette = False
        hair.select_border = False
        hair.select_crease = False
        hair.select_external_contour = True
        style = bpy.data.linestyles.new("ink")
        style.color = srgb(INK)[:3]
        style.thickness = width
        style.thickness_position = "CENTER"
        noise = style.thickness_modifiers.new("scratch", "NOISE")
        noise.amplitude = width * 0.45
        noise.period = 24
        wobble = style.geometry_modifiers.new("wobble", "PERLIN_NOISE_1D")
        wobble.amplitude = width * 0.12
        wobble.frequency = 10
        for lineset in (body, hair):
            lineset.select_by_visibility = True
            lineset.select_by_edge_types = True
            lineset.linestyle = style


def render(path: Path, size: tuple[int, int], flat_pass: bool, parts, mats, line: float) -> float:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.view_settings.view_transform = "Standard"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    if flat_pass:
        scene.render.use_freestyle = False
        scene.render.filter_size = 0.0
        for region, objects in parts.items():
            for obj in objects:
                obj.data.materials[0] = flat(mats[region]["flat"])
    else:
        scene.render.filter_size = 1.5
        outline(scene, line)
        for region, objects in parts.items():
            for obj in objects:
                obj.data.materials[0] = mats[region]
    scene.render.filepath = str(path)
    start = time.perf_counter()
    bpy.ops.render.render(write_still=True)
    return time.perf_counter() - start


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1 :]
    spec = json.loads(Path(args[0]).read_text())
    if spec.get("grime"):
        spec["grime"] = str((Path(args[0]).parent / spec["grime"]).resolve())
    folder = Path(args[1])
    folder.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    human, rig, parts, mats = build(spec)
    built = time.perf_counter() - start
    meshes = [human, *parts.get("shoe", [])]
    size, ppm = tuple(spec["size"]), spec["ppm"]
    timings = {"build": round(built, 2), "frames": {}}
    standing = None
    for frame in spec["frames"]:
        t0 = time.perf_counter()
        pose(rig, frame["angles"])
        rig.location = (0.0, 0.0, 0.0)
        bpy.context.view_layer.update()
        if frame.get("plant", True):
            rig.location.z = -lowest(meshes) + frame.get("air", 0.0)
        else:
            if standing is None:
                pose(rig, spec["stand"])
                bpy.context.view_layer.update()
                standing = -lowest(meshes)
                pose(rig, frame["angles"])
            rig.location.z = standing + frame.get("rise", 0.0)
        bpy.context.view_layer.update()
        camera(frame["view"], 2.0, size, ppm)
        lights(frame["view"])
        name = frame["name"]
        toon_s = render(folder / f"{name}.png", size, False, parts, mats, spec["line"])
        flat_s = render(folder / f"{name}-flat.png", size, True, parts, mats, spec["line"])
        timings["frames"][name] = {
            "pose": round(time.perf_counter() - t0 - toon_s - flat_s, 2),
            "toon": round(toon_s, 2),
            "flat": round(flat_s, 2),
        }
        print(name, timings["frames"][name], flush=True)
    if spec.get("save_blend"):
        bpy.ops.wm.save_as_mainfile(filepath=str(folder / "model.blend"))
    (folder / "timings.json").write_text(json.dumps(timings, indent=1))


main()
