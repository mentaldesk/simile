from enum import StrEnum
from typing import Self

from pydantic import Field, field_validator, model_validator

from simile.schema.common import PLAYER_ID, Id, Key, Model, Timestamp


class IntentionKind(StrEnum):
    """B1's options: `create`, `seek` and `news` are its activities of the same name, and `go` is
    whichever activity takes them to `target`."""

    CREATE = "create"
    GO = "go"
    SEEK = "seek"
    NEWS = "news"


TARGETED = (IntentionKind.GO, IntentionKind.SEEK)


class Intention(Model):
    """Something `owner` said they'd do, which they favour from when it's due until it's done or
    expires."""

    id: Key
    owner: Id = Field(description="The resident who said they'd do it.")
    kind: IntentionKind
    target: Id | None = Field(
        default=None,
        description="For `go` the location, and for `seek` whom they'll seek out. For `create` "
        "the wall or location to make it at, and for `news` the terminal, or null for wherever "
        "they'd usually go.",
    )
    description: str = Field(
        min_length=1,
        max_length=240,
        description="What they said they'd do, in a few words, for prompts. For `create` the idea "
        'itself, e.g. "a mural of an ocean of coffee with cups half-sunk in it".',
    )
    promised_to: list[Id] = Field(
        default=[], description="Who they said it to. Each remembers if it's broken."
    )
    created: Timestamp = Field(description="When they said it.")
    due: Timestamp = Field(description="When they mean to do it: `created` for now.")
    expires: Timestamp = Field(description="When it's dropped if they haven't done it.")
    conversation_id: Key | None = Field(
        default=None,
        description="The conversation it came from. The owner's `conversation` memory of it "
        "carries the same id. Null if it didn't come from one.",
    )

    @field_validator("owner")
    @classmethod
    def _not_player(cls, owner: str) -> str:
        if owner == PLAYER_ID:
            raise ValueError("the player doesn't have intentions")
        return owner

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.kind in TARGETED and self.target is None:
            raise ValueError(f"a {self.kind} intention needs a target")
        if self.kind is IntentionKind.SEEK and self.target == self.owner:
            raise ValueError("they can't seek themselves out")
        if self.owner in self.promised_to:
            raise ValueError("they can't promise themselves")
        if len(set(self.promised_to)) != len(self.promised_to):
            raise ValueError("promised_to names each person once")
        if self.due < self.created:
            raise ValueError("due must not be before created")
        if self.expires <= self.due:
            raise ValueError("expires must be after due")
        return self
