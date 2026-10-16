"""`simile art iso scenery`: each lighting set's ground, object sprites, light map and manifest."""

import hashlib
import json
import shutil
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from simile.art.iso import blender, camera, depth, formats, post
from simile.art.iso.lighting import CROSSFADE_MINUTES, LOOK, SETS, LightingSet
from simile.art.iso.town import Building, Object, Town

PIPELINE_VERSION = 1
CONTENT_DIR = Path(__file__).resolve().parents[4] / "content"
MANIFEST_FORMAT = 1
LIGHT_MAP_PX = 8
MARGIN_PX = 24

Renderer = Callable[[dict[str, Any], Path], dict[str, Any]]


def blender_renderer(job: dict[str, Any], work: Path) -> dict[str, Any]:
    return blender.run("render_scenery.py", job, work, progress=lambda line: print(f"  {line}"))


def digest(data: Any) -> str:
    text = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def ground_rect(town: Town) -> tuple[int, int, int, int]:
    x0 = -town.height * camera.TILE_W // 2 - MARGIN_PX
    x1 = town.width * camera.TILE_W // 2 + MARGIN_PX
    y1 = (town.width + town.height) * camera.TILE_H // 2 + MARGIN_PX
    return x0, -MARGIN_PX, x1 - x0, y1 + MARGIN_PX


@dataclass
class SpriteTask:
    obj: Object
    context: list[dict[str, Any]]
    hash: str

    @property
    def key(self) -> str:
        return self.obj.id

    def job(self) -> dict[str, Any]:
        x0, y0, x1, y1 = self.obj.footprint
        return {
            "key": self.key,
            "target": self.obj.spec(),
            "context": self.context,
            "centre": [(x0 + x1) / 2, (y0 + y1) / 2],
        }


@dataclass
class Plan:
    light: LightingSet
    town: Town
    sprites: dict[str, SpriteTask] = field(default_factory=dict)
    ground_hash: str = ""
    light_map_hash: str = ""


def plan(town: Town, light: LightingSet) -> Plan:
    """What one set's renders depend on, and so each one's hash."""
    base = {
        "pipeline": PIPELINE_VERSION,
        "look": LOOK,
        "light": light.params(),
        "camera": [camera.TILE_W, camera.TILE_H, camera.TILE_M, camera.ELEVATION],
    }
    out = Plan(light, town)
    for obj in town.objects:
        context = [o.spec() for o in town.context(obj, light)]
        inputs = {"format": formats.SPRITES.name, "target": obj.spec(), "context": context}
        out.sprites[obj.id] = SpriteTask(obj, context, digest({**base, **inputs}))
    scene = {
        **base,
        "ground": town.ground(),
        "objects": [o.spec() for o in town.objects],
    }
    out.ground_hash = digest({**scene, "rect": ground_rect(town), "format": formats.GROUND.name})
    light_map = {"light_map": LIGHT_MAP_PX, "format": formats.LIGHT_MAP.name}
    out.light_map_hash = digest({**scene, **light_map})
    return out


def _write(path: Path, data: bytes) -> bool:
    if path.exists() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


@dataclass
class Report:
    name: str
    rendered: list[str] = field(default_factory=list)
    written: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    seconds: dict[str, float] = field(default_factory=dict)
    bytes: int = 0


class SetBuild:
    def __init__(self, plan: Plan, root: Path, work: Path, force: bool) -> None:
        self.plan, self.root, self.work, self.force = plan, root, work, force
        self.name = plan.light.name
        self.folder = root / self.name
        self.manifest_path = root / f"{self.name}.json"
        self.old = self._old_manifest()
        self.report = Report(self.name)

    def _old_manifest(self) -> dict[str, Any]:
        try:
            return json.loads(self.manifest_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _have(self, image: str) -> bool:
        return (self.root / image).exists()

    def stale_sprites(self) -> list[SpriteTask]:
        old = {o["id"]: o for o in self.old.get("objects", [])}
        return [
            t
            for t in self.plan.sprites.values()
            if self.force
            or old.get(t.key, {}).get("hash") != t.hash
            or not self._have(old[t.key]["image"])
        ]

    def ground_stale(self) -> bool:
        old = self.old.get("ground", {})
        if self.force or old.get("hash") != self.plan.ground_hash:
            return True
        return not all(self._have(c["image"]) for c in old.get("chunks", []))

    def light_map_stale(self) -> bool:
        old = self.old.get("light_map", {})
        return (
            self.force
            or old.get("hash") != self.plan.light_map_hash
            or not self._have(old.get("image", "-"))
        )

    def job(self, sprites: list[SpriteTask], ground: bool, light_map: bool) -> dict[str, Any]:
        town = self.plan.town
        job: dict[str, Any] = {
            "look": LOOK,
            "light": self.plan.light.params(),
            "sprites": [t.job() for t in sprites],
        }
        if ground or light_map:
            job["town"] = {
                "width": town.width,
                "height": town.height,
                "ground": town.ground(),
                "buildings": [b.spec() for b in town.buildings],
                "props": [p.spec() for p in town.props],
            }
        if ground:
            job["ground"] = {"rect": list(ground_rect(town))}
        if light_map:
            job["lightmap"] = {"px_per_tile": LIGHT_MAP_PX}
        return job

    def run(self, render: Renderer) -> Report:
        sprites = self.stale_sprites()
        ground, light_map = self.ground_stale(), self.light_map_stale()
        rendered: dict[str, Any] = {"sprites": {}}
        if sprites or ground or light_map:
            work = self.work / self.name
            start = time.time()
            rendered = render(self.job(sprites, ground, light_map), work)
            self.report.seconds = {**rendered.get("seconds", {}), "wall": time.time() - start}
            self.report.rendered = [
                *(["ground"] if ground else []),
                *(["light map"] if light_map else []),
                *(t.key for t in sprites),
            ]
        manifest = {
            "format": MANIFEST_FORMAT,
            "set": self.name,
            "hours": list(self.plan.light.hours),
            "crossfade_minutes": CROSSFADE_MINUTES,
            "sun": {"azimuth": self.plan.light.azimuth, "elevation": self.plan.light.elevation},
            "tile": {"width": camera.TILE_W, "height": camera.TILE_H, "metres": camera.TILE_M},
            "map": {"width": self.plan.town.width, "height": self.plan.town.height},
            "ground": self._ground(ground),
            "light_map": self._light_map(light_map),
            "objects": self._objects(rendered["sprites"]),
        }
        text = json.dumps(manifest, indent=1) + "\n"
        if _write(self.manifest_path, text.encode()):
            self.report.written.append(self.manifest_path.name)
        self._remove_unused(manifest)
        self.report.bytes = sum(p.stat().st_size for p in self.folder.rglob("*") if p.is_file())
        self.report.bytes += self.manifest_path.stat().st_size
        return self.report

    def _save(self, name: str, data: bytes) -> str:
        image = f"{self.name}/{name}"
        if _write(self.root / image, data):
            self.report.written.append(image)
        return image

    def _ground(self, rendered: bool) -> dict[str, Any]:
        if not rendered:
            return self.old["ground"]
        x0, y0, w, h = ground_rect(self.plan.town)
        with Image.open(self.work / self.name / "ground.png") as raw:
            image = post.glow(raw.convert("RGBA"), LOOK["glow_radius"], self._glow())
        pieces = []
        for col, row, cx, cy, cw, ch in post.chunks(w, h):
            piece = image.crop((cx, cy, cx + cw, cy + ch))
            name = f"ground-{col}-{row}.{formats.GROUND.ext}"
            pieces.append(
                {
                    "image": self._save(name, formats.GROUND.encode(piece)),
                    "x": x0 + cx,
                    "y": y0 + cy,
                    "width": cw,
                    "height": ch,
                }
            )
        return {
            "x": x0,
            "y": y0,
            "width": w,
            "height": h,
            "hash": self.plan.ground_hash,
            "chunks": pieces,
        }

    def _glow(self) -> float:
        return LOOK["glow_strength"] * self.plan.light.glow

    def _light_map(self, rendered: bool) -> dict[str, Any]:
        if not rendered:
            return self.old["light_map"]
        work = self.work / self.name
        passes = [np.load(work / f"light_{p}.npy") for p in ("sunsky", "sun", "lights")]
        image, scale = post.light_map(*passes, self.plan.light.elevation, LIGHT_MAP_PX)
        return {
            "image": self._save(f"light.{formats.LIGHT_MAP.ext}", formats.LIGHT_MAP.encode(image)),
            "px_per_tile": LIGHT_MAP_PX,
            "width": image.width,
            "height": image.height,
            "scale": scale,
            "hash": self.plan.light_map_hash,
        }

    def _objects(self, rendered: dict[str, Any]) -> list[dict[str, Any]]:
        old = {o["id"]: o for o in self.old.get("objects", [])}
        out = []
        for key, task in self.plan.sprites.items():
            obj = task.obj
            ax, ay = camera.project(*obj.anchor)
            if key in rendered:
                x0, y0, w, h = rendered[key]["rect"]
                with Image.open(self.work / self.name / "sprites" / f"{key}.png") as raw:
                    image = post.glow(raw.convert("RGBA"), LOOK["glow_radius"], self._glow())
                encoded = formats.SPRITES.encode(image)
                sprite = {
                    "image": self._save(f"{key}.{formats.SPRITES.ext}", encoded),
                    "width": w,
                    "height": h,
                    "offset": [x0 - round(ax), y0 - round(ay)],
                    "hash": task.hash,
                }
            else:
                sprite = {k: old[key][k] for k in ("image", "width", "height", "offset", "hash")}
            left = round(ax) + sprite["offset"][0]
            out.append(
                {
                    "id": obj.id,
                    "kind": "building" if isinstance(obj, Building) else obj.kind,
                    "anchor": list(obj.anchor),
                    "footprint": list(obj.footprint),
                    **sprite,
                    "slices": depth.slices(obj.footprint, left, sprite["width"]),
                }
            )
        return out

    def _remove_unused(self, manifest: dict[str, Any]) -> None:
        used = {o["image"] for o in manifest["objects"]}
        used |= {c["image"] for c in manifest["ground"]["chunks"]}
        used.add(manifest["light_map"]["image"])
        for path in sorted(self.folder.glob("*")):
            if path.is_file() and f"{self.name}/{path.name}" not in used:
                path.unlink()
                self.report.removed.append(f"{self.name}/{path.name}")


def build(
    content: Path = CONTENT_DIR,
    sets: list[str] | None = None,
    work: Path | None = None,
    force: bool = False,
    render: Renderer | None = None,
) -> list[Report]:
    """Render what changed in each set and rewrite its manifest; unchanged files are left alone."""
    town = Town(content / "map" / "village.tmj")
    root = content / "art" / "iso" / "scenery"
    scratch = None if work else Path(tempfile.mkdtemp(prefix="simile-iso-"))
    reports = []
    try:
        for name in sets or list(SETS):
            build_set = SetBuild(plan(town, SETS[name]), root, work or scratch, force)
            reports.append(build_set.run(render or blender_renderer))
    finally:
        if scratch:
            shutil.rmtree(scratch, ignore_errors=True)
    return reports
