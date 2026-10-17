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
NUMBER = r"\s*(-?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?)\s*,?"
VIEWBOX = re.compile(rf"^{NUMBER * 4}\s*$", re.IGNORECASE)

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
        root = ET.fromstring(svg.strip())
    except ET.ParseError as error:
        raise BadSvg(f"it isn't well-formed XML ({error})") from None
    every = list(root.iter())
    if len(every) > elements:
        raise BadSvg(f"it has {len(every):,} elements, and the most is {elements:,}")
    for element in every:
        _check(element)
    if local(root.tag) != "svg":
        raise BadSvg("its root element isn't <svg>")
    _no_nested_use(every)
    _fit(root, width, height, tolerance)
    return ET.tostring(root, encoding="unicode")


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
    style = element.text or ""
    if name == "style" and (EXTERNAL_URL.search(style) or "@import" in style.lower()):
        raise BadSvg("its <style> loads something from outside the SVG")


def _no_nested_use(every: list[ET.Element]) -> None:
    ids = {element.get("id"): element for element in every if element.get("id")}
    for element in every:
        if local(element.tag) != "use":
            continue
        href = next((v for k, v in element.attrib.items() if local(k) == "href"), "")
        target = ids.get(href.strip().removeprefix("#"))
        if target is not None and any(local(e.tag) == "use" for e in target.iter()):
            raise BadSvg("a <use> refers to something with another <use> in it")


def _fit(root: ET.Element, width: int, height: int, tolerance: float) -> None:
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
