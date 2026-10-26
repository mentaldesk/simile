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

from simile.dolls import bionics
from simile.dolls.bionics import COMBINATIONS, Combination, figure_id, layers
from simile.dolls.figure import (
    EDITS,
    FRAMES,
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
from simile.schema import PLAYER_ID, Appearance, Npc
from simile.schema.player import Bionic

REPO = Path(__file__).resolve().parents[3]
CONTENT = REPO / "content" / "dolls"
PAINTINGS = REPO / "server" / "data" / "dolls" / "paintings"
"""Every painting as FLUX returned it, by what it was painted from, so cutting and matching can
be retuned without painting again. Ignored by git."""
TRIES = {"stand": 3, "edit": 2, "fitted": 3}
"""How many times a painting is made, at most, while its colours can't be matched."""
SCALE = 1.25
"""How much bigger or smaller than the standing figure FLUX may draw another pose before it's
painted again."""
WRONG = 20.0
"""A colour painted further than this from the `Appearance`, CIEDE2000, is another colour, not a
shade of it: rather than pulled back, the painting is made again."""
REROLLS: dict[str, int] = {
    "player_datajack/stride": 1,
    "player_eye/stand": 3,
    "player_eye/pass": 2,
    "player_eye/sit": 8,
    "player_bionic_legs/climb": 1,
    "player_bionic_legs_feet/pass": 2,
}
"""`<id>/<frame>` to a reroll number, for a painting that came out off-model by eye."""
MISSES: dict[tuple[str, str, str], str] = {
    ("henrietta", "climb", "shoe"): "ΔE 7.8: near-black shoes, seen from behind, among the outline",
    ("raymond", "run_pass", "shoe"): "ΔE 6.1: near-black shoes, mid-stride, among the outline",
}
"""(id, frame, colour) still over `CLOSE` from the `Appearance` once matched, and why."""

Cut = Callable[[Image.Image], Image.Image]


def characters() -> list[Npc]:
    """Every resident in `content/npcs/`, and the clinic's doctor."""
    from simile.clinic.doctor import load_doctor
    from simile.npc.content import NPCS_DIR, load_npcs

    return [*load_npcs(NPCS_DIR), load_doctor()]


def outsiders() -> set[str]:
    """The characters who aren't residents, whose manifests say so: the clinic's doctor."""
    from simile.clinic.doctor import DOCTOR

    return {DOCTOR}


def people() -> dict[str, Appearance]:
    """Every character and the player, by id."""
    from simile.characters.palette import PLAYER

    return {npc.id: npc.appearance for npc in characters()} | {PLAYER_ID: PLAYER}


def personas() -> dict[str, str]:
    """Each character's age, and whether a man or a woman, from their voice."""
    return {
        npc.id: persona(npc.age, gender_in(npc.voice.description or "")) for npc in characters()
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


def fitted_fingerprint(combination: Combination, player: str, appearance: Appearance) -> str:
    """What the player with bionics is made from: the player's, its parts' prompts and rerolls."""
    painted = [layer[: n + 1] for layer in layers(combination) for n in range(len(layer))]
    ids = {figure_id(layer) for layer in painted}
    prompts = [bionics.edit_prompt(f, p[-1], appearance, p[:-1]) for p in painted for f in FRAMES]
    inputs = {
        "player": player,
        "version": bionics.VERSION,
        "prompts": prompts,
        "rerolls": {k: v for k, v in REROLLS.items() if k.split("/")[0] in ids},
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
    missing: list[str] = field(default_factory=list)
    """Bionics it should show but doesn't: `bionics.missing`."""


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
    fitted: Combination = (),
    frame: str = "stand",
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
        colours = {k: v for k, v in standing.colours.items() if k not in bionics.hides(fitted)}
        found = follow(figure, colours, appearance, pose.bands)
        fixed = matched(figure, found, pose.bands)
        after = kept(figure, fixed, colours, appearance, pose.bands)
        tried = Try(seed, raw, after, seconds, followed=True)
        tried.lost = sorted(set(colours) - set(found))
        stand = standing.figures["stand"]
        tried.scale = round(scale(fixed, stand, pose.bands == "climb"), 3)
        tried.strays = strays(fixed, stand, bionics.PALETTE if fitted else None)
    if pose.face:
        eye = bionics.spared(fixed) if Bionic.INFRARED_EYE in fitted else None
        tried.marks = round(face_marks(fixed, appearance, eye), 3)
    tried.missing = bionics.missing(fixed, fitted, frame)
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
    bad = after > CLOSE or wrong or tried.marks > MARKS or off_scale or unlike or tried.missing
    odd = tried.marks + abs(np.log(tried.scale)) + tried.strays + len(tried.lost + tried.missing)
    return bool(bad), odd, after, before


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
    standing: Painted | None = None,
    fitted: Combination = (),
) -> None:
    """Paints `frame` until it matches, at most `tries` times, keeping the best."""
    first = REROLLS.get(f"{painted.who}/{frame}", 0)
    standing = standing or (painted if painted.figures.get("stand") else None)
    made = []
    for n in range(first, first + tries):
        number = seed(painted.who, frame, n)
        args = (painter, prompt, number, images, appearance, cut, pose, standing, fitted, frame)
        made.append(attempt(*args))
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


def paint_parts(
    player: Painted,
    appearance: Appearance,
    painter: Cached,
    cut: Cut = cut_out,
    log: Callable[[str], None] = print,
) -> dict[Combination, Painted]:
    """Each layer on every frame that shows it, as an edit of the `player`'s frame or its base's."""
    found: dict[Combination, Painted] = {}
    for layer in bionics.LAYERS:
        base = found[layer[:-1]] if len(layer) > 1 else player
        painted = Painted(figure_id(layer), colours=player.colours)
        for frame in FRAMES:
            if not any(bionics.shows(b, frame) for b in layer):
                continue
            pose = STANDING if frame == "stand" else EDITS[frame]
            prompt = bionics.edit_prompt(frame, layer[-1], appearance, layer[:-1])
            images, tries = [base.paintings[frame]], TRIES["fitted"]
            args = (painter, painted, frame, prompt, images, appearance, cut, pose, tries)
            paint_frame(*args, standing=player, fitted=layer)
            log(f"{painted.who} {frame}: {summary(painted.tries[frame][-1])}")
        found[layer] = painted
    return found


def fit(player: Painted, parts: dict[Combination, Painted]) -> dict[Combination, dict]:
    """Each combination's frames: the `player`'s, with its `parts` laid over them."""
    laid = {
        (layer, frame): (figure, bionics.changed(player.figures[frame], figure, layer))
        for layer, painted in parts.items()
        for frame, figure in painted.figures.items()
    }
    return {
        combination: {
            frame: bionics.laid(
                whole, [laid[p, frame] for p in layers(combination) if (p, frame) in laid]
            )
            for frame, whole in player.figures.items()
        }
        for combination in COMBINATIONS
    }


def summary(tried: Try) -> str:
    missing = f", missing {', '.join(tried.missing)}" if tried.missing else ""
    return ", ".join(f"{k} {s.delta_e:g}" for k, s in tried.matched.items()) + missing


def files(
    who: str, painted: Painted, standing: Image.Image | None = None, **extra: Any
) -> dict[str, bytes]:
    """The manifest and the atlas, by file name."""
    climbs = [f for f, pose in EDITS.items() if pose.bands == "climb"]
    lifted = {f: pose.lifted for f, pose in EDITS.items() if pose.lifted}
    seated = [f for f, pose in EDITS.items() if pose.seated]
    made = frames(painted.figures, "stand", climbs, lifted, seated, standing)
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
    """Files in `directory` that belong to no one in `keep` nor the player with bionics: #310's
    atlases, or a resident's who's gone."""
    keep = [*keep, *(figure_id(c) for c in COMBINATIONS)]
    wanted = {name for who in keep for name in (f"{who}.json", f"{who}.webp")}
    return [
        p for p in directory.glob("*") if p.suffix in (".json", ".webp") and p.name not in wanted
    ]


def build_fitted(
    model: Cached,
    directory: Path,
    appearance: Appearance,
    player: str,
    whole: Painted | None,
    force: bool = False,
    cut: Cut = cut_out,
    log: Callable[[str], None] = print,
) -> list[Painted]:
    """Paints the bionics over the `whole` player and lays them in every combination."""
    hashes = {figure_id(c): fitted_fingerprint(c, player, appearance) for c in COMBINATIONS}
    if not force and all(current(directory, who, h) for who, h in hashes.items()):
        log("the player with bionics: up to date")
        return []
    whole = whole or paint(PLAYER_ID, appearance, model, cut=cut, log=lambda _: None)
    parts = paint_parts(whole, appearance, model, cut, log)
    dumped = appearance.model_dump(mode="json")
    for combination, figures in fit(whole, parts).items():
        who = figure_id(combination)
        for frame, figure in figures.items():
            if lost := bionics.missing(figure, combination, frame):
                log(f"{who} {frame}: missing {', '.join(lost)}")
        extra = {
            "hash": hashes[who],
            "appearance": dumped,
            "fitted": [b.value for b in combination],
        }
        changed = write(
            directory, files(who, Painted(who, figures=figures), whole.figures["stand"], **extra)
        )
        log(f"{who}: wrote {len(changed)} files")
    return list(parts.values())


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
    isn't in `cache`. The player comes with every combination of bionics."""
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
            extra = {
                "hash": hashes[who],
                "appearance": everyone[who].model_dump(mode="json"),
                **({"resident": False} if who in outsiders() else {}),
            }
            changed = write(directory, files(who, painted, **extra))
            log(f"{who}: painted in {painted.seconds:.0f} s of FLUX, wrote {len(changed)} files")
            done.append(painted)
        if PLAYER_ID in wanted:
            whole = next((p for p in done if p.who == PLAYER_ID), None)
            player = (everyone[PLAYER_ID], hashes[PLAYER_ID], whole)
            done += build_fitted(model, directory, *player, force=force, cut=cut, log=log)
    if not only:
        for path in stale(directory, everyone):
            path.unlink()
            log(f"removed {path.name}")
    return done
