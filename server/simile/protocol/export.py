import json
from pathlib import Path

from pydantic import TypeAdapter
from pydantic.json_schema import GenerateJsonSchema
from pydantic_core import CoreSchema

from simile.protocol.messages import Message

SCHEMA_FILE = Path(__file__).parent / "protocol.schema.json"


class WithoutFieldTitles(GenerateJsonSchema):
    """Field titles would become a named TypeScript alias for every property."""

    def field_title_should_be_set(self, schema: CoreSchema) -> bool:
        return False


def render() -> str:
    schema = TypeAdapter(Message).json_schema(
        mode="serialization", schema_generator=WithoutFieldTitles
    )
    return json.dumps({"title": "Message", **schema}, indent=2) + "\n"


def write(path: Path = SCHEMA_FILE) -> None:
    path.write_text(render())


def outdated(path: Path = SCHEMA_FILE) -> bool:
    return not path.exists() or path.read_text() != render()
