from typing import Self

from pydantic import Field, model_validator

from simile.schema.common import Id, Key, Model, Timestamp


class Line(Model):
    id: int = Field(ge=0, description="Unique across the world. Audio for the line carries it.")
    conversation_id: Key
    speaker: Id
    text: str
    timestamp: Timestamp = Field(description="When the speaker starts saying it.")
    duration: float = Field(ge=0, description="Estimated seconds to say it aloud.")


class Conversation(Model):
    id: Key
    participants: list[Id] = Field(min_length=2)
    started: Timestamp
    ended: Timestamp | None = Field(default=None, description="Null while it's going on.")
    lines: list[Line] = []

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if len(set(self.participants)) != len(self.participants):
            raise ValueError("participants must be distinct")
        for line in self.lines:
            if line.conversation_id != self.id:
                raise ValueError(f"line {line.id} belongs to conversation {line.conversation_id}")
            if line.speaker not in self.participants:
                raise ValueError(f"line {line.id} speaker {line.speaker} isn't a participant")
        return self
