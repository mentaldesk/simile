"""The real client's shots in one grid: a row for each combination, standing, walking, jumping and
facing west. python grid.py <shots dir> <out.png>"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

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
SHOTS = ["standing", "walking", "jumping", "west"]
LABEL = 200


def main(folder: Path, out: Path) -> None:
    shots = {(w, s): Image.open(folder / f"{w}-{s}.png").convert("RGB") for w in IDS for s in SHOTS}
    cw = max(i.width for i in shots.values())
    ch = max(i.height for i in shots.values())
    grid = Image.new("RGB", (LABEL + cw * len(SHOTS), 30 + ch * len(IDS)), (250, 248, 244))
    draw = ImageDraw.Draw(grid)
    for c, s in enumerate(SHOTS):
        draw.text((LABEL + c * cw + 8, 8), s, fill=(40, 30, 20))
    for r, w in enumerate(IDS):
        draw.text((8, 30 + r * ch + ch // 2), w, fill=(40, 30, 20))
        for c, s in enumerate(SHOTS):
            shot = shots[w, s]
            grid.paste(shot, (LABEL + c * cw + (cw - shot.width) // 2, 30 + r * ch + (ch - shot.height)))
    grid.save(out)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
