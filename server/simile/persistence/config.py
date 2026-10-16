from pydantic import BaseModel, ConfigDict, Field


class PersistenceConfig(BaseModel):
    """When the world is saved, and how long shutdown waits to save it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    save_every: float = Field(default=10.0, gt=0, description="Real seconds between saves.")
    reflection_wait: float = Field(
        default=20.0,
        ge=0,
        description="Real seconds shutdown waits for reflections still going on before saving "
        "without them.",
    )


DEFAULT_CONFIG = PersistenceConfig()
