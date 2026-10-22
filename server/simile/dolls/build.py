"""Paints the residents' and the player's figures into `content/dolls/`, repainting only those
whose `Appearance` or pipeline changed."""

import hashlib
import json
import time
import zlib
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager, ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from simile.dolls.figure import (
    EDITS,
    POSES,
    SIZE,
    STANDING,
    Pose,
    edit_prompt,
    legs_guide,
    stand_prompt,
)
from simile.dolls.flux import Painter
from simile.dolls.measure import (
    CLOSE,
    MARKS,
    STRAYS,
    Swatch,
    face_marks,
    follow,
    hidden,
    identify,
    kept,
    matched,
    pulled,
    strays,
    swatches,
    worst,
)
from simile.dolls.sprites import VERSION, atlas, cut_out, frames, manifest, scale, seat
from simile.dolls.words import gender_in, persona
from simile.schema import PLAYER_ID, Appearance

REPO = Path(__file__).resolve().parents[3]
CONTENT = REPO / "content" / "dolls"
PAINTINGS = REPO / "server" / "data" / "dolls" / "paintings"
"""Every painting as FLUX returned it, by what it was painted from, so cutting and matching can
be retuned without painting again. Ignored by git."""
TRIES = {"stand": 3, "edit": 2}
"""How many times a painting is made, at most, while its colours can't be matched."""
SCALE = 1.25
"""How much bigger or smaller than the standing figure FLUX may draw another pose before it's
painted again."""
WRONG = 20.0
"""A colour painted further than this from the `Appearance`, CIEDE2000, is another colour, not a
shade of it: rather than pulled back, the painting is made again."""
REROLLS: dict[str, int] = {}
"""`<id>/<frame>` to a reroll number, for a painting that came out off-model by eye."""
MISSES: dict[tuple[str, str, str], str] = {
    ("henrietta", "climb", "shoe"): "ΔE 7.8: near-black shoes, seen from behind, among the outline",
    ("raymond", "run_pass", "shoe"): "ΔE 6.1: near-black shoes, mid-stride, among the outline",
}
"""(id, frame, colour) still over `CLOSE` from the `Appearance` once matched, and why."""

Cut = Callable[[Image.Image], Image.Image]


def people() -> dict[str, Appearance]:
    """Every resident in `content/npcs/` and the player, by id."""
    from simile.characters.palette import PLAYER
    from simile.npc.content import NPCS_DIR, load_npcs

    return {npc.id: npc.appearance for npc in load_npcs(NPCS_DIR)} | {PLAYER_ID: PLAYER}


def personas() -> dict[str, str]:
    """Each resident's age, and whether a man or a woman, from their voice."""
    from simile.npc.content import NPCS_DIR, load_npcs

    return {
        npc.id: persona(npc.age, gender_in(npc.voice.description or ""))
        for npc in load_npcs(NPCS_DIR)
    }


def fingerprint(who: str, appearance: Appearance, said: str = "") -> str:
    """What a figure is painted from: a new one means it's painted again."""
    inputs = {
        "version": VERSION,
        "who": who,
        "appearance": appearance.model_dump(mode="json"),
        "persona": said,
        "rerolls": {k: v for k, v in REROLLS.items() if k.startswith(f"{who}/")},
    }
    return hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:16]


def seed(who: str, frame: str, reroll: int = 0) -> int:
    return zlib.crc32(f"{who}/{frame}/{reroll}".encode()) % 2**31


@dataclass
class Try:
    seed: int
    raw: dict[str, Swatch]
    matched: dict[str, Swatch]
    seconds: float | None
    marks: float = 0.0
    """The share of the face painted over: `measure.face_marks`."""
    scale: float = 1.0
    """How much bigger it's drawn than the standing figure: `sprites.scale`."""
    lost: list[str] = field(default_factory=list)
    """Colours of the standing figure it doesn't show as painted there: `measure.follow`."""
    strays: float = 0.0
    """The share of it in colours the standing figure hasn't got: `measure.strays`."""
    followed: bool = False
    """Matched as the standing figure was painted, so a colour painted far off is the standing
    figure's, already accepted, rather than another colour."""


@dataclass
class Painted:
    who: str
    colours: dict[str, Any] = field(default_factory=dict)
    """Each colour the standing figure shows, in CIELAB as FLUX painted it."""
    figures: dict[str, Image.Image] = field(default_factory=dict)
    paintings: dict[str, Image.Image] = field(default_factory=dict)
    tries: dict[str, list[Try]] = field(default_factory=dict)
    """Every painting of each frame, the one kept last."""

    @property
    def seconds(self) -> float:
        return sum(t.seconds or 0 for tries in self.tries.values() for t in tries)


class Cached:
    """Paints through `painter`, keeping each painting in `folder` by everything it was painted
    from, and loading the painter only for one that isn't there."""

    def __init__(
        self, painter: Callable[[], AbstractContextManager[Painter]], folder: Path | None
    ) -> None:
        self.factory, self.folder = painter, folder
        self.stack = ExitStack()
        self.model: Painter | None = None

    def paint(
        self, prompt: str, seed: int, images: list[Image.Image]
    ) -> tuple[Image.Image, float | None]:
        key = hashlib.sha256(prompt.encode() + str(seed).encode())
        for image in images:
            key.update(image.tobytes())
        path = None if self.folder is None else self.folder / f"{key.hexdigest()[:20]}.png"
        if path is not None and path.exists():
            return Image.open(path).convert("RGB"), None
        if self.model is None:
            self.model = self.stack.enter_context(self.factory())
        start = time.perf_counter()
        painting = self.model.paint(prompt, SIZE, seed, images)
        seconds = round(time.perf_counter() - start, 1)
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            painting.save(path)
        return painting, seconds


def attempt(
    painter: Cached,
    prompt: str,
    seed: int,
    images: list[Image.Image],
    appearance: Appearance,
    cut: Cut,
    pose: Pose,
    standing: Painted | None,
) -> tuple[Try, Image.Image, Image.Image]:
    """One painting cut out and its colours pulled back to the `Appearance`, following how the
    `standing` figure was painted, if this isn't it. With how far off they were before and after,
    how much of the face is painted over, how big it's drawn, which of the standing figure's
    colours it lost and how much of it is painted in others."""
    painting, seconds = painter.paint(prompt, seed, images)
    figure = cut(painting)
    raw = swatches(figure, appearance, pose.bands)
    if standing is None:
        fixed = pulled(figure, appearance, pose.bands)
        tried = Try(seed, raw, swatches(fixed, appearance, pose.bands), seconds)
    else:
        found = follow(figure, standing.colours, appearance, pose.bands)
        fixed = matched(figure, found, pose.bands)
        after = kept(figure, fixed, standing.colours, appearance, pose.bands)
        tried = Try(seed, raw, after, seconds, followed=True)
        tried.lost = sorted(set(standing.colours) - set(found))
        stand = standing.figures["stand"]
        tried.scale = round(scale(fixed, stand, pose.bands == "climb"), 3)
        tried.strays = strays(fixed, stand)
    if pose.face:
        tried.marks = round(face_marks(fixed, appearance), 3)
    return tried, painting, fixed


def misses(tried: Try, appearance: Appearance) -> tuple[bool, float, float, float]:
    """Sorts tries best first: matched within `CLOSE`, with nothing painted another colour, a
    clean face, drawn to scale and painted like the standing figure; then the least marked, off
    scale and unlike it; then the closest."""
    shown = hidden(appearance)
    after, before = worst(tried.matched, shown), worst(tried.raw, shown)
    off_scale = abs(np.log(tried.scale)) > np.log(SCALE)
    unlike = bool(tried.lost) or tried.strays > STRAYS
    wrong = before > WRONG and not tried.followed
    bad = after > CLOSE or wrong or tried.marks > MARKS or off_scale or unlike
    odd = tried.marks + abs(np.log(tried.scale)) + tried.strays + len(tried.lost)
    return bad, odd, after, before


def paint_frame(
    painter: Cached,
    painted: Painted,
    frame: str,
    prompt: str,
    images: list[Image.Image],
    appearance: Appearance,
    cut: Cut,
    pose: Pose,
    tries: int,
) -> None:
    """Paints `frame` until it matches, at most `tries` times, keeping the best."""
    first = REROLLS.get(f"{painted.who}/{frame}", 0)
    standing = painted if painted.figures.get("stand") else None
    made = []
    for n in range(first, first + tries):
        number = seed(painted.who, frame, n)
        made.append(attempt(painter, prompt, number, images, appearance, cut, pose, standing))
        if not misses(made[-1][0], appearance)[0]:
            break
    best = min(made, key=lambda m: misses(m[0], appearance))
    painted.tries[frame] = [m[0] for m in made if m is not best] + [best[0]]
    painted.paintings[frame], painted.figures[frame] = best[1], best[2]


def paint(
    who: str,
    appearance: Appearance,
    painter: Cached,
    said: str = "",
    cut: Cut = cut_out,
    log: Callable[[str], None] = print,
) -> Painted:
    """The standing figure from text, then every other pose as an edit of it: of the painting
    as FLUX painted it, so matching colours can be retuned without painting again."""
    painted = Painted(who)
    stand = stand_prompt(appearance, who, said)
    paint_frame(painter, painted, "stand", stand, [], appearance, cut, STANDING, TRIES["stand"])
    found = identify(cut(painted.paintings["stand"]), appearance)
    painted.colours = {name: got for name, (got, _) in found.items()}
    log(f"{who} stand: {summary(painted.tries['stand'][-1])}")
    for frame, pose in EDITS.items():
        figure = painted.figures[pose.base]
        image = painted.paintings[pose.base]
        if pose.legs:
            image = legs_guide(image, np.asarray(figure.getchannel("A")), appearance, pose.legs)
        prompt = edit_prompt(frame, appearance, who)
        paint_frame(painter, painted, frame, prompt, [image], appearance, cut, pose, TRIES["edit"])
        log(f"{who} {frame}: {summary(painted.tries[frame][-1])}")
    return painted


def summary(tried: Try) -> str:
    return ", ".join(f"{k} {s.delta_e:g}" for k, s in tried.matched.items())


def files(who: str, painted: Painted, **extra: Any) -> dict[str, bytes]:
    """The manifest and the atlas, by file name."""
    climbs = [f for f, pose in EDITS.items() if pose.bands == "climb"]
    lifted = {f: pose.lifted for f, pose in EDITS.items() if pose.lifted}
    seated = [f for f, pose in EDITS.items() if pose.seated]
    made = frames(painted.figures, hands_up=climbs, lifted=lifted, seated=seated)
    data, places = atlas(made)
    name = f"{who}.webp"
    body = manifest(made, places, POSES, name, id=who, **extra)
    return {name: data, f"{who}.json": (json.dumps(body, indent=2) + "\n").encode()}


def reseat(directory: Path = CONTENT) -> list[Path]:
    """Measures each figure's seats again from its atlas, without painting."""
    seated = [f for f, pose in EDITS.items() if pose.seated]
    named = {}
    for path in sorted(directory.glob("*.json")):
        body = json.loads(path.read_text())
        with Image.open(directory / body["painted"]) as painted:
            sheet = painted.convert("RGBA")
        for name in seated:
            entry = body["frames"][name]
            x, y, w, h = entry["frame"]
            at = seat(sheet.crop((x, y, x + w, y + h)), entry["feet"][0])
            entry["seat"] = [round(at[0], 1), round(at[1], 1)]
        named[path.name] = (json.dumps(body, indent=2) + "\n").encode()
    return write(directory, named)


def write(directory: Path, named: dict[str, bytes]) -> list[Path]:
    """Writes only the files whose bytes changed."""
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name, data in named.items():
        path = directory / name
        if not path.exists() or path.read_bytes() != data:
            path.write_bytes(data)
            written.append(path)
    return written


def current(directory: Path, who: str, hash: str) -> bool:
    path = directory / f"{who}.json"
    if not path.exists():
        return False
    found = json.loads(path.read_text())
    return found.get("hash") == hash and (directory / found.get("painted", "")).is_file()


def stale(directory: Path, keep: Iterable[str]) -> list[Path]:
    """Files in `directory` that belong to no one in `keep`: #310's atlases, or a resident's
    who's gone."""
    wanted = {name for who in keep for name in (f"{who}.json", f"{who}.webp")}
    return [
        p for p in directory.glob("*") if p.suffix in (".json", ".webp") and p.name not in wanted
    ]


def build(
    painter: Callable[[], AbstractContextManager[Painter]],
    directory: Path = CONTENT,
    only: Iterable[str] = (),
    force: bool = False,
    cache: Path | None = PAINTINGS,
    cut: Cut = cut_out,
    log: Callable[[str], None] = print,
) -> list[Painted]:
    """Paints each figure whose fingerprint changed, loading the painter only if a painting
    isn't in `cache`."""
    everyone = people()
    said = personas()
    wanted = list(only) or list(everyone)
    unknown = [who for who in wanted if who not in everyone]
    if unknown:
        raise KeyError(f"No resident or player called {', '.join(unknown)}")
    hashes = {who: fingerprint(who, everyone[who], said.get(who, "")) for who in wanted}
    todo = [who for who in wanted if force or not current(directory, who, hashes[who])]
    for who in set(wanted) - set(todo):
        log(f"{who}: up to date")
    done: list[Painted] = []
    model = Cached(painter, cache)
    with model.stack:
        for who in todo:
            painted = paint(who, everyone[who], model, said.get(who, ""), cut, log)
            appearance = everyone[who].model_dump(mode="json")
            changed = write(directory, files(who, painted, hash=hashes[who], appearance=appearance))
            log(f"{who}: painted in {painted.seconds:.0f} s of FLUX, wrote {len(changed)} files")
            done.append(painted)
    if not only:
        for path in stale(directory, everyone):
            path.unlink()
            log(f"removed {path.name}")
    return done
