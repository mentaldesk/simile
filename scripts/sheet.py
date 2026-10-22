"""Sheets of the player's frames: every combination of bionics, and each one made both ways.

    uv run python sheet.py <out dir> overlays=<content/dolls> "full edits=<dir>" ...
"""

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

FRAMES = ["stand", "stride", "pass", "run", "run_pass", "sit", "climb"]
IDS = [
    "player",
    "player_legs",
    "player_datajack",
    "player_eye",
    "player_legs_datajack",
    "player_legs_eye",
    "player_datajack_eye",
    "player_legs_datajack_eye",
]
CELL = (110, 180)
SCALE = 2
BACK = (239, 232, 218)


def frames(folder: Path, who: str) -> dict[str, Image.Image]:
    body = json.loads((folder / f"{who}.json").read_text())
    atlas = Image.open(folder / body["painted"]).convert("RGBA")
    out = {}
    for name, entry in body["frames"].items():
        x, y, w, h = entry["frame"]
        out[name] = (atlas.crop((x, y, x + w, y + h)), entry["feet"])
    return out


def row(found: dict, label: str) -> Image.Image:
    w, h = CELL
    out = Image.new("RGBA", (w * len(FRAMES) + 160, h), BACK + (255,))
    ImageDraw.Draw(out).text((6, h // 2), label, fill=(60, 50, 40))
    for i, name in enumerate(FRAMES):
        picture, (fx, fy) = found[name]
        out.alpha_composite(picture, (160 + i * w + round(w / 2 - fx), round(h - 8 - fy)))
    return out


def main(out: Path, *sources: str) -> None:
    """`sources` are `label=folder`: the first is drawn whole, and each combination's sheet has a
    row from each."""
    out.mkdir(parents=True, exist_ok=True)
    named = [(label, Path(folder)) for label, folder in (s.split("=", 1) for s in sources)]
    first = named[0][1]
    sheet([row(frames(first, who), who) for who in IDS], out / "all.png")
    for who in IDS[1:]:
        sheet([row(frames(folder, who), label) for label, folder in named], out / f"{who}.png")


def sheet(rows: list[Image.Image], path: Path) -> None:
    w, h = rows[0].size
    out = Image.new("RGBA", (w, h * len(rows)), BACK + (255,))
    for i, r in enumerate(rows):
        out.alpha_composite(r, (0, i * h))
    out = out.resize((w * SCALE, h * len(rows) * SCALE), Image.Resampling.LANCZOS)
    out.convert("RGB").save(path)


if __name__ == "__main__":
    main(Path(sys.argv[1]), *sys.argv[2:])
