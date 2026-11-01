"""Lies each figure on the bed art at play size (80 px/m, 1:1): p53-bed.py out.png zoom id-or-png..."""

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve()
CONTENT = Path.cwd().parent / "content"
PPM = 80
BED_W_M = 1.58
MATTRESS = (0.5, 76 / 126)
"""Where the underside goes on the bed art: the middle of the mattress's top face, by eye."""

out_path, zoom, items = Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3:]
bed = Image.open(CONTENT / "papercraft/furniture/bed.webp").convert("RGBA")
factor = BED_W_M * PPM / bed.width
bed = bed.resize((round(bed.width * factor), round(bed.height * factor)), Image.Resampling.LANCZOS)


def lying(item: str) -> tuple[str, Image.Image, tuple[float, float]]:
    if item.endswith(".png"):
        name, rest = item.split("=")
        image = Image.open(rest).convert("RGBA")
        box = image.getchannel("A").getbbox()
        image = image.crop(box)
        return name, image, (image.width / 2, image.height)
    body = json.loads((CONTENT / "dolls" / f"{item}.json").read_text())
    sheet = Image.open(CONTENT / "dolls" / body["painted"]).convert("RGBA")
    entry = body["frames"]["lie"]
    x, y, w, h = entry["frame"]
    return item, sheet.crop((x, y, x + w, y + h)), tuple(entry["bed"])


cells = [lying(i) for i in items]
cell_w = max(bed.width, *(im.width for _, im, _ in cells)) + 40
cell_h = bed.height + 90
cols = min(4, len(cells))
rows = (len(cells) + cols - 1) // cols
sheet = Image.new("RGBA", (cols * cell_w, rows * cell_h), (236, 232, 224, 255))
draw = ImageDraw.Draw(sheet)
for i, (name, image, (bx, by)) in enumerate(cells):
    ox, oy = (i % cols) * cell_w, (i // cols) * cell_h
    left = ox + (cell_w - bed.width) // 2
    top = oy + cell_h - bed.height - 14
    sheet.alpha_composite(bed, (left, top))
    mx, my = left + MATTRESS[0] * bed.width, top + MATTRESS[1] * bed.height
    sheet.alpha_composite(image, (round(mx - bx), round(my - by)))
    draw.text((ox + 4, oy + 2), name, fill=(60, 50, 40, 255))
if zoom > 1:
    sheet = sheet.resize((sheet.width * zoom, sheet.height * zoom), Image.Resampling.NEAREST)
sheet.convert("RGB").save(out_path)
