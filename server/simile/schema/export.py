import json
from pathlib import Path

from simile.schema import MODELS

JSON_DIR = Path(__file__).parent / "json"


def render() -> dict[str, str]:
    schemas = {model.__name__: model.model_json_schema(mode="serialization") for model in MODELS}
    return {f"{name}.json": json.dumps(schema, indent=2) + "\n" for name, schema in schemas.items()}


def write(directory: Path = JSON_DIR) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    files = render()
    for stale in directory.glob("*.json"):
        if stale.name not in files:
            stale.unlink()
    for name, text in files.items():
        (directory / name).write_text(text)


def outdated(directory: Path = JSON_DIR) -> list[str]:
    files = render()
    existing = {path.name: path.read_text() for path in directory.glob("*.json")}
    return sorted(
        name for name in files.keys() | existing.keys() if files.get(name) != existing.get(name)
    )
