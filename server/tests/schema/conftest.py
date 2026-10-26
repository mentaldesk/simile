import json
from pathlib import Path
from typing import Any

DOOR: dict[str, Any] = {
    "id": "coffee_shop",
    "outside": {"map": "village", "x": 31, "y": 13},
    "inside": {"map": "coffee_shop", "x": 10, "y": 12},
}
COUNTER: dict[str, Any] = {
    "id": "coffee_shop_counter",
    "label": "Counter",
    "kind": "counter",
    "map": "coffee_shop",
    "area": {"x": 6, "y": 4, "width": 6, "height": 1},
    "stand": [{"x": 9, "y": 6}],
}
SEARCHABLES: list[dict[str, Any]] = json.loads(
    (Path(__file__).parent / "searchables.json").read_text()
)
