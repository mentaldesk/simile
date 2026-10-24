"""What the side-view maps say the scenery must fit: each street, each building's front and
floors, and each piece of furniture's size.

`layout.json` is the copy the scenery was painted to. `simile papercraft` refreshes it from
content/street/ when that's there, so a change to the maps repaints only what it moves.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

CONTENT = Path(__file__).resolve().parents[3] / "content"
STREET_DIR = CONTENT / "street"
LAYOUT = CONTENT / "papercraft" / "layout.json"
TILE_PX = 16


@dataclass(frozen=True)
class Mural:
    x: int
    """Tiles from the front's left edge."""
    width: int
    bottom: float
    top: float


@dataclass(frozen=True)
class Facade:
    """A building's front on its street, in tiles: `height` from the ground line up to where
    its roof starts."""

    id: str
    street: str
    x: int
    width: int
    height: int
    storeys: int
    interior: bool
    door: int | None = None
    """The door's tile, from the front's left edge."""
    murals: tuple[Mural, ...] = ()


@dataclass(frozen=True)
class Layout:
    streets: dict[str, int]
    """Each street's width in tiles."""
    facades: dict[str, Facade]
    rooms: dict[str, tuple[str, ...]]
    """Each building's rooms, a floor each, ground floor first."""
    furniture: dict[str, tuple[int, int]]
    """Each piece of furniture's largest width and height in tiles on any map."""
    links: tuple[str, ...] = field(default=())
    """The kinds of link and climb the maps use: stairs, ladder, lift."""


def _props(obj: dict[str, Any]) -> dict[str, Any]:
    return {p["name"]: p["value"] for p in obj.get("properties", [])}


def _objects(data: dict[str, Any], layer: str) -> list[dict[str, Any]]:
    for each in data["layers"]:
        if each["name"] == layer:
            return each.get("objects", [])
    return []


def _tiles(obj: dict[str, Any]) -> tuple[int, int, int, int]:
    x, y, w, h = (round(obj[k] / TILE_PX) for k in ("x", "y", "width", "height"))
    return x, y, w, h


def read_maps(directory: Path = STREET_DIR) -> Layout:
    """The layout of the side-view maps in `directory`, its `floors/` and every generated level,
    whose maps share their ids: a street is as wide as its widest level."""
    maps = [(p.stem, json.loads(p.read_text())) for p in sorted(directory.rglob("*.tmj"))]
    streets, facades, rooms = {}, {}, {}
    furniture: dict[str, tuple[int, int]] = {}
    links: set[str] = set()
    floors: dict[str, dict[int, str]] = {}
    for map_id, data in maps:
        props = _props(data)
        if props.get("kind") == "floor":
            floors.setdefault(props["building"], {})[props["floor"]] = props["room"]
        for obj in _objects(data, "furniture"):
            _, _, w, h = _tiles(obj)
            old = furniture.get(obj["name"], (0, 0))
            furniture[obj["name"]] = (max(old[0], w), max(old[1], h))
        for obj in _objects(data, "doors"):
            kind = _props(obj).get("kind", "door")
            if kind != "door":
                links.add(kind)
        for layer in data["layers"]:
            if layer["name"] == "climbable" and any(layer.get("data", [])):
                tiles = {t["id"] + 1: _props(t)["name"] for t in data["tilesets"][0]["tiles"]}
                links |= {tiles[gid] for gid in set(layer["data"]) if gid}
        if props.get("kind") != "street":
            continue
        streets[map_id] = max(streets.get(map_id, 0), data["width"])
        doors = {
            o["name"]: _tiles(o)[0]
            for o in _objects(data, "doors")
            if _props(o)["side"] == "outside"
        }
        murals = [(_tiles(o), _props(o)) for o in _objects(data, "murals")]
        for obj in _objects(data, "buildings"):
            x, _, width, height = _tiles(obj)
            fprops = _props(obj)
            facades[obj["name"]] = Facade(
                id=obj["name"],
                street=map_id,
                x=x,
                width=width,
                height=height,
                storeys=fprops["storeys"],
                interior=fprops["interior"],
                door=doors[obj["name"]] - x if obj["name"] in doors else None,
                murals=tuple(
                    Mural(mx - x, mw, p["bottom"], p["top"])
                    for (mx, _, mw, _), p in murals
                    if x <= mx < x + width
                ),
            )
    for building, by_floor in floors.items():
        rooms[building] = tuple(by_floor[n] for n in sorted(by_floor))
    return Layout(streets, facades, rooms, dict(sorted(furniture.items())), tuple(sorted(links)))


def dumps(layout: Layout) -> str:
    return json.dumps(asdict(layout), indent=1, sort_keys=True) + "\n"


def loads(text: str) -> Layout:
    data = json.loads(text)
    facades = {
        k: Facade(**{**v, "murals": tuple(Mural(**m) for m in v["murals"])})
        for k, v in data["facades"].items()
    }
    return Layout(
        streets=data["streets"],
        facades=facades,
        rooms={k: tuple(v) for k, v in data["rooms"].items()},
        furniture={k: (w, h) for k, (w, h) in data["furniture"].items()},
        links=tuple(data["links"]),
    )


def load_layout(path: Path = LAYOUT) -> Layout:
    return loads(path.read_text())


def refresh(directory: Path = STREET_DIR, path: Path = LAYOUT) -> bool:
    """Copy the maps' layout into `path` if they're there and it changed. True if it did."""
    if not directory.is_dir():
        return False
    text = dumps(read_maps(directory))
    if path.exists() and path.read_text() == text:
        return False
    path.write_text(text)
    return True
