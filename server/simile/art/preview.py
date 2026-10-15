from collections.abc import Sequence
from dataclasses import dataclass, field

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
from simile.art.tiles import COLUMNS, TILE_SIZE, Tile, edge_variant, groups, tile_ids

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


# Scene

TERRAIN = [
    "RRRRRRRRRRRRRRRRRRRRRRRRRRRR",
    "RRRRRRRRRRRRRRRRRRRRRRRRRRRR",
    "RRRRRRRRRRRRRRRRRRRRRRRRRRRR",
    "PPPPPPPPPPPPPPPPPPPPPPPPPPPP",
    "PPPPPPPPPPPPPPPPPPPPPPPPPPPP",
    "PPPPPPPPPPPPPPPPPPPPPPPPPPPP",
    "PPPPPPPPPPPPPPPPPPPPPPPPPPPP",
    "PPPPPPPPPPPPPPPPPPPPPPPPPPPP",
    "PPPPPPPPPPPPPPPPPPPPPPPPPPPP",
    "PPPPPPPPPPPPPPPPPPPPPPPPPPPP",
    "PGGGGGGGPPPPPPPPPPPZZZZZZZZP",
    "PGGGGGGGPPPPPPPPPPPZZZZZZZZP",
    "PGGGGGGGPPWWWWWWWPPZZZZZZZZP",
    "PGGGGGPPPPWWWWWWWPPZZZZZZZZP",
    "PGGGGGPPPPWWWWWWWPPZZZZZZZZP",
    "PPPPPPPPPPPPPPPPPPPZZZZZZZZP",
    "PPPPPPPPPPPPPPPPPPPPPPPPPPPP",
]
TERRAIN_TILES = {"P": "pavement", "G": "grass", "R": "road", "W": "water", "Z": "plaza"}


@dataclass
class Scene:
    ground: dict[tuple[int, int], str] = field(default_factory=dict)
    placements: list[tuple[int, int, str]] = field(default_factory=list)

    def put(self, x: int, y: int, *names: str) -> None:
        for i, name in enumerate(names):
            self.placements.append((x + i, y, name))

    def building(self, x: int, y: int, roof: str, roof_rows: int, facade: list[list[str]]) -> None:
        width = len(facade[0])
        for row in range(roof_rows):
            for col in range(width):
                ns = "n" if row == 0 else "s" if row == roof_rows - 1 else ""
                ew = "w" if col == 0 else "e" if col == width - 1 else ""
                self.put(x + col, y + row, f"{roof}_{ns}{ew}" if ns or ew else roof)
        for row, names in enumerate(facade):
            self.put(x, y + roof_rows + row, *names)


def village() -> Scene:
    scene = Scene()
    height, width = len(TERRAIN), len(TERRAIN[0])
    for y, row in enumerate(TERRAIN):
        for x, cell in enumerate(row):

            def same(dx: int, dy: int, x: int = x, y: int = y, cell: str = cell) -> bool:
                nx, ny = x + dx, y + dy
                return not (0 <= nx < width and 0 <= ny < height) or TERRAIN[ny][nx] == cell

            terrain = TERRAIN_TILES[cell]
            edged = cell in "GRW"
            scene.ground[x, y] = edge_variant(terrain, same) if edged else terrain
    for x in range(width):
        scene.ground[x, 1] = "road_line_h"
    for x in range(11, 16):
        scene.ground[x, 3] = "tactile_h"
    for y in range(3):
        scene.ground[13, y] = "crosswalk_h"
    for x, y in ((3, 11), (4, 12), (2, 13)):
        scene.ground[x, y] = "grass_flowers"
    for x, y in ((5, 10), (1, 12), (7, 11)):
        scene.ground[x, y] = "grass_tufts"
    scene.ground[22, 11] = "plaza_inlay"

    scene.building(
        1,
        4,
        "roof",
        3,
        [
            ["wall_cream_l", "window_cream", "door_cream_top", "wall_cream_r"],
            ["base_cream_l", "base_window_cream", "door_cream", "base_cream_r"],
        ],
    )
    scene.put(2, 5, "roof_solar")
    scene.put(4, 7, "ac_unit")

    scene.building(
        6,
        4,
        "roof",
        2,
        [
            ["wall_slate_l", "window_slate", "window_slate", "window_slate", "wall_slate_r"],
            ["wall_slate_l", "wall_slate", "wall_slate", "wall_slate", "wall_slate_r"],
            ["shopfront_l", "shopfront", "shopfront_r", "shop_door", "base_slate_r"],
        ],
    )
    scene.put(8, 4, "roof_ac")
    scene.put(6, 8, "awning_red_l", "awning_red", "awning_red_r")
    scene.put(8, 7, "neon_bolt", "neon_24h")
    scene.put(10, 6, "neon_vertical_top")
    scene.put(10, 7, "neon_vertical_bottom")

    scene.building(
        12,
        4,
        "roof_green",
        3,
        [
            ["cafe_wall_l", "cafe_wall", "cafe_sign_l", "cafe_sign_r", "cafe_wall", "cafe_wall_r"],
            ["cafe_window_l", "cafe_window", "cafe_door", "cafe_window", "cafe_window", "cafe_window_r"],
        ],
    )
    scene.put(12, 8, "cafe_awning_l", "cafe_awning_r")
    scene.put(15, 8, "cafe_awning_l", "cafe_awning", "cafe_awning_r")
    scene.put(16, 7, "neon_cup")
    scene.put(12, 9, "cafe_table")
    scene.put(15, 9, "cafe_menu")
    scene.put(16, 9, "cafe_table")

    scene.building(
        20,
        4,
        "roof",
        3,
        [
            ["wall_slate_l", "window_slate", "door_slate_top", "wall_slate", "wall_slate", "wall_slate_r"],
            ["base_slate_l", "base_window_slate", "door_slate", "base_slate", "base_window_slate", "base_slate_r"],
        ],
    )
    scene.put(21, 5, "roof_skylight")
    scene.put(24, 5, "roof_solar")
    scene.put(23, 7, "screen_l", "screen_r")

    scene.put(18, 7, "vending_top")
    scene.put(18, 8, "vending")
    scene.put(19, 8, "bins")
    for x in (0, 11, 19, 27):
        scene.put(x, 8, "lamp_top")
        scene.put(x, 9, "lamp")
    scene.put(6, 9, "bike_yellow", "bike_blue")
    scene.put(26, 9, "bike_yellow")

    scene.put(2, 10, "tree_tl", "tree_tr")
    scene.put(2, 11, "tree_bl", "tree_br")
    scene.put(5, 11, "tree_tl", "tree_tr")
    scene.put(5, 12, "tree_bl", "tree_br")
    scene.put(1, 14, "bush")
    scene.put(4, 14, "bush")
    scene.put(2, 15, "bench_l", "bench_r")
    scene.put(5, 15, "planter_flowers")
    for x in (10, 13, 16):
        scene.put(x, 15, "bollard")
    scene.put(9, 10, "palm_top")
    scene.put(9, 11, "palm")
    scene.put(17, 10, "palm_top")
    scene.put(17, 11, "palm")

    scene.put(22, 12, "fountain_tl", "fountain_tr")
    scene.put(22, 13, "fountain_bl", "fountain_br")
    scene.put(20, 10, "terminal_top")
    scene.put(20, 11, "terminal")
    scene.put(25, 10, "terminal_top")
    scene.put(25, 11, "terminal")
    scene.put(19, 15, "planter")
    scene.put(26, 15, "planter")
    scene.put(21, 15, "bench_l", "bench_r")
    scene.put(24, 15, "bench_l", "bench_r")
    scene.put(0, 16, "planter_flowers")
    scene.put(12, 16, "bike_blue", "bike_yellow")
    return scene


@dataclass(frozen=True)
class Walker:
    appearance: Appearance
    x: int
    y: int
    direction: str
    frame: int = 1


def render_scene(
    scene: Scene, tiles: dict[str, Tile], walkers: Sequence[Walker] = ()
) -> Image.Image:
    width = 1 + max(x for x, _ in scene.ground)
    height = 1 + max(y for _, y in scene.ground)
    canvas = Canvas(width * TILE_SIZE, height * TILE_SIZE)
    for (x, y), name in scene.ground.items():
        canvas.paste(tiles[name].canvas, x * TILE_SIZE, y * TILE_SIZE)
    above = []
    for x, y, name in scene.placements:
        if tiles[name].above:
            above.append((x, y, name))
        else:
            canvas.paste(tiles[name].canvas, x * TILE_SIZE, y * TILE_SIZE)
    for w in sorted(walkers, key=lambda w: w.y):
        canvas.paste(draw_frame(w.appearance, w.direction, w.frame), w.x, w.y - FRAME_HEIGHT)
    for x, y, name in above:
        canvas.paste(tiles[name].canvas, x * TILE_SIZE, y * TILE_SIZE)
    return canvas.to_image()


# Contact sheets


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


def characters_sheet(people: dict[str, Appearance], scale: int = 3) -> Image.Image:
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
    image.alpha_composite(label("CHARACTERS - 1X, 2X, THEN SHEETS AT 3X", scale=3), (margin, margin))
    y = margin + 3 * GLYPH_HEIGHT + 12
    strip = Image.new("RGBA", (len(people) * (FRAME_WIDTH + 4), FRAME_HEIGHT), rgba("pavement"))
    for i, appearance in enumerate(people.values()):
        strip.alpha_composite(draw_frame(appearance, "down", 1).to_image(), (i * (FRAME_WIDTH + 4), 0))
    image.alpha_composite(strip, (margin, y))
    image.alpha_composite(scaled(strip, 2), (margin, y + FRAME_HEIGHT + 8))
    y += actual
    for i, (name, appearance) in enumerate(people.items()):
        x0 = margin + (i % per_row) * pitch_x
        y0 = y + (i // per_row) * pitch_y
        image.alpha_composite(label(name.replace("_", " ")), (x0, y0))
        background = Image.new("RGBA", (sheet_w, sheet_h), rgba("pavement"))
        background.alpha_composite(scaled(sprite_sheet(appearance).to_image(), scale))
        image.alpha_composite(background, (x0, y0 + name_height))
    return image


WALK_CYCLE = (0, 1, 2, 1)


def walk_frames(people: Sequence[Appearance], tile: Tile, scale: int = 3) -> list[Image.Image]:
    gap = 8
    width = len(people) * (FRAME_WIDTH + gap) + gap
    height = FRAME_HEIGHT + 2 * gap
    floor = Canvas(width, height)
    for y in range(0, height, TILE_SIZE):
        for x in range(0, width, TILE_SIZE):
            floor.paste(tile.canvas, x, y)
    frames = []
    for direction in ("down", "left", "up", "right"):
        for _ in range(2):
            for step in WALK_CYCLE:
                c = Canvas(width, height)
                c.paste(floor)
                for i, appearance in enumerate(people):
                    c.paste(draw_frame(appearance, direction, step), gap + i * (FRAME_WIDTH + gap), gap)
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
