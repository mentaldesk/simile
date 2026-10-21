"""Approach 1: flat whole characters, painted by FLUX like Paper Mario's.

Each resident is painted whole from text, standing in three-quarter view, as #295's villagers
were. Its walk, sitting and climbing are edits of that painting. The client would flip the sprite
for the other direction and bob and sway it as it walks.

`python whole.py [who …]` paints what's missing into out/whole/.
"""

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from study import FACE, OUT, WHO, Painter, cut_out, described, restored, styled, trimmed

FOLDER = OUT / "whole"
SIZE = (768, 1024)
CITY = "a modern southern Chinese tech city like Shenzhen"
BODY = (
    "The character has a very big round head, almost half their height, on a small short body "
    "with short legs, like the residents of a cartoon colony-building game."
)
BACKGROUND = "on a plain flat light grey background with nothing else in the picture"
STAND = (
    "A single full-body 2D game character sprite {background}: one resident of {city}, standing "
    "in a three-quarter view turned to the right, arms relaxed at the sides, feet apart. {who} "
    "{body} {face} Contemporary casual clothes."
)
EDITS = {
    "step_a": (
        "Redraw image 1 with the same character, unchanged in every detail and the same size, in "
        "the same three-quarter view turned to the right, now walking to the right in mid-stride: "
        "the left leg forward, the right leg back, the arms swinging."
    ),
    "step_b": (
        "Redraw image 1 with the same character, unchanged in every detail and the same size, in "
        "the same three-quarter view turned to the right, now walking to the right in the middle "
        "of a step: standing on the straight right leg with the left knee lifted forward and the "
        "left foot off the ground, the arms close to the sides."
    ),
    "sit": (
        "Redraw image 1 with the same character, unchanged in every detail and the same size, in "
        "the same three-quarter view turned to the right, now sitting with the knees bent forward "
        "and the hands resting on the knees, sitting in mid-air with nothing under them: no "
        "chair, no box, no seat."
    ),
    "climb": (
        "Redraw image 1 with the same character, unchanged in every detail and the same size, now "
        "seen from directly behind: the back of the head and the back of the clothes, both hands "
        "raised above the head as if gripping a rung, one knee raised as if stepping up, hanging "
        "in mid-air with nothing else drawn: no ladder, no steps, no rungs."
    ),
}
"""Each pose, as an edit of the standing painting."""
SEEDS: dict[str, int] = {}
"""`<who>/<pose>` to a seed other than 1, for a painting that came out off-model."""


def stand_prompt(who: str) -> str:
    return styled(
        STAND.format(background=BACKGROUND, city=CITY, who=described(who), body=BODY, face=FACE)
    )


def edit_prompt(who: str, pose: str) -> str:
    face = "" if pose == "climb" else f" {FACE}"
    return styled(f"{EDITS[pose]} {described(who)}{face} Keep the background plain light grey.")


def path(who: str, pose: str) -> Path:
    seed = SEEDS.get(f"{who}/{pose}", 1)
    return FOLDER / "paintings" / f"{who}-{pose}-{seed}.png"


def paint(who: list[str], poses: list[str]) -> None:
    stands = [w for w in who if not path(w, "stand").exists()]
    if stands:
        with Painter("whole", edit=False) as painter:
            for name in stands:
                seed = SEEDS.get(f"{name}/stand", 1)
                image = painter.paint(f"{name}/stand", stand_prompt(name), SIZE, seed)
                path(name, "stand").parent.mkdir(parents=True, exist_ok=True)
                image.save(path(name, "stand"))
    edits = [(w, p) for w in who for p in poses if not path(w, p).exists()]
    if edits:
        with Painter("whole") as painter:
            for name, pose in edits:
                seed = SEEDS.get(f"{name}/{pose}", 1)
                base = Image.open(path(name, "stand"))
                image = painter.paint(f"{name}/{pose}", edit_prompt(name, pose), SIZE, seed, [base])
                image.save(path(name, pose))


POSES = ("stand", *EDITS)
STRIP = [(f"w{i}", "side", None, 0.13 + 0.245 * i) for i in range(4)]
"""Approach 1 painted from the rig instead: four side-on walk frames on one sheet."""
STRIP_PROMPT = (
    "Redraw image 1 as four drawings of the same cartoon game character walking to the right, "
    "seen from the side, in the scratchy, grimy cartoon style of the residents in image 2. Keep "
    "each figure's pose, size and place, its very big round head and its colours, but draw it "
    "freely as one whole person with natural rounded shapes, real clothes, hands and shoes, "
    "rather than separate flat pieces. All four are the same person, drawn alike. {who} {face} "
    "Keep the background plain light grey."
)


def strip_figures() -> list:
    import poses

    return [
        (name, view, poses.walk(i / 4), across) for i, (name, view, _, across) in enumerate(STRIP)
    ]


def paint_strips(who: list[str]) -> None:
    import cut

    folder = FOLDER / "strip"
    todo = [w for w in who if not (folder / f"{w}.png").exists()]
    if not todo:
        return
    reference = Image.open(cut.RESIDENTS_REF).convert("RGB")
    reference = reference.resize((768, round(reference.height * 768 / reference.width / 16) * 16))
    folder.mkdir(parents=True, exist_ok=True)
    with Painter("whole") as painter:
        for name in todo:
            guide = cut.mannequin(name, figures=strip_figures()).image
            guide.save(folder / f"{name}-guide.png")
            words = styled(STRIP_PROMPT.format(who=described(name), face=FACE))
            image = painter.paint(f"strip/{name}", words, cut.SHEET, 1, [guide, reference])
            image.save(folder / f"{name}.png")


def strip_sprites(who: list[str]) -> None:
    """Each painted walk frame cut out, every painted blob going to the nearest frame: as FLUX
    painted it in raw/, and with #310's colour restore, the mannequin fitted over the painting
    naming each region."""
    import cut
    import cv2

    folder = FOLDER / "strip"
    (folder / "raw").mkdir(parents=True, exist_ok=True)
    feet = {}
    for name in who:
        painting = Image.open(folder / f"{name}.png").convert("RGB")
        rgba = cut_out(painting)
        alpha = np.asarray(rgba.getchannel("A")) > 128
        mannequin, _ = cut.fitted(name, alpha.astype(np.float32), strip_figures())
        kept = restored(painting, mannequin.image).convert("RGBA")
        kept.putalpha(rgba.getchannel("A"))
        count, labels, stats, centres = cv2.connectedComponentsWithStats(alpha.astype(np.uint8), 8)
        middles = [cut.SHEET[0] * across for *_, across in STRIP]
        for i, (frame, *_) in enumerate(STRIP):
            mine = np.zeros_like(alpha)
            for c in range(1, count):
                nearest = min(range(len(middles)), key=lambda k: abs(middles[k] - centres[c][0]))
                if stats[c, cv2.CC_STAT_AREA] >= 300 and nearest == i:
                    mine |= labels == c
            a = np.asarray(rgba.getchannel("A")).copy()
            a[~mine] = 0
            box = Image.fromarray(a).point(lambda v: 255 if v > 24 else 0).getbbox()
            box = (max(0, box[0] - 4), max(0, box[1] - 4), box[2] + 4, box[3] + 4)
            for source, path in ((rgba, folder / "raw"), (kept, folder)):
                image = source.copy()
                image.putalpha(Image.fromarray(a))
                image.crop(box).save(path / f"{name}-{frame}.png")
            b = a[box[1] : box[3], box[0] : box[2]] > 128
            rows = np.flatnonzero(b.any(axis=1))
            top, bottom = rows[0], rows[-1]
            cols = np.flatnonzero(b[top : top + round(0.3 * (bottom - top))].any(axis=0))
            feet[f"{name}/{frame}"] = [round(float(cols.mean()), 1), int(bottom), int(top)]
    (folder / "feet.json").write_text(json.dumps(feet, indent=1))


def sprites(who: list[str]) -> None:
    """Each painting cut out of its background and trimmed, with where it stands: under the
    middle of its head, so the head doesn't jump sideways as the legs change, and at its
    lowest row."""
    folder = FOLDER / "sprites"
    folder.mkdir(parents=True, exist_ok=True)
    feet = {}
    for name in who:
        for pose in POSES:
            image = trimmed(cut_out(Image.open(path(name, pose)).convert("RGB")))
            a = np.asarray(image.getchannel("A")) > 128
            rows = np.flatnonzero(a.any(axis=1))
            bottom, top = rows[-1], rows[0]
            cols = np.flatnonzero(a[top : top + round(0.3 * (bottom - top))].any(axis=0))
            feet[f"{name}/{pose}"] = [round(float(cols.mean()), 1), int(bottom), int(rows[0])]
            image.save(folder / f"{name}-{pose}.png")
    known = (
        json.loads((folder / "feet.json").read_text()) if (folder / "feet.json").exists() else {}
    )
    (folder / "feet.json").write_text(json.dumps(known | feet, indent=1))


if __name__ == "__main__":
    names = [a for a in sys.argv[1:] if a in WHO] or list(WHO)
    if "strip" in sys.argv[1:]:
        import poses

        poses.use()
        paint_strips(names)
        strip_sprites(names)
    elif "sprites" in sys.argv[1:]:
        sprites(names)
    else:
        paint(names, [a for a in sys.argv[1:] if a in EDITS] or list(EDITS))
