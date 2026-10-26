from datetime import UTC
from typing import Annotated

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field

PLAYER_ID = "player"

Id = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)]
Key = Annotated[str, Field(min_length=1)]
Unit = Annotated[float, Field(ge=0, le=1)]
Signed = Annotated[float, Field(ge=-1, le=1)]
Colour = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]
Timestamp = Annotated[AwareDatetime, AfterValidator(lambda value: value.astimezone(UTC))]


# Checks across fields are mode="before", so a rejected assignment leaves the model unchanged.
CHECKED = ConfigDict(validate_assignment=True)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


class MapTile(Model):
    """A tile on a given map: the village or an interior, or in side view a street or a floor."""

    model_config = CHECKED

    map: Key
    x: int = Field(ge=0)
    y: int = Field(ge=0)
