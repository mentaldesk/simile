from collections.abc import Sequence

from PIL import Image

from simile.art.canvas import GLYPH_HEIGHT, Canvas, draw_text, text_width
from simile.art.characters import (
    DIRECTIONS,
    FRAME_HEIGHT,
    FRAME_WIDTH,
    FRAMES,
    Appearance,
    draw_frame,
    sprite_sheet,
)
from simile.art.palette import PALETTE, RGB, rgba
from simile.art.tiles import COLUMNS, TILE_SIZE, Tile, groups, tile_ids

BACKGROUND = "night"
TEXT = "pavement"
MUTED = "concrete"


def scaled(image: Image.Image, scale: int) -> Image.Image:
    return image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)


def label(text: str, colour: str = TEXT, scale: int = 2) -> Image.Image:
    c = Canvas(max(text_width(text), 1), GLYPH_HEIGHT)
    draw_text(c, text, 0, 0, colour)
    return scaled(c.to_image(), scale)


def checker(width: int, height: int, size: int = 6) -> Image.Image:
    image = Image.new("RGBA", (width, height), rgba("pavement"))
    alt = Image.new("RGBA", (size, size), rgba("concrete"))
    for y in range(0, height, size):
        for x in range((y // size) % 2 * size, width, size * 2):
            image.paste(alt, (x, y))
    return image


def palette_strip(scale: int = 2) -> Image.Image:
    swatch, border = 12 * scale, 2
    width = swatch * len(PALETTE) + 2 * border
    image = Image.new("RGBA", (width, swatch + 2 * border), rgba("steel"))
    for i, name in enumerate(PALETTE):
        image.paste(Image.new("RGBA", (swatch, swatch), rgba(name)), (border + i * swatch, border))
    return image


def tiles_sheet(cells: list[Tile | None], scale: int = 3) -> Image.Image:
    cell = TILE_SIZE * scale
    pitch = cell + 6
    margin = 16
    ids = tile_ids(cells)
    blocks = [(g.name, [t.name for t in g.tiles]) for g in groups()]
    heading = 2 * GLYPH_HEIGHT + 10
    id_height = 2 * GLYPH_HEIGHT + 4
    rows_height = sum(
        heading + -(-len(tiles) // COLUMNS) * (cell + id_height + 4) for _, tiles in blocks
    )
    palette = palette_strip()
    title_height = 3 * GLYPH_HEIGHT + 12
    width = margin * 2 + COLUMNS * pitch
    height = margin * 2 + title_height + palette.height + 12 + rows_height
    sheet = Image.new("RGBA", (width, height), rgba(BACKGROUND))
    sheet.alpha_composite(label("SIMILE TILESET - 16PX TILES AT 3X", scale=3), (margin, margin))
    y = margin + title_height
    sheet.alpha_composite(palette, (margin, y))
    y += palette.height + 12
    by_name = {t.name: t for t in cells if t is not None}
    for group_name, tiles in blocks:
        sheet.alpha_composite(label(group_name, MUTED), (margin, y))
        y += heading
        for i, name in enumerate(tiles):
            x0 = margin + i % COLUMNS * pitch
            y0 = y + i // COLUMNS * (cell + id_height + 4)
            background = checker(cell, cell)
            background.alpha_composite(scaled(by_name[name].canvas.to_image(), scale))
            sheet.alpha_composite(background, (x0, y0))
            sheet.alpha_composite(label(str(ids[name])), (x0, y0 + cell + 2))
        y += -(-len(tiles) // COLUMNS) * (cell + id_height + 4)
    return sheet


def characters_sheet(
    people: dict[str, Appearance], scale: int = 3, seeded: bool = False
) -> Image.Image:
    per_row = 6
    margin = 16
    sheet_w, sheet_h = FRAME_WIDTH * FRAMES * scale, FRAME_HEIGHT * len(DIRECTIONS) * scale
    pitch_x = sheet_w + 24
    name_height = 2 * GLYPH_HEIGHT + 8
    pitch_y = name_height + sheet_h + 24
    rows = -(-len(people) // per_row)
    actual = 1 * FRAME_HEIGHT + 2 * FRAME_HEIGHT + 16
    width = margin * 2 + min(per_row, len(people)) * pitch_x
    height = margin * 2 + 3 * GLYPH_HEIGHT + 12 + actual + rows * pitch_y
    image = Image.new("RGBA", (width, height), rgba(BACKGROUND))
    image.alpha_composite(
        label("CHARACTERS - 1X, 2X, THEN SHEETS AT 3X", scale=3), (margin, margin)
    )
    y = margin + 3 * GLYPH_HEIGHT + 12
    strip = Image.new("RGBA", (len(people) * (FRAME_WIDTH + 4), FRAME_HEIGHT), rgba("pavement"))
    for i, (name, appearance) in enumerate(people.items()):
        frame = draw_frame(appearance, "down", 1, name if seeded else None)
        strip.alpha_composite(frame.to_image(), (i * (FRAME_WIDTH + 4), 0))
    image.alpha_composite(strip, (margin, y))
    image.alpha_composite(scaled(strip, 2), (margin, y + FRAME_HEIGHT + 8))
    y += actual
    for i, (name, appearance) in enumerate(people.items()):
        x0 = margin + (i % per_row) * pitch_x
        y0 = y + (i // per_row) * pitch_y
        image.alpha_composite(label(name.replace("_", " ")), (x0, y0))
        background = Image.new("RGBA", (sheet_w, sheet_h), rgba("pavement"))
        sheet = sprite_sheet(appearance, name if seeded else None)
        background.alpha_composite(scaled(sheet.to_image(), scale))
        image.alpha_composite(background, (x0, y0 + name_height))
    return image


WALK_CYCLE = (0, 1, 2, 1)
WALK_ORDER = ("down", "down_left", "left", "up_left", "up", "up_right", "right", "down_right")


def walk_frames(people: Sequence[Appearance], tile: Tile, scale: int = 3) -> list[Image.Image]:
    gap = 8
    width = len(people) * (FRAME_WIDTH + gap) + gap
    height = FRAME_HEIGHT + 2 * gap
    floor = Canvas(width, height)
    for y in range(0, height, TILE_SIZE):
        for x in range(0, width, TILE_SIZE):
            floor.paste(tile.canvas, x, y)
    frames = []
    for direction in WALK_ORDER:
        for _ in range(2):
            for step in WALK_CYCLE:
                c = Canvas(width, height)
                c.paste(floor)
                for i, appearance in enumerate(people):
                    c.paste(
                        draw_frame(appearance, direction, step), gap + i * (FRAME_WIDTH + gap), gap
                    )
                frames.append(scaled(c.to_image(), scale))
    return frames


def gif_palette() -> Image.Image:
    image = Image.new("P", (1, 1))
    colours = [channel for name in PALETTE for channel in RGB[name]]
    image.putpalette(colours + [0] * (768 - len(colours)))
    return image


def save_gif(frames: list[Image.Image], path: str, duration: int = 140) -> None:
    palette = gif_palette()
    indexed = [
        frame.convert("RGB").quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames
    ]
    indexed[0].save(
        path, save_all=True, append_images=indexed[1:], duration=duration, loop=0, optimize=False
    )
