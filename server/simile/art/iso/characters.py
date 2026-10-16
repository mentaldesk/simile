"""`simile art iso characters`: each resident's walk and idle sheet, neutrally lit, and the
per-set constants that light them at runtime."""

import hashlib
import json
import math
import shutil
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from simile.art import palette
from simile.art.build import load_npcs
from simile.art.characters import PLAYER, Colours
from simile.art.iso import blender, camera, formats
from simile.art.iso.lighting import LOOK, NEUTRAL, SETS, shadow_direction
from simile.schema import Appearance
from simile.world.map import WALKING_SPEED

PIPELINE_VERSION = 1
CONTENT_DIR = Path(__file__).resolve().parents[4] / "content"
SIMILE = Path(__file__).resolve().parents[2]
SOURCES = (
    "art/palette.py",
    "art/iso/camera.py",
    "art/iso/formats.py",
    "art/iso/lighting.py",
    "art/iso/characters.py",
    "art/iso/in_blender/common.py",
    "art/iso/in_blender/character.py",
    "art/iso/in_blender/render_characters.py",
)
MANIFEST = "characters.json"
MANIFEST_FORMAT = 1

DIRECTIONS = {"s": 0, "se": 45, "e": 90, "ne": 135, "n": 180, "nw": 225, "w": 270, "sw": 315}
WALK_FRAMES = 8
IDLE_FRAMES = 4
IDLE_FPS = 3
STRIDE_DEG = 24.0
LEG_M = 0.87
FEET_REACH_M = 0.55
HEAD_REACH_M = 0.2
HEIGHT_M = 1.9
PAD_PX = 2
FIGURE_M = 1.8
PROBE = "player"

Renderer = Callable[[dict[str, Any], Path], dict[str, Any]]


class ClippedError(RuntimeError):
    pass


def blender_renderer(job: dict[str, Any], work: Path) -> dict[str, Any]:
    return blender.run("render_characters.py", job, work, progress=lambda line: print(f"  {line}"))


def digest(data: Any) -> str:
    text = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def sources_digest() -> str:
    """A digest of the code that decides how the sheets look, which tests pin."""
    h = hashlib.sha256()
    for name in SOURCES:
        h.update(name.encode() + b"\0" + (SIMILE / name).read_bytes())
    return h.hexdigest()[:16]


def frame() -> dict[str, Any]:
    """One frame's size and the feet within it, holding a figure HEIGHT_M tall whose feet reach
    FEET_REACH_M from where it stands, and its head HEAD_REACH_M."""
    feet = FEET_REACH_M * camera.PX_PER_M
    squash = math.sin(math.radians(camera.ELEVATION))
    half = math.ceil(feet) + PAD_PX
    head = HEAD_REACH_M * camera.PX_PER_M * squash
    ground = math.ceil(HEIGHT_M * camera.UPRIGHT_PX_PER_M + head) + PAD_PX
    return {
        "width": 2 * half,
        "height": ground + math.ceil(feet * squash) + PAD_PX,
        "anchor": [half, ground],
    }


def animations() -> dict[str, dict[str, Any]]:
    return {
        "walk": {"frames": WALK_FRAMES, "stride": STRIDE_DEG, "leg": LEG_M},
        "idle": {"frames": IDLE_FRAMES},
    }


def tiles_per_cycle() -> float:
    """How far a resident walks in one walk cycle: two steps, each the feet's swing apart."""
    return 4 * LEG_M * math.sin(math.radians(STRIDE_DEG)) / camera.TILE_M


def columns() -> int:
    return WALK_FRAMES + IDLE_FRAMES


@dataclass(frozen=True)
class Character:
    id: str
    appearance: Appearance
    seed: str | None

    def spec(self) -> dict[str, Any]:
        return {
            "key": self.id,
            "appearance": self.appearance.model_dump(mode="json"),
            "colours": asdict(Colours.of(self.appearance, self.seed)),
        }


def residents(content: Path) -> dict[str, Character]:
    """The player, then every resident in content/npcs/, by id."""
    out = {"player": Character("player", PLAYER, None)}
    for npc_id, appearance in load_npcs(content / "npcs").items():
        out[npc_id] = Character(npc_id, appearance, npc_id)
    return out


def base() -> dict[str, Any]:
    return {
        "pipeline": PIPELINE_VERSION,
        "look": LOOK,
        "neutral": NEUTRAL.params(),
        "camera": [camera.TILE_W, camera.TILE_H, camera.TILE_M, camera.ELEVATION],
        "palette": palette.PALETTE,
        "directions": DIRECTIONS,
    }


def character_hash(character: Character) -> str:
    sheet = {"frame": frame(), "animations": animations(), "format": asdict(formats.CHARACTERS)}
    return digest({**base(), **sheet, "character": character.spec()})


def constants_hash(probe: Character) -> str:
    return digest(
        {
            **base(),
            "sets": [s.params() for s in SETS.values()],
            "probe": probe.spec(),
            "probe_rect": probe_rect(),
            "figure": FIGURE_M,
        }
    )


def probe_rect() -> list[int]:
    """Screen px that hold a standing figure and its shadow under every set's sun."""
    points = []
    for i in range(32):
        a = math.tau * i / 32
        for z in (0.0, HEIGHT_M):
            points.append((FEET_REACH_M * math.cos(a), FEET_REACH_M * math.sin(a), z))
    shadows = []
    for light in SETS.values():
        dx, dy = shadow_direction(light.azimuth)
        reach = HEIGHT_M / math.tan(math.radians(light.elevation)) * 1.15
        shadows += [(x + dx * reach, y - dy * reach, 0.0) for x, y, z in points if z]
    xs, ys = zip(*(camera.screen(p) for p in points + shadows), strict=True)
    x0, y0 = math.floor(min(xs)) - PAD_PX, math.floor(min(ys)) - PAD_PX
    return [x0, y0, math.ceil(max(xs)) + PAD_PX - x0, math.ceil(max(ys)) + PAD_PX - y0]


def shadow(azimuth: float, elevation: float) -> dict[str, Any]:
    """Where a standing figure's drop shadow falls: a unit step in tiles, its length and its tip."""
    dx, dy = shadow_direction(azimuth)
    length = FIGURE_M / math.tan(math.radians(elevation)) / camera.TILE_M
    tip = camera.project(dx * length, dy * length)
    return {
        "direction": [round(dx, 4), round(dy, 4)],
        "length": round(length, 3),
        "tip": [round(tip[0], 1), round(tip[1], 1)],
    }


def measure(neutral: list[np.ndarray], lit: list[np.ndarray]) -> tuple[list[float], float]:
    """A set's tint and shadow strength: the probe under its light against the neutral render."""
    lit_sum, neutral_sum, shade = np.zeros(3), np.zeros(3), []
    for n, b in zip(neutral, lit, strict=True):
        n, b = n.astype(np.float64), b.astype(np.float64)
        solid = (n[..., 3] > 250) & (b[..., 3] > 250)
        lit_sum += b[solid][:, :3].sum(axis=0)
        neutral_sum += n[solid][:, :3].sum(axis=0)
        near = _dilate(n[..., 3] > 0, 4)
        alpha = b[..., 3][~near] / 255
        shade += list(alpha[alpha > 0.03])
    ratio = lit_sum / neutral_sum
    tint = [round(float(c), 3) for c in ratio / max(ratio.max(), 1.0)]
    return tint, round(float(np.percentile(shade, 95)), 3) if shade else 0.0


def _dilate(mask: np.ndarray, r: int) -> np.ndarray:
    out = np.pad(mask, r)
    for axis in (0, 1):
        grown = out.copy()
        for k in range(1, r + 1):
            grown |= np.roll(out, k, axis) | np.roll(out, -k, axis)
        out = grown
    return out[r:-r, r:-r]


def _write(path: Path, data: bytes) -> bool:
    if path.exists() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def _rgba(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGBA"))


@dataclass
class Report:
    rendered: list[str] = field(default_factory=list)
    written: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    probed: bool = False
    seconds: dict[str, float] = field(default_factory=dict)
    bytes: dict[str, int] = field(default_factory=dict)


class Build:
    def __init__(self, content: Path, work: Path, force: bool) -> None:
        self.root = content / "art" / "iso" / "characters"
        self.work, self.force = work, force
        self.characters = residents(content)
        self.hashes = {key: character_hash(c) for key, c in self.characters.items()}
        self.constants_hash = constants_hash(self.characters[PROBE])
        self.old = self._old_manifest()
        self.report = Report()

    def _old_manifest(self) -> dict[str, Any]:
        try:
            return json.loads((self.root / MANIFEST).read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def stale(self) -> list[str]:
        old = self.old.get("characters", {})
        return [
            key
            for key, h in self.hashes.items()
            if self.force
            or old.get(key, {}).get("hash") != h
            or not (self.root / old[key]["image"]).exists()
        ]

    def constants_stale(self) -> bool:
        return self.force or self.old.get("constants_hash") != self.constants_hash

    def job(self, keys: list[str], probe: bool) -> dict[str, Any]:
        job: dict[str, Any] = {
            "look": LOOK,
            "light": NEUTRAL.params(),
            "frame": frame(),
            "directions": DIRECTIONS,
            "animations": animations(),
            "characters": [self.characters[key].spec() for key in keys],
        }
        if probe:
            job["probe"] = {
                "character": self.characters[PROBE].spec(),
                "rect": probe_rect(),
                "sets": [s.params() for s in SETS.values()],
            }
        return job

    def run(self, render: Renderer) -> Report:
        keys, probe = self.stale(), self.constants_stale()
        if keys or probe:
            start = time.time()
            result = render(self.job(keys, probe), self.work)
            self.report.seconds = {"wall": time.time() - start}
            self.report.seconds |= {k: v["seconds"] for k, v in result["characters"].items()}
            self.report.rendered, self.report.probed = keys, probe
        manifest = {
            "format": MANIFEST_FORMAT,
            "frame": frame(),
            "columns": columns(),
            "directions": [
                {"name": name, "row": row, "vector": self._vector(degrees)}
                for row, (name, degrees) in enumerate(DIRECTIONS.items())
            ],
            "animations": self._animations(),
            "figure_m": FIGURE_M,
            "constants_hash": self.constants_hash,
            "sets": self._sets(probe),
            "characters": {key: self._sheet(key, key in keys) for key in self.characters},
        }
        text = json.dumps(manifest, indent=1) + "\n"
        if _write(self.root / MANIFEST, text.encode()):
            self.report.written.append(MANIFEST)
        self._remove_unused(manifest)
        for key, sheet in manifest["characters"].items():
            self.report.bytes[key] = (self.root / sheet["image"]).stat().st_size
        self.report.bytes[MANIFEST] = (self.root / MANIFEST).stat().st_size
        return self.report

    @staticmethod
    def _vector(degrees: float) -> list[int]:
        a = math.radians(degrees)
        return [round(math.sin(a)), round(math.cos(a))]

    def _animations(self) -> dict[str, Any]:
        cols, walk = columns(), range(WALK_FRAMES)
        idle = range(WALK_FRAMES, WALK_FRAMES + IDLE_FRAMES)
        return {
            "walk": {
                "fps": round(WALK_FRAMES * WALKING_SPEED / tiles_per_cycle()),
                "tiles_per_cycle": round(tiles_per_cycle(), 3),
                "frames": {d: [r * cols + c for c in walk] for r, d in enumerate(DIRECTIONS)},
            },
            "idle": {
                "fps": IDLE_FPS,
                "frames": {d: [r * cols + c for c in idle] for r, d in enumerate(DIRECTIONS)},
            },
        }

    def _sets(self, probed: bool) -> dict[str, Any]:
        if not probed:
            return self.old["sets"]
        folder = self.work / "probe"
        neutral = [_rgba(folder / NEUTRAL.name / f"{d}.png") for d in DIRECTIONS]
        out = {}
        for name, light in SETS.items():
            lit = [_rgba(folder / name / f"{d}.png") for d in DIRECTIONS]
            tint, strength = measure(neutral, lit)
            out[name] = {
                "sun": {"azimuth": light.azimuth, "elevation": light.elevation},
                "tint": tint,
                "shadow": {"strength": strength, **shadow(light.azimuth, light.elevation)},
            }
        return out

    def _sheet(self, key: str, rendered: bool) -> dict[str, Any]:
        if not rendered:
            return self.old["characters"][key]
        f, cols = frame(), columns()
        w, h = f["width"], f["height"]
        sheet = Image.new("RGBA", (cols * w, len(DIRECTIONS) * h))
        for row in range(len(DIRECTIONS)):
            for col in range(cols):
                path = self.work / key / f"{row}-{col}.png"
                with Image.open(path) as raw:
                    image = raw.convert("RGBA")
                if _touches_edge(image):
                    raise ClippedError(f"{key} reaches the edge of {path.name}: enlarge frame()")
                sheet.paste(image, (col * w, row * h))
        name = f"{key}.{formats.CHARACTERS.ext}"
        if _write(self.root / name, formats.CHARACTERS.encode(sheet)):
            self.report.written.append(name)
        return {
            "image": name,
            "width": sheet.width,
            "height": sheet.height,
            "hash": self.hashes[key],
        }

    def _remove_unused(self, manifest: dict[str, Any]) -> None:
        used = {MANIFEST} | {s["image"] for s in manifest["characters"].values()}
        for path in sorted(self.root.iterdir()):
            if path.is_file() and path.name not in used:
                path.unlink()
                self.report.removed.append(path.name)


def _touches_edge(image: Image.Image) -> bool:
    alpha = np.asarray(image.getchannel("A"))
    return bool(alpha[0].any() or alpha[-1].any() or alpha[:, 0].any() or alpha[:, -1].any())


def build(
    content: Path = CONTENT_DIR,
    work: Path | None = None,
    force: bool = False,
    render: Renderer | None = None,
) -> Report:
    """Render the sheets that changed, and the per-set constants if the light changed."""
    scratch = None if work else Path(tempfile.mkdtemp(prefix="simile-iso-characters-"))
    try:
        return Build(content, work or scratch, force).run(render or blender_renderer)
    finally:
        if scratch:
            shutil.rmtree(scratch, ignore_errors=True)
