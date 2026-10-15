from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

PLAYER_ID = "player"

Id = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)]
Unit = Annotated[float, Field(ge=0, le=1)]
Signed = Annotated[float, Field(ge=-1, le=1)]
Colour = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)
