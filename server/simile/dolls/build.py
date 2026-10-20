"""Paints the residents' and the player's dolls into `content/dolls/`, repainting only those whose
`Appearance` or pipeline changed."""

import hashlib
import json
import tempfile
import time
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager, ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from simile.dolls.doll import VERSION, Doll, aligned, atlas, flat_doll, manifest, pack, webp
from simile.dolls.look import Look
from simile.dolls.paint import SheetPainter, prompt, seed
from simile.dolls.pieces import Piece
from simile.dolls.sheet import LAYOUTS, SIZE, cut, misplaced, patches, sheet
from simile.schema import PLAYER_ID, Appearance

REPO = Path(__file__).resolve().parents[3]
CONTENT = REPO / "content" / "dolls"
PAINTINGS = REPO / "server" / "data" / "dolls" / "paintings"
"""Every painting as FLUX returned it, by what it was painted from, so cutting can be retuned
without painting again. Ignored by git."""
REFERENCES = (
    REPO / "content" / "papercraft" / "references" / "characters.jpg",
    REPO / "docs" / "side-view-study" / "references" / "characters.jpg",
)
"""The villagers reference: part 3's copy once it lands, the study's until then."""
REFERENCE_WIDTH = 768
DONORS = {"shoe_front": "shoe"}
"""A piece the painter often drops, and the piece of the same colours to take its paint from."""
REROLLS: dict[str, int] = {
    "ingrid/side": 1,
    "ingrid/front_back": 1,
    "lachlan/side": 1,
    "marguerite/front_back": 1,
    "mirela/side": 3,
    "odalys/front_back": 5,
    "tobias/side": 4,
}
"""`<id>/<sheet>` to a reroll number, for a painting that came out off-model or off-tone."""


def people() -> dict[str, Appearance]:
    """Every resident in `content/npcs/` and the player, by id."""
    from simile.art.characters import PLAYER
    from simile.npc.content import NPCS_DIR, load_npcs

    return {npc.id: npc.appearance for npc in load_npcs(NPCS_DIR)} | {PLAYER_ID: PLAYER}


def reference() -> Path:
    return next(path for path in REFERENCES if path.exists())


def fingerprint(who: str, appearance: Appearance) -> str:
    """What a doll is painted from: a new one means it's painted again."""
    inputs = {
        "version": VERSION,
        "who": who,
        "appearance": appearance.model_dump(mode="json"),
        "rerolls": {k: v for k, v in REROLLS.items() if k.startswith(f"{who}/")},
    }
    return hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:16]


@dataclass
class Painted:
    who: str
    doll: Doll
    seconds: dict[str, float] = field(default_factory=dict)
    misplaced: dict[str, float] = field(default_factory=dict)
    patches: dict[str, float] = field(default_factory=dict)
    paintings: dict[str, Image.Image] = field(default_factory=dict)


class Lazy:
    """Enters the painter's context only when a painting isn't cached."""

    def __init__(self, painter: Callable[[], AbstractContextManager[SheetPainter]]) -> None:
        self.factory = painter
        self.stack = ExitStack()
        self.model: SheetPainter | None = None

    def paint(
        self, prompt: str, images: list[Path], size: tuple[int, int], seed: int
    ) -> Image.Image:
        if self.model is None:
            self.model = self.stack.enter_context(self.factory())
        return self.model.paint(prompt, images, size, seed)


def paint(
    who: str, appearance: Appearance, painter: SheetPainter, scratch: Path, cache: Path | None
) -> Painted:
    """Every sheet painted and cut, the pieces laid over the flat ones at the atlas's scale."""
    look = Look.of(appearance, who)
    doll = flat_doll(look)
    pieces: dict[str, tuple[Image.Image, Piece, float]] = {}
    out = Painted(who, doll)
    small = scratch / "reference.png"
    if not small.exists():
        image = Image.open(reference()).convert("RGB")
        height = round(image.height * REFERENCE_WIDTH / image.width / 16) * 16
        image.resize((REFERENCE_WIDTH, height), Image.Resampling.LANCZOS).save(small)
    for name in LAYOUTS:
        laid = sheet(name, look)
        path = scratch / f"{who}-{name}.png"
        laid.image().save(path)
        asked = prompt(name, appearance, who)
        number = seed(who, name, REROLLS.get(f"{who}/{name}", 0))
        key = hashlib.sha256(
            asked.encode() + str(number).encode() + path.read_bytes() + small.read_bytes()
        ).hexdigest()[:16]
        cached = None if cache is None else cache / f"{who}-{name}-{key}.png"
        if cached is not None and cached.exists():
            painting = Image.open(cached).convert("RGB")
        else:
            start = time.perf_counter()
            painting = painter.paint(asked, [path, small], SIZE, number)
            out.seconds[name] = round(time.perf_counter() - start, 1)
            if cached is not None:
                cached.parent.mkdir(parents=True, exist_ok=True)
                painting.save(cached)
        out.paintings[name] = painting
        out.misplaced |= misplaced(laid, painting)
        out.patches |= patches(laid, painting)
        for piece, image in cut(laid, painting).items():
            pieces[piece] = (image, laid.pieces[piece], laid.scale)
    for piece, donor in DONORS.items():
        if out.misplaced.get(piece, 0.0) > 0.5:
            given, _, scale = pieces[donor]
            flat = pieces[piece][1]
            pieces[piece] = (given.resize(flat.image.size, Image.Resampling.LANCZOS), flat, scale)
    doll.painted = {
        piece: aligned(image, laid_piece, scale, doll.flat[piece])
        for piece, (image, laid_piece, scale) in pieces.items()
    }
    return out


def files(who: str, doll: Doll, **extra: Any) -> dict[str, bytes]:
    """The manifest and atlases, by file name."""
    size, frames = pack(doll.flat)
    images = {"flat": f"{who}-flat.webp"}
    out = {images["flat"]: webp(atlas(doll.flat, size, frames), lossless=True)}
    if doll.painted is not None:
        images["painted"] = f"{who}-painted.webp"
        out[images["painted"]] = webp(atlas(doll.painted, size, frames), lossless=False)
    body = manifest(doll, frames, images, id=who, **extra)
    out[f"{who}.json"] = (json.dumps(body, indent=2) + "\n").encode()
    return out


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
    return found.get("hash") == hash and all(
        (directory / found.get(kind, "")).is_file() for kind in ("flat", "painted")
    )


def build(
    painter: Callable[[], AbstractContextManager[SheetPainter]],
    directory: Path = CONTENT,
    only: Iterable[str] = (),
    force: bool = False,
    cache: Path | None = PAINTINGS,
    log: Callable[[str], None] = print,
) -> list[Painted]:
    """Paints each doll whose fingerprint changed, loading the painter only if a painting isn't
    in `cache`."""
    everyone = people()
    wanted = list(only) or list(everyone)
    unknown = [who for who in wanted if who not in everyone]
    if unknown:
        raise KeyError(f"No resident or player called {', '.join(unknown)}")
    stale = {
        who: fingerprint(who, everyone[who])
        for who in wanted
        if force or not current(directory, who, fingerprint(who, everyone[who]))
    }
    for who in set(wanted) - set(stale):
        log(f"{who}: up to date")
    done: list[Painted] = []
    if not stale:
        return done
    model = Lazy(painter)
    with model.stack, tempfile.TemporaryDirectory() as scratch:
        for who, hash in stale.items():
            painted = paint(who, everyone[who], model, Path(scratch), cache)
            appearance = everyone[who].model_dump(mode="json")
            changed = write(directory, files(who, painted.doll, hash=hash, appearance=appearance))
            seconds = " + ".join(f"{s:.0f} s" for s in painted.seconds.values()) or "cache"
            log(f"{who}: painted in {seconds}, wrote {len(changed)} files")
            done.append(painted)
    return done
