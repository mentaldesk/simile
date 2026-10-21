"""Approach 4: approach 3's Blender renders, each repainted by FLUX in edit mode in the grimy
cartoon style.

Two ways: every frame on its own, and the walk four frames to a painting, which FLUX keeps more
alike. `python repaint.py [who …]` paints what's missing into out/repaint/ and cuts every
painting out of its background.
"""

import sys

from PIL import Image
from study import (
    FACE,
    OUT,
    RESIDENTS_REF,
    WHO,
    Painter,
    cut_out,
    described,
    restored,
    styled,
)

FOLDER = OUT / "repaint"
STRIP_FOLDER = OUT / "repaint-strip"
MODEL = OUT / "model"
SIZE = (512, 768)
BACKGROUND = (214, 210, 202)
FRAMES = (
    *(f"walk-{i}" for i in range(8)),
    "stand",
    "front",
    "back",
    "sit",
    "stairs-1",
    "ladder-1",
)
BEHIND = {"back", "ladder-1"}
STRIP = 336
"""Each frame's width in a four-frame strip: 1344 px, as wide as FLUX paints at 768 px tall."""
PROMPT = (
    "Redraw image 1 as the same {many} in exactly the same pose, place and size, in the "
    "scratchy, grimy hand-drawn cartoon style of the residents in image 2: a very big round head, "
    "thick scratchy dark brown ink outlines, flat colours with simple soft shading and a few "
    "light smudges on the clothes. Keep every colour. {who} {face} Keep the background plain "
    "light grey."
)
SEED = 1


def on_grey(image: Image.Image) -> Image.Image:
    back = Image.new("RGBA", image.size, (*BACKGROUND, 255))
    back.alpha_composite(image.convert("RGBA"))
    return back.convert("RGB")


def render(who: str, name: str) -> Image.Image:
    return Image.open(MODEL / who / f"{name}.png").convert("RGBA")


def prompt(who: str, name: str | None, many: bool = False) -> str:
    if many:
        face = f"{FACE} Each of the four is the same person, drawn alike."
        what = "cartoon character four times, walking"
    else:
        face = "Seen from behind, with no face." if name in BEHIND else FACE
        what = "cartoon character"
    return styled(PROMPT.format(many=what, who=described(who), face=face))


def reference() -> Image.Image:
    image = Image.open(RESIDENTS_REF).convert("RGB")
    return image.resize((768, round(image.height * 768 / image.width / 16) * 16))


def strip(who: str, names: list[str]) -> Image.Image:
    out = Image.new("RGB", (STRIP * len(names), SIZE[1]), BACKGROUND)
    for i, name in enumerate(names):
        frame = on_grey(render(who, name))
        left = (SIZE[0] - STRIP) // 2
        out.paste(frame.crop((left, 0, left + STRIP, SIZE[1])), (i * STRIP, 0))
    return out


def unstrip(painting: Image.Image, names: list[str]) -> dict[str, Image.Image]:
    out = {}
    left = (SIZE[0] - STRIP) // 2
    for i, name in enumerate(names):
        frame = Image.new("RGB", SIZE, BACKGROUND)
        frame.paste(painting.crop((i * STRIP, 0, (i + 1) * STRIP, SIZE[1])), (left, 0))
        out[name] = frame
    return out


def paint(who: list[str]) -> None:
    todo = [(w, n) for w in who for n in FRAMES if not (FOLDER / w / f"{n}.png").exists()]
    strips = [
        (w, k)
        for w in who
        for k in (0, 1)
        if not (STRIP_FOLDER / w / "paintings" / f"walk-{4 * k}-{4 * k + 3}.png").exists()
    ]
    if not todo and not strips:
        return
    ref = reference()
    with Painter("repaint") as painter:
        for name, frame in todo:
            guide = on_grey(render(name, frame))
            image = painter.paint(f"{name}/{frame}", prompt(name, frame), SIZE, SEED, [guide, ref])
            (FOLDER / name).mkdir(parents=True, exist_ok=True)
            image.save(FOLDER / name / f"{frame}.png")
        for name, k in strips:
            names = [f"walk-{i}" for i in range(4 * k, 4 * k + 4)]
            guide = strip(name, names)
            size = guide.size
            image = painter.paint(
                f"strip/{name}/{k}", prompt(name, None, True), size, SEED, [guide, ref]
            )
            folder = STRIP_FOLDER / name / "paintings"
            folder.mkdir(parents=True, exist_ok=True)
            guide.save(folder / f"walk-{4 * k}-{4 * k + 3}-guide.png")
            image.save(folder / f"walk-{4 * k}-{4 * k + 3}.png")


def recoloured(painting: Image.Image, who: str, frame: str) -> Image.Image:
    """#310's colour restore, with Blender's flat pass naming each region: the repaint's
    colours pulled back to the `Look`, keeping its shading."""
    flat = Image.open(MODEL / who / f"{frame}-flat.png").convert("RGBA")
    back = Image.new("RGBA", flat.size, (*BACKGROUND, 255))
    back.alpha_composite(flat)
    return restored(painting, back)


def cut(who: list[str]) -> None:
    """Every repainted frame cut out of its background, as approach 3's renders are: as FLUX
    painted it, and with its colours restored."""
    for name in who:
        for frame in FRAMES:
            source = FOLDER / name / f"{frame}.png"
            if source.exists():
                painting = Image.open(source).convert("RGB")
                alpha = cut_out(painting).getchannel("A")
                for kind, image in (("raw", painting), ("cut", recoloured(painting, name, frame))):
                    (FOLDER / name / kind).mkdir(parents=True, exist_ok=True)
                    image = image.convert("RGBA")
                    image.putalpha(alpha)
                    image.save(FOLDER / name / kind / f"{frame}.png")
        for k in (0, 1):
            source = STRIP_FOLDER / name / "paintings" / f"walk-{4 * k}-{4 * k + 3}.png"
            if source.exists():
                names = [f"walk-{i}" for i in range(4 * k, 4 * k + 4)]
                for frame, image in unstrip(Image.open(source).convert("RGB"), names).items():
                    cut_out(image).save(STRIP_FOLDER / name / f"{frame}.png")


if __name__ == "__main__":
    names = [a for a in sys.argv[1:] if a in WHO] or list(WHO)
    if "cut" not in sys.argv[1:]:
        paint(names)
    cut(names)
