"""Building fronts drawn flat in code, as the plan FLUX redraws in papercraft.

The plan fixes what the painting must keep: the width, the storeys, the door where the map has
it, blank walls where murals go, and where the windows and lamps are, which is all a glow map may
light.
"""

from dataclasses import dataclass, replace
from functools import cache
from typing import Literal

import numpy as np
from PIL import Image, ImageDraw

type Rgb = tuple[int, int, int]
type Roof = Literal["gable", "hip", "flat", "lean"]
type Box = tuple[float, float, float, float]
"""left, bottom, right, top in metres: x from the front's left edge, y up from the ground."""

WINDOW = (1.0, 1.35)
DOOR = (1.1, 2.15)
SILL = 0.95
SHOP_MOST = 8.0
UNIT = 8.6
"""The widest front FLUX redraws faithfully: it keeps to a plan one house wide, and redraws a
wider one as some other building. Wider fronts are a terrace of units, painted one at a time."""
ROOF_RISE = {"gable": 1.9, "hip": 1.5, "flat": 0.55, "lean": 1.3}
EAVES = 0.35
MARGIN = 0.5
GLASS: Rgb = (74, 86, 104)
INSIDE: Rgb = (196, 168, 128)
CURTAIN: Rgb = (232, 222, 200)
GOODS: tuple[Rgb, ...] = ((196, 92, 70), (230, 196, 96), (110, 150, 110), (240, 236, 220))
FRAME: Rgb = (245, 240, 228)
STEP: Rgb = (176, 172, 164)
BACKDROP: Rgb = (255, 255, 255)
GREY: Rgb = (150, 150, 150)


@dataclass(frozen=True)
class Front:
    """A building's front: its size and openings in metres, and its colours."""

    width: float
    storeys: int
    storey: float
    """From one floor to the next."""
    wall_height: float
    door: float | None
    """The door's middle, from the left edge, if it has one."""
    wall: Rgb
    trim: Rgb
    roof: Rgb
    roof_shape: Roof = "gable"
    shutters: Rgb | None = None
    shop: Rgb | None = None
    """Awnings over shop windows on the ground floor, in this colour striped with cream."""
    lanterns: int = 0
    """Round paper lanterns hanging along the ground floor's top."""
    lamp: bool = True
    """A wall lamp beside the door."""
    flower_boxes: Rgb | None = None
    murals: tuple[Box, ...] = ()
    """Blank stretches of wall, kept free of everything, for murals."""
    glass_door: bool = False
    plants: bool = True
    """A potted plant each side of the door, where there's room."""
    window: tuple[float, float] = WINDOW
    """Each window's width and height."""
    awnings: Rgb | None = None
    """Awnings over the ground floor's windows, in this colour striped with cream."""
    one_shop: bool = False
    """In a terrace, only the unit with the door has shop windows, and the others windows
    with awnings: FLUX boards up the middle of a shop window with no door near it."""

    @property
    def rise(self) -> float:
        return ROOF_RISE[self.roof_shape]

    @property
    def total_height(self) -> float:
        return self.wall_height + self.rise

    @property
    def door_box(self) -> Box | None:
        if self.door is None:
            return None
        return (self.door - DOOR[0] / 2, 0.15, self.door + DOOR[0] / 2, 0.15 + DOOR[1])

    def lamp_box(self) -> Box | None:
        if not self.lamp or self.door is None:
            return None
        side = -1 if self.door > self.width / 2 else 1
        x = self.door + side * (DOOR[0] / 2 + 0.35)
        return (x - 0.14, 2.0, x + 0.14, 2.4)

    def shop_boxes(self) -> list[Box]:
        """Shop windows along the ground floor, clear of the door and murals, none wider than
        `SHOP_MOST`."""
        if self.shop is None:
            return []
        blocked = [b for b in (self.door_box, self.lamp_box(), *self.murals) if b]
        boxes = []
        for left, right in _free_spans(self.width, blocked, 0.7, 2.2, 0.4):
            count = int(np.ceil((right - left) / SHOP_MOST))
            step = (right - left) / count
            for i in range(count):
                a, b = left + i * step, left + (i + 1) * step
                if count > 1:
                    a, b = a + (0.3 if i else 0), b - (0.3 if i < count - 1 else 0)
                if b - a >= 1.4:
                    boxes.append((a, 0.7, b, 2.2))
        return boxes

    def window_boxes(self) -> list[Box]:
        """Every window: evenly spaced along each storey, clear of the door, shop windows, lamp
        and murals."""
        boxes = []
        for level in range(self.storeys):
            w, h = self.window
            base = level * self.storey + SILL
            if base + h > self.wall_height - 0.3:
                continue
            blocked = list(self.murals)
            if level == 0:
                blocked += [b for b in (self.door_box, self.lamp_box()) if b]
                blocked += self.shop_boxes()
            for left, right in _free_spans(self.width, blocked, base, base + h, 0.55):
                room = right - left
                n = int((room + 1.6) // (w + 1.6))
                if n <= 0:
                    continue
                gap = room / n
                for i in range(n):
                    middle = left + gap * (i + 0.5)
                    boxes.append((middle - w / 2, base, middle + w / 2, base + h))
        return boxes

    def lamp_boxes(self) -> list[Box]:
        """The lit things that aren't windows: the wall lamp and the lanterns."""
        boxes = [box] if (box := self.lamp_box()) else []
        if self.lanterns:
            top = min(self.storey - 0.55, self.wall_height - 0.3)
            step = self.width / (self.lanterns + 1)
            for i in range(self.lanterns):
                x = step * (i + 1)
                box = (x - 0.22, top - 0.5, x + 0.22, top)
                if not any(_overlaps(box, m) for m in (*self.murals, self.door_box) if m):
                    boxes.append(box)
        return boxes

    def plant_spots(self) -> list[float]:
        """Where potted plants stand, as x in metres."""
        if not self.plants or self.door is None:
            return []
        spots = []
        for x in (self.door - DOOR[0] / 2 - 0.45, self.door + DOOR[0] / 2 + 0.45):
            box = (x - 0.3, 0, x + 0.3, 1.0)
            clear = not any(_overlaps(box, m) for m in self.murals)
            if 0.35 < x < self.width - 0.35 and clear:
                spots.append(x)
        return spots


def _overlaps(a: Box, b: Box) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _free_spans(
    width: float, blocked: list[Box], bottom: float, top: float, pad: float
) -> list[tuple[float, float]]:
    """The stretches of wall between `bottom` and `top` that nothing in `blocked` crosses,
    `pad` clear of it and of the corners."""
    edges = [(pad, pad)]
    for left, low, right, high in blocked:
        if low < top and high > bottom:
            edges.append((left - pad, right + pad))
    edges.append((width - pad, width - pad))
    edges.sort()
    spans = []
    reach = edges[0][1]
    for left, right in edges[1:]:
        if left - reach > 0:
            spans.append((reach, left))
        reach = max(reach, right)
    return spans


@dataclass(frozen=True)
class Plan:
    """A front drawn flat: the picture, its scale, where the front's ground line and left edge
    are in it, and the mask of what can glow at night."""

    image: Image.Image
    glow: Image.Image
    ppm: float
    left: float
    ground: float


def backdrop(front: Front) -> Rgb:
    """White, or grey behind a white building, since white on white defeats the cut-out."""
    return GREY if min(front.wall) > 220 else BACKDROP


def plan_ppm(front: Front, pixels: float = 1.2e6, longest: int = 1536) -> float:
    """Pixels a metre to draw `front` at: about `pixels` in all, at most `longest` across."""
    w = front.width + 2 * (MARGIN + EAVES)
    h = front.total_height + 2 * MARGIN
    return min((pixels / (w * h)) ** 0.5, longest / max(w, h))


def canvas_size(front: Front, ppm: float | None = None) -> tuple[int, int]:
    """The plan's size in px, in multiples of 16."""
    ppm = ppm or plan_ppm(front)
    w = front.width + 2 * (MARGIN + EAVES)
    h = front.total_height + 2 * MARGIN
    return round(w * ppm / 16) * 16, round(h * ppm / 16) * 16


def units(front: Front) -> list[tuple[float, Front]]:
    """`front` as a terrace of units no wider than `UNIT`, each a whole front of its own with
    its own roof, and where each starts. The cuts keep clear of the door, its lamp and murals."""
    count = int(np.ceil(front.width / UNIT))
    keep = [b for b in (front.door_box, front.lamp_box(), *front.murals) if b]
    cuts = [0.0]
    for i in range(1, count):
        x = front.width * i / count
        for left, _, right, _ in keep:
            if left - 0.4 < x < right + 0.4:
                x = left - 0.4 if x - left < right - x else right + 0.4
        cuts.append(x)
    cuts.append(front.width)
    out = []
    for a, b in zip(cuts, cuts[1:], strict=False):
        door = front.door if front.door is not None and a < front.door < b else None
        murals = tuple(
            (max(m[0], a) - a, m[1], min(m[2], b) - a, m[3])
            for m in front.murals
            if m[0] < b and m[2] > a
        )
        unit = replace(
            front,
            width=b - a,
            door=None if door is None else door - a,
            murals=murals,
            lanterns=round(front.lanterns * (b - a) / front.width),
        )
        if front.one_shop and door is None and front.shop:
            unit = replace(unit, shop=None, awnings=front.shop)
        out.append((a, unit))
    return out


@cache
def unit_plans(front: Front) -> tuple[tuple[float, Plan], ...]:
    """Each unit's plan, all at one scale, with where the unit starts."""
    parts = units(front)
    ppm = min(plan_ppm(unit) for _, unit in parts)
    return tuple((x, draw(unit, ppm)) for x, unit in parts)


def draw(front: Front, ppm: float | None = None) -> Plan:
    ppm = ppm or plan_ppm(front)
    size = canvas_size(front, ppm)
    left = (size[0] - front.width * ppm) / 2
    ground = size[1] - MARGIN * ppm
    image = Image.new("RGB", size, backdrop(front))
    glow = Image.new("L", size, 0)
    pen, light = ImageDraw.Draw(image), ImageDraw.Draw(glow)

    def px(box: Box) -> tuple[float, float, float, float]:
        x0, y0, x1, y1 = box
        return (left + x0 * ppm, ground - y1 * ppm, left + x1 * ppm, ground - y0 * ppm)

    def rect(box: Box, fill: Rgb, outline: Rgb | None = None, width: float = 0.06) -> None:
        pen.rectangle(px(box), fill=fill, outline=outline, width=max(1, round(width * ppm)))

    w, top = front.width, front.wall_height
    _roof(pen, front, px)
    rect((0, 0, w, top), front.wall)
    rect((0, 0.15, w, 0.55), _darker(front.wall, 0.88))
    for level in range(1, front.storeys):
        y = level * front.storey - 0.55
        rect((-0.05, y - 0.08, w + 0.05, y + 0.08), front.trim)
    rect((-0.1, top - 0.18, w + 0.1, top), front.trim)
    rect((-0.15, 0, w + 0.15, 0.15), STEP)
    for box in front.window_boxes():
        _window(rect, box, front)
        light.rectangle(px(box), fill=255)
        if front.awnings and box[1] < front.storey:
            _awning(pen, px, (box[0] - 0.3, box[2] + 0.3), box[3] + 0.6, front.awnings)
    for shop in front.shop_boxes():
        _shop(rect, pen, px, shop, front)
        light.rectangle(px(shop), fill=255)
    if door := front.door_box:
        _door(rect, pen, light, px, door, front)
    for x in front.plant_spots():
        _plant(pen, px, x)
    lamp = front.lamp_box()
    for box in front.lamp_boxes():
        if box == lamp:
            rect((box[0] + 0.1, box[1] - 0.05, box[2] - 0.1, box[3] + 0.1), (40, 44, 40))
            pen.ellipse(px(box), fill=(250, 226, 160), outline=(40, 44, 40))
        else:
            x = (box[0] + box[2]) / 2
            rect((x - 0.01, box[3], x + 0.01, box[3] + 0.15), (90, 70, 50))
            pen.ellipse(px(box), fill=(236, 120, 90))
        light.ellipse(px(box), fill=255)
    return Plan(image, glow, ppm, left, ground)


def _door(
    rect, pen: ImageDraw.ImageDraw, light: ImageDraw.ImageDraw, px, door: Box, front: Front
) -> None:
    rect((door[0] - 0.12, door[1], door[2] + 0.12, door[3] + 0.12), _darker(front.wall, 0.8))
    rect(door, front.trim, _darker(front.trim), 0.08)
    rect((door[0] - 0.2, 0.0, door[2] + 0.2, 0.15), _darker(STEP, 0.9))
    knob = door[2] - 0.17
    pen.ellipse(px((knob - 0.05, 1.0, knob + 0.05, 1.1)), fill=(196, 160, 80))
    if front.glass_door:
        glass = (door[0] + 0.18, door[1] + 0.25, door[2] - 0.18, door[3] - 0.2)
        rect(glass, GLASS)
        light.rectangle(px(glass), fill=255)
    else:
        for i in range(2):
            x0 = door[0] + 0.14 + i * (DOOR[0] - 0.28) / 2
            rect((x0 + 0.04, 0.5, x0 + (DOOR[0] - 0.28) / 2 - 0.04, 1.2), _darker(front.trim))
            rect((x0 + 0.04, 1.4, x0 + (DOOR[0] - 0.28) / 2 - 0.04, 2.1), _darker(front.trim))


def _shop(rect, pen: ImageDraw.ImageDraw, px, shop: Box, front: Front) -> None:
    x0, y0, x1, y1 = shop
    rect(shop, INSIDE, front.trim, 0.12)
    for shelf in (y0 + 0.55, y0 + 1.0):
        rect((x0 + 0.12, shelf - 0.04, x1 - 0.12, shelf), _darker(INSIDE, 0.6))
        for i, gx in enumerate(np.arange(x0 + 0.25, x1 - 0.3, 0.32)):
            rect((gx, shelf, gx + 0.18, shelf + 0.2), GOODS[i % len(GOODS)])
    rect((x0 + 0.12, y0 + 0.1, x1 - 0.12, y0 + 0.32), _darker(front.trim, 0.9))
    panes = max(2, round((x1 - x0) / 1.1))
    for i in range(1, panes):
        x = x0 + (x1 - x0) * i / panes
        rect((x - 0.04, y0, x + 0.04, y1), front.trim)
    if front.shop:
        _awning(pen, px, (x0 - 0.25, x1 + 0.25), y1 + 0.65, front.shop)


def _plant(pen: ImageDraw.ImageDraw, px, x: float) -> None:
    for angle in (-62, -38, -14, 10, 34, 58):
        a = np.radians(angle)
        tip = (x + 0.62 * np.sin(a), 0.5 + 0.7 * np.cos(a))
        side = (0.1 * np.cos(a), -0.1 * np.sin(a))
        mid = ((x + tip[0]) / 2, (0.52 + tip[1]) / 2)
        shape = [(x, 0.52), (mid[0] + side[0], mid[1] + side[1]), tip]
        shape.append((mid[0] - side[0], mid[1] - side[1]))
        green = (86, 136, 84) if angle % 20 else (110, 156, 96)
        pen.polygon([px((u, v, u, v))[:2] for u, v in shape], fill=green)
    l0, t0, r0, b0 = px((x - 0.22, 0.15, x + 0.22, 0.55))
    inset = (r0 - l0) * 0.15
    pen.polygon([(l0, t0), (r0, t0), (r0 - inset, b0), (l0 + inset, b0)], fill=(184, 104, 74))


def _window(rect, box: Box, front: Front) -> None:
    x0, y0, x1, y1 = box
    rect((x0 - 0.14, y1 + 0.08, x1 + 0.14, y1 + 0.2), _darker(front.wall, 0.8))
    rect((x0 - 0.08, y0 - 0.08, x1 + 0.08, y1 + 0.08), FRAME)
    rect(box, GLASS)
    rect((x0, y0, x0 + 0.2, y1), CURTAIN)
    rect((x1 - 0.2, y0, x1, y1), CURTAIN)
    rect((x0 - 0.16, y0 - 0.16, x1 + 0.16, y0 - 0.06), front.trim)
    panes = max(2, round((x1 - x0) / 0.6))
    for i in range(1, panes):
        x = x0 + (x1 - x0) * i / panes
        rect((x - 0.035, y0, x + 0.035, y1), FRAME)
    mid_y = y0 + (y1 - y0) * 0.55
    rect((x0, mid_y - 0.035, x1, mid_y + 0.035), FRAME)
    if front.shutters:
        rect((x0 - 0.5, y0 - 0.05, x0 - 0.1, y1 + 0.05), front.shutters, _darker(front.shutters))
        rect((x1 + 0.1, y0 - 0.05, x1 + 0.5, y1 + 0.05), front.shutters, _darker(front.shutters))
    if front.flower_boxes:
        rect((x0 - 0.12, y0 - 0.3, x1 + 0.12, y0 - 0.08), front.flower_boxes)


def _awning(pen: ImageDraw.ImageDraw, px, span: tuple[float, float], y: float, colour: Rgb) -> None:
    x0, x1 = span
    stripes = max(4, round((x1 - x0) / 0.32))
    for i in range(stripes):
        a = x0 + (x1 - x0) * i / stripes
        b = x0 + (x1 - x0) * (i + 1) / stripes
        fill = colour if i % 2 == 0 else (244, 236, 216)
        l0, t0, r0, b0 = px((a, y - 0.6, b, y))
        pen.polygon([(l0, t0), (r0, t0), (r0, b0), (l0, b0)], fill=fill)
        pen.pieslice((l0, b0 - (r0 - l0) / 2, r0, b0 + (r0 - l0) / 2), 0, 180, fill=fill)


def _roof(pen: ImageDraw.ImageDraw, front: Front, px) -> None:
    w, top, rise = front.width, front.wall_height, front.rise
    colour, dark = front.roof, _darker(front.roof)
    if front.roof_shape == "flat":
        l0, t0, r0, b0 = px((-0.2, top, w + 0.2, top + rise))
        pen.rectangle((l0, t0, r0, b0), fill=colour, outline=dark, width=2)
        return
    slope = min(w * 0.22, rise * 1.6)
    corners = {
        "gable": [(-EAVES, top), (w / 2, top + rise), (w + EAVES, top)],
        "hip": [(-EAVES, top), (slope, top + rise), (w - slope, top + rise), (w + EAVES, top)],
        "lean": [(-EAVES, top), (-EAVES, top + rise), (w + EAVES, top + rise * 0.35)],
    }[front.roof_shape]
    points = [px((x, y, x, y))[:2] for x, y in corners]
    pen.polygon(points, fill=colour, outline=dark, width=3)
    inside = Image.new("L", pen.im.size, 0)
    ImageDraw.Draw(inside).polygon(points, fill=255)
    lines = Image.new("L", pen.im.size, 0)
    ruler = ImageDraw.Draw(lines)
    for y in np.arange(top + 0.32, top + rise, 0.32):
        t0 = px((0, y, 0, y))[1]
        ruler.line((0, t0, pen.im.size[0], t0), fill=255, width=2)
    pen.bitmap(
        (0, 0), Image.fromarray(np.minimum(np.asarray(inside), np.asarray(lines))), fill=dark
    )


def _darker(rgb: Rgb, by: float = 0.72) -> Rgb:
    return (round(rgb[0] * by), round(rgb[1] * by), round(rgb[2] * by))
