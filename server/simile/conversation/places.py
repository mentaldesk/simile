from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from simile.schema import Id
from simile.story.town import FACTS, Knowing, Place, TownFact

ABOUT = "What you know of {place}, should {other} ask:"
KNOWS = '- You know this: "{said}"'
HEARD = "- You've only heard this, and say it's just what people say: \"{said}\""
UNKNOWN = "- {unknown}"
ONLY = (
    "- That's all you know of it. Give no other directions or details, and if asked for more, "
    "say you've no idea rather than guess."
)


@dataclass(frozen=True)
class Asked:
    """A place the player asked a resident about, and what they know of it."""

    place: Place
    known: Mapping[Id, Knowing]

    def facts(self) -> list[TownFact]:
        return [FACTS[id] for id in self.place.facts]

    def lines(self, other: str) -> str:
        lines = [ABOUT.format(place=self.place.name, other=other)]
        for fact in self.facts():
            knowing = self.known.get(fact.id)
            if knowing is Knowing.KNOWS:
                lines.append(KNOWS.format(said=fact.what))
            elif knowing is Knowing.HEARD:
                lines.append(HEARD.format(said=fact.rumour))
            else:
                lines.append(UNKNOWN.format(unknown=fact.unknown))
        return "\n".join([*lines, ONLY])

    def told(self) -> list[tuple[TownFact, Knowing]]:
        """What they tell of it that the journal keeps."""
        return [
            (fact, knowing)
            for fact in self.facts()
            if fact.journal and (knowing := self.known.get(fact.id)) is not None
        ]


def directions(asked: Iterable[Asked], other: str) -> list[str]:
    """What the resident knows of each place they've been asked about."""
    return [each.lines(other) for each in asked]
