import random
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from simile.schema import CoreValue, Npc

CAFE_DIR = Path(__file__).resolve().parents[3] / "content" / "cafe"


class Drink(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    seconds: float = Field(gt=0, description="How long it takes to make, in sim seconds.")
    values: dict[CoreValue, float] = Field(
        default={}, description="Who orders it: score per unit of `value - 0.5`."
    )


class Menu(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    drinks: list[Drink] = Field(min_length=1)
    improvised_seconds: float = Field(gt=0, description="How long anything off the menu takes.")

    def get(self, drink_id: str | None) -> Drink | None:
        return next((drink for drink in self.drinks if drink.id == drink_id), None)

    def seconds(self, drink_id: str | None) -> float:
        drink = self.get(drink_id)
        return drink.seconds if drink else self.improvised_seconds

    def usual(self, npc: Npc) -> Drink:
        """The drink their values lean towards most."""
        return max(self.drinks, key=lambda drink: _appeal(drink, npc))

    def choose(self, npc: Npc, rng: random.Random, usual: float) -> Drink:
        """Their usual with chance `usual`, otherwise any drink, weighted to their taste."""
        if rng.random() < usual:
            return self.usual(npc)
        weights = [max(_appeal(drink, npc), 0.0) + 0.1 for drink in self.drinks]
        return rng.choices(self.drinks, weights)[0]

    def listing(self) -> str:
        return ", ".join(f"{drink.name} ({drink.id})" for drink in self.drinks)


def _appeal(drink: Drink, npc: Npc) -> float:
    return sum(weight * (npc.values[value] - 0.5) for value, weight in drink.values.items())


def load_menu(path: Path = CAFE_DIR / "menu.json") -> Menu:
    return Menu.model_validate_json(path.read_text(encoding="utf-8"))
