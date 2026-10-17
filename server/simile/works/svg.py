import math
import re
import xml.etree.ElementTree as ET

SVG = "http://www.w3.org/2000/svg"
XLINK = "http://www.w3.org/1999/xlink"
ELEMENTS = frozenset(
    {
        "svg",
        "g",
        "defs",
        "title",
        "desc",
        "style",
        "symbol",
        "use",
        "path",
        "rect",
        "circle",
        "ellipse",
        "line",
        "polyline",
        "polygon",
        "text",
        "tspan",
        "textPath",
        "linearGradient",
        "radialGradient",
        "stop",
        "pattern",
        "clipPath",
        "mask",
        "filter",
        "feBlend",
        "feColorMatrix",
        "feComponentTransfer",
        "feComposite",
        "feDisplacementMap",
        "feDropShadow",
        "feFlood",
        "feFuncA",
        "feFuncB",
        "feFuncG",
        "feFuncR",
        "feGaussianBlur",
        "feMerge",
        "feMergeNode",
        "feMorphology",
        "feOffset",
        "feTurbulence",
    }
)
EXTERNAL_URL = re.compile(r"url\((?!\s*['\"]?\s*#)", re.IGNORECASE)
LOCAL_URL = re.compile(r"url\(\s*['\"]?\s*#([^'\")\s]+)", re.IGNORECASE)
NUMBER = r"\s*(-?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?)\s*,?"
VIEWBOX = re.compile(rf"^{NUMBER * 4}\s*$", re.IGNORECASE)
BARE_AMPERSAND = re.compile(r"&(?!#\d+;|#x[0-9a-fA-F]+;|[A-Za-z]\w*;)")
TRANSFORM = re.compile(r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)", re.IGNORECASE)
LEADING_NUMBER = re.compile(r"^\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?)", re.IGNORECASE)
SIZES = frozenset(
    {"x", "y", "width", "height", "r", "rx", "ry", "cx", "cy", "x1", "y1", "x2", "y2"}
    | {"fx", "fy", "fr", "stroke-width", "font-size"}
)

DEPTH = 32
USES = 200
REFERENCES = 4
SCALES = (1 / 1000, 20.0)
SIZE = 10
TILE = 2

type Matrix = tuple[float, float, float, float]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0)
CLAMPED = {("feTurbulence", "numOctaves"): 8.0, ("feMorphology", "radius"): 20.0}

ET.register_namespace("", SVG)
ET.register_namespace("xlink", XLINK)


class BadSvg(ValueError):
    """Why a mural's SVG can't be used, in words the painter can act on."""


def local(name: str) -> str:
    return name.rpartition("}")[2]


def checked(
    svg: str, width: int, height: int, *, chars: int, elements: int, tolerance: float
) -> str:
    """`svg` cleaned up to render at `width` × `height` px, or `BadSvg` if it's too big, not
    roughly that shape, or has anything in it that could run or load something."""
    if len(svg) > chars:
        raise BadSvg(f"it's {len(svg):,} characters long, and the most is {chars:,}")
    if re.search(r"<!(DOCTYPE|ENTITY)", svg, re.IGNORECASE):
        raise BadSvg("it has a DOCTYPE or ENTITY declaration")
    try:
        root = ET.fromstring(BARE_AMPERSAND.sub("&amp;", svg.strip()))
    except ET.ParseError as error:
        raise BadSvg(f"it isn't well-formed XML ({error})") from None
    every = list(root.iter())
    if len(every) > elements:
        raise BadSvg(f"it has {len(every):,} elements, and the most is {elements:,}")
    if _depth(root) > DEPTH:
        raise BadSvg(f"its elements are nested more than {DEPTH} deep")
    try:
        for element in every:
            _check(element)
        if local(root.tag) != "svg":
            raise BadSvg("its root element isn't <svg>")
        view = _fit(root, width, height, tolerance)
        _check_geometry(root, view, max(width, height))
        _check_references(every)
        return ET.tostring(root, encoding="unicode")
    except RecursionError:
        raise BadSvg("its elements or references are nested too deep") from None


def _depth(root: ET.Element) -> int:
    deepest, stack = 0, [(root, 1)]
    while stack:
        element, depth = stack.pop()
        deepest = max(deepest, depth)
        stack.extend((child, depth + 1) for child in element)
    return deepest


def _check(element: ET.Element) -> None:
    namespace, _, name = element.tag.rpartition("}")
    if namespace.lstrip("{") not in ("", SVG) or name not in ELEMENTS:
        raise BadSvg(f"<{name}> isn't allowed")
    element.tag = f"{{{SVG}}}{name}"
    for attribute, value in element.attrib.items():
        key = local(attribute)
        if key.lower().startswith("on"):
            raise BadSvg(f"event handlers like {key} aren't allowed")
        if key == "href" and not value.strip().startswith("#"):
            raise BadSvg(f'href="{value[:40]}" points outside the SVG')
        if EXTERNAL_URL.search(value):
            raise BadSvg(f'{key}="{value[:40]}" refers to something outside the SVG')
        if key == "style":
            _check_css(value)
        if (most := CLAMPED.get((name, key))) is not None:
            element.set(attribute, _clamp(key, value, most))
    if name == "style":
        if len(element):
            raise BadSvg("its <style> has elements in it")
        _check_css(element.text or "")


def _check_css(css: str) -> None:
    if "\\" in css:
        raise BadSvg("CSS escapes aren't allowed")
    if EXTERNAL_URL.search(css) or "@import" in css.lower():
        raise BadSvg("its CSS loads something from outside the SVG")
    if "transform" in css.lower():
        raise BadSvg("transforms belong in transform attributes, not CSS")


def _clamp(key: str, value: str, most: float) -> str:
    try:
        numbers = [float(number) for number in value.replace(",", " ").split()]
    except ValueError:
        raise BadSvg(f"{key}={value[:40]!r} isn't a number") from None
    return " ".join(f"{min(abs(number), most):g}" for number in numbers)


def _check_references(every: list[ET.Element]) -> None:
    """No duplicate ids, few `<use>`s, none reaching another, and no long chains of references,
    each of which can take resvg exponentially longer to draw."""
    ids: dict[str, ET.Element] = {}
    for element in every:
        if (id := element.get("id")) is not None:
            if id in ids:
                raise BadSvg(f'the id "{id[:40]}" is used twice')
            ids[id] = element
    uses = [element for element in every if local(element.tag) == "use"]
    if len(uses) > USES:
        raise BadSvg(f"it has {len(uses)} <use> elements, and the most is {USES}")
    for use in uses:
        target = ids.get(_href(use))
        if target is not None and any(local(e.tag) == "use" for e in target.iter()):
            raise BadSvg("a <use> refers to something with another <use> in it")
    hops: dict[str, int] = {}

    def chain(id: str, path: tuple[str, ...]) -> int:
        if id in path:
            raise BadSvg(f'"{id[:40]}" refers to itself')
        if len(path) >= REFERENCES:
            raise BadSvg(f"it has references to references more than {REFERENCES} deep")
        if id not in hops:
            onward = [chain(ref, (*path, id)) for ref in _references(ids[id]) if ref in ids]
            hops[id] = 1 + max(onward, default=0)
        if len(path) + hops[id] > REFERENCES:
            raise BadSvg(f"it has references to references more than {REFERENCES} deep")
        return hops[id]

    for element in every:
        for ref in _references(element, subtree=False):
            if ref in ids:
                chain(ref, ())


def _href(element: ET.Element) -> str:
    href = next((v for k, v in element.attrib.items() if local(k) == "href"), "")
    return href.strip().removeprefix("#")


def _references(element: ET.Element, subtree: bool = True) -> set[str]:
    found: set[str] = set()
    for each in element.iter() if subtree else [element]:
        if href := _href(each):
            found.add(href)
        for value in [*each.attrib.values(), each.text or "" if local(each.tag) == "style" else ""]:
            found.update(LOCAL_URL.findall(value))
    return found


def _check_geometry(root: ET.Element, view: tuple[float, float], pixels: int) -> None:
    """No transform that scales by more than 20 or less than 1/1000, no size over 10 times the
    viewBox, and no pattern whose tile could be drawn bigger than twice the wall: resvg draws a
    pattern's tile whole, however big it gets."""
    largest, to_pixels = max(view), pixels / max(view)
    most, patterns = 1.0, []
    stack = [(root, IDENTITY)]
    while stack:
        element, outer = stack.pop()
        name = local(element.tag)
        if element is not root:
            if name == "svg":
                raise BadSvg("only the outermost element may be an <svg>")
            if "viewBox" in element.attrib:
                raise BadSvg("only the outermost <svg> may have a viewBox")
            for key in SIZES & element.attrib.keys():
                _check_size(key, element.attrib[key], SIZE * largest)
        matrix = _times(outer, _transform(element.get("transform", "")))
        most = max(most, _scaled(matrix, element.get("transform", "")))
        if name == "pattern":
            patterns.append(element)
        stack.extend((child, matrix) for child in element)
    for pattern in patterns:
        moved = pattern.get("patternTransform", "")
        tile = max(_size(pattern.get("width", "0")), _size(pattern.get("height", "0")))
        if pattern.get("patternUnits") != "userSpaceOnUse":
            if tile > 1:
                raise BadSvg("a pattern's tile is bigger than what it fills")
            tile *= largest
        elif tile > largest:
            raise BadSvg("a pattern's tile is bigger than the wall")
        if tile * _scaled(_transform(moved), moved) * most * to_pixels > TILE * pixels:
            raise BadSvg("a pattern's tile would be drawn bigger than the wall")


def _transform(text: str) -> Matrix:
    matrix = IDENTITY
    for name, arguments in TRANSFORM.findall(text):
        try:
            n = [float(number) for number in re.split(r"[\s,]+", arguments.strip()) if number]
        except ValueError:
            raise BadSvg(f"transform={text[:40]!r} isn't a transform") from None
        if not all(math.isfinite(number) for number in n):
            raise BadSvg(f"transform={text[:40]!r} has a number that isn't finite")
        match name.lower(), len(n):
            case "matrix", 6:
                step = (n[0], n[1], n[2], n[3])
            case "translate", 1 | 2:
                step = IDENTITY
            case "scale", 1 | 2:
                step = (n[0], 0.0, 0.0, n[-1])
            case "rotate", 1 | 3:
                turn = math.radians(n[0])
                step = (math.cos(turn), math.sin(turn), -math.sin(turn), math.cos(turn))
            case "skewx", 1:
                step = (1.0, 0.0, math.tan(math.radians(n[0])), 1.0)
            case "skewy", 1:
                step = (1.0, math.tan(math.radians(n[0])), 0.0, 1.0)
            case _:
                raise BadSvg(f"transform={text[:40]!r} isn't a transform")
        matrix = _times(matrix, step)
    return matrix


def _times(first: Matrix, then: Matrix) -> Matrix:
    a1, b1, c1, d1 = first
    a2, b2, c2, d2 = then
    return (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2, a1 * c2 + c1 * d2, b1 * c2 + d1 * d2)


def _scaled(matrix: Matrix, text: str) -> float:
    """How much `matrix` stretches anything at most, or `BadSvg` if it's too much or too little."""
    a, b, c, d = matrix
    q, r = math.hypot((a + d) / 2, (b - c) / 2), math.hypot((a - d) / 2, (b + c) / 2)
    least, most = SCALES
    if not (q + r <= most and abs(q - r) >= least):
        raise BadSvg(
            f"transform={text[:40]!r} scales things by more than {most:g} or less than {least:g}"
        )
    return q + r


def _size(value: str) -> float:
    match = LEADING_NUMBER.match(value)
    number = float(match[1]) if match else 0.0
    return number / 100 if value.strip().endswith("%") else number


def _check_size(key: str, value: str, most: float) -> None:
    match = LEADING_NUMBER.match(value)
    if match and not abs(float(match[1])) <= most:
        raise BadSvg(f"{key}={value[:40]!r} is far bigger than the wall")


def _fit(root: ET.Element, width: int, height: int, tolerance: float) -> tuple[float, float]:
    match = VIEWBOX.match(root.get("viewBox", ""))
    if not match:
        raise BadSvg(f'it needs viewBox="0 0 {width} {height}"')
    view_width, view_height = float(match[3]), float(match[4])
    if view_width <= 0 or view_height <= 0:
        raise BadSvg("its viewBox has no area")
    if abs(view_width / view_height / (width / height) - 1) > tolerance:
        raise BadSvg(
            f"its viewBox is {view_width:g} × {view_height:g}, not the wall's shape: "
            f'use viewBox="0 0 {width} {height}"'
        )
    root.set("width", str(width))
    root.set("height", str(height))
    root.set("preserveAspectRatio", "xMidYMid slice")
    return view_width, view_height
