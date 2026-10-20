from collections.abc import Sequence

from PIL import Image, ImageDraw, ImageFont

from simile.schema import DoorKind, Facing, TileArea
from simile.street.plan import MARKERS, TILE_SIZE, Plan
from simile.street.village import GROUND, STOREY
from simile.world.map import MapKind

SCALE = 16
COLOURS = {
    "sky": (223, 233, 243, 255),
    "ground": (138, 107, 74, 255),
    "path": (247, 243, 232, 255),
    "front": (201, 193, 180, 255),
    "wall": (109, 106, 117, 255),
    "room": (239, 230, 214, 255),
    "floor": (255, 248, 232, 255),
    "stairs": (242, 193, 78, 255),
    "ladder": (224, 122, 46, 255),
    "lift": (214, 51, 132, 255),
    "door": (60, 180, 75, 255),
    "spot": (142, 68, 173, 255),
    "entry": (255, 212, 0, 255),
    "mural": (0, 190, 210, 110),
    "mural_edge": (0, 150, 170, 255),
    "item": (245, 130, 48, 255),
    "place": (42, 157, 143, 255),
    "ink": (30, 30, 40, 255),
    "blocked": (220, 60, 60, 120),
    "furniture": (150, 140, 128, 255),
}
COLOURS["solid"] = COLOURS["ground"]
LINKS = {DoorKind.STAIRS: "stairs", DoorKind.LADDER: "ladder", DoorKind.LIFT: "lift"}
TICKS = {Facing.EAST: (1, 0), Facing.WEST: (-1, 0), Facing.NORTH: (0, -1), Facing.SOUTH: (0, 1)}


def markers() -> Image.Image:
    """The tileset the maps' tile layers use, so Tiled shows them."""
    image = Image.new("RGBA", (TILE_SIZE * len(MARKERS), TILE_SIZE))
    draw = ImageDraw.Draw(image)
    for i, name in enumerate(MARKERS):
        x0, x1 = i * TILE_SIZE, (i + 1) * TILE_SIZE - 1
        draw.rectangle((x0, 0, x1, TILE_SIZE - 1), fill=COLOURS[name], outline=COLOURS["ink"])
        if name == "stairs":
            for step in range(0, TILE_SIZE, 4):
                draw.line(
                    (x0 + step, TILE_SIZE - 1 - step, x0 + step + 4, TILE_SIZE - 1 - step),
                    fill=COLOURS["ink"],
                )
        elif name == "ladder":
            draw.line((x0 + 4, 0, x0 + 4, TILE_SIZE), fill=COLOURS["ink"])
            draw.line((x1 - 4, 0, x1 - 4, TILE_SIZE), fill=COLOURS["ink"])
            for rung in range(2, TILE_SIZE, 5):
                draw.line((x0 + 4, rung, x1 - 4, rung), fill=COLOURS["ink"])
    return image


def render(plans: Sequence[Plan]) -> Image.Image:
    """Every street, with its buildings' floors drawn in place, its links, spots, entries,
    mural walls and things to use, one under another with their names."""
    streets = [plan for plan in plans if plan.kind is MapKind.STREET]
    floors = [plan for plan in plans if plan.kind is MapKind.FLOOR]
    width = max(street.width for street in streets) * SCALE
    height = sum((street.height + 2) * SCALE for street in streets)
    image = Image.new("RGBA", (width, height), COLOURS["ink"])
    top = 0
    for street in streets:
        panel = Panel(image, top + SCALE * 2)
        panel.street(street, [f for f in floors if f.properties["street"] == street.id])
        panel.label(street.properties["label"].upper(), 4, top + 4, "floor")
        top += (street.height + 2) * SCALE
    return image


class Panel:
    def __init__(self, image: Image.Image, top: int) -> None:
        self.image, self.top = image, top
        self.draw = ImageDraw.Draw(image, "RGBA")
        self.draw.fontmode = "1"
        self.font = ImageFont.load_default(size=10)

    def box(self, x: float, y: float, width: float = 1, height: float = 1) -> tuple[float, ...]:
        x0, y0 = x * SCALE, self.top + y * SCALE
        return x0, y0, x0 + width * SCALE - 1, y0 + height * SCALE - 1

    def cell(self, x: int, y: int, colour: str, inset: int = 0) -> None:
        x0, y0, x1, y1 = self.box(x, y)
        self.draw.rectangle((x0 + inset, y0 + inset, x1 - inset, y1 - inset), fill=COLOURS[colour])

    def outline(
        self, area: TileArea, colour: str, dx: int = 0, dy: int = 0, width: int = 2
    ) -> None:
        box = self.box(area.x + dx, area.y + dy, area.width, area.height)
        self.draw.rectangle(box, outline=COLOURS[colour], width=width)

    def label(self, text: str, x: float, y: float, background: str = "floor") -> None:
        left, upper, right, lower = self.draw.textbbox((x, y), text, font=self.font)
        self.draw.rectangle((left - 2, upper - 2, right + 2, lower + 2), fill=COLOURS[background])
        self.draw.text((x, y), text, fill=COLOURS["ink"], font=self.font)

    def middle(self, x: float, y: float, dx: int = 0, dy: int = 0) -> tuple[float, float]:
        return (x + dx + 0.5) * SCALE, self.top + (y + dy + 0.5) * SCALE

    def street(self, street: Plan, floors: Sequence[Plan]) -> None:
        for y in range(street.height):
            for x in range(street.width):
                solid, path = (x, y) in street.solid, street.walkable(x, y)
                self.cell(x, y, "ground" if solid else "path" if path else "sky")
        for facade in street.buildings:
            if not facade.interior:
                x0, y0, x1, y1 = self.box(
                    facade.area.x, facade.area.y, facade.area.width, facade.area.height - 1
                )
                self.draw.rectangle(
                    (x0, y0, x1, y1), fill=COLOURS["front"], outline=COLOURS["wall"]
                )
        placed = {f.id: (f.properties["street_x"], f.properties["street_y"]) for f in floors}
        for floor in floors:
            self.plan(floor, *placed[floor.id])
        self.plan(street, 0, 0, cells=False)
        for floor in floors:
            for door in floor.doors:
                if door.kind is not DoorKind.DOOR and door.outside.map == floor.id:
                    a = self.middle(door.outside.x, door.outside.y, *placed[door.outside.map])
                    b = self.middle(door.inside.x, door.inside.y, *placed[door.inside.map])
                    self.draw.line((*a, *b), fill=COLOURS[LINKS[door.kind]], width=3)
        notes = []
        for wall in street.murals:
            bottom, top = (GROUND + 1 - s * STOREY for s in (wall.bottom, wall.top))
            x0, y0, x1, y1 = self.box(wall.x, top, wall.width, bottom - top)
            self.draw.rectangle(
                (x0, y0, x1, y1), fill=COLOURS["mural"], outline=COLOURS["mural_edge"]
            )
            notes.append((wall.x, f"MURAL {wall.id.upper()}", "mural_edge"))
        for facade in street.buildings:
            self.label(
                facade.id.upper(),
                facade.area.x * SCALE + 2,
                self.top + facade.area.y * SCALE - 14,
                "front",
            )
        for door in street.doors:
            ends = (door.outside, door.inside)
            here, there = ends if door.outside.map == street.id else ends[::-1]
            if there.map not in placed:
                notes.append((here.x, f"TO {there.map.upper()}", "door"))
        self.underground(sorted(notes))

    def underground(self, notes: Sequence[tuple[int, str, str]]) -> None:
        """Labels in the ground under the cells they name, in rows so none overlap."""
        rows: list[float] = []
        for x, text, colour in notes:
            left = x * SCALE + 2
            width = self.draw.textlength(text, font=self.font)
            row = next((i for i, end in enumerate(rows) if end < left), len(rows))
            rows[row : row + 1] = [left + width + 8]
            y = self.top + (GROUND + 2) * SCALE + 2 + row * 15
            self.draw.line((left - 2, y - 4, left - 2, y + 10), fill=COLOURS[colour], width=2)
            self.label(text, left + 2, y, "path")

    def plan(self, plan: Plan, dx: int, dy: int, cells: bool = True) -> None:
        if cells:
            for y in range(plan.height):
                for x in range(plan.width):
                    solid, standing = (x, y) in plan.solid, plan.walkable(x, y)
                    self.cell(x + dx, y + dy, "wall" if solid else "floor" if standing else "room")
        for (x, y), kind in plan.climbable.items():
            self.cell(x + dx, y + dy, LINKS[kind], inset=2)
        for piece in plan.furniture:
            self.outline(piece.area, "furniture", dx, dy, width=1)
        for location in plan.locations:
            self.outline(location.area, "place", dx, dy)
        for item in plan.interactables:
            self.outline(item.area, "item", dx, dy)
        for door in plan.doors:
            for end in (door.outside, door.inside):
                if end.map == plan.id:
                    colour = "door" if door.kind is DoorKind.DOOR else LINKS[door.kind]
                    self.outline(TileArea(x=end.x, y=end.y, width=1, height=1), colour, dx, dy)
        for location in plan.locations:
            self.cell(location.entry.x + dx, location.entry.y + dy, "entry", inset=5)
        for spot in plan.spots:
            cx, cy = self.middle(spot.x, spot.y, dx, dy)
            tx, ty = TICKS[spot.facing]
            reach, r = SCALE * 0.45, 3
            self.draw.line(
                (cx, cy, cx + tx * reach, cy + ty * reach), fill=COLOURS["spot"], width=2
            )
            self.draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=COLOURS["spot"])
