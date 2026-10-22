from collections.abc import Callable
from datetime import datetime

from simile.schema import (
    Bionic,
    Fact,
    Id,
    Investigation,
    JournalEntry,
    Knower,
    Player,
    Source,
    SourceKind,
)

QUOTES = '"“” '


def quoted(said: str) -> str:
    """A lie as the journal writes it: in quotes, as it was told."""
    return f"“{said.strip(QUOTES)}”"


def flushed(lie: bool, player: Player) -> bool | None:
    """Whether the infrared eye sees the speaker flush, as on a lie, or None without the eye."""
    return lie if Bionic.INFRARED_EYE in player.body.bionics else None


class Journal:
    """Writes what reaches the player about the incident into the investigation's journal."""

    def __init__(
        self,
        investigation: Investigation,
        now: Callable[[], datetime],
        player: Callable[[], Player] = Player,
    ) -> None:
        self.investigation = investigation
        self.now = now
        self.player = player

    def told(self, fact: Fact, knower: Knower, name: str, *, lie: bool) -> bool:
        """`knower` told the player `fact`, or lied about it. Whether the journal changed."""
        if lie and knower.cover is None:
            return False
        entry = JournalEntry(
            fact_id=fact.id,
            text=quoted(knower.cover) if lie and knower.cover else fact.what,
            source=Source(kind=SourceKind.RESIDENT, id=knower.id, name=name),
            learned=self.now(),
            flushed=flushed(lie, self.player()),
            leads=[] if lie else fact.leads,
        )
        return self._add(entry, by_anyone=not lie)

    def found(self, clue: Id, name: str) -> bool:
        """The player found each fact in `clue`. Whether the journal changed."""
        incident = self.investigation.incident
        source = Source(kind=SourceKind.CLUE, id=clue, name=name)
        added = [
            self._add(
                JournalEntry(
                    fact_id=fact.id,
                    text=fact.what,
                    source=source,
                    learned=self.now(),
                    flushed=None,
                    leads=fact.leads,
                ),
                by_anyone=True,
            )
            for fact in (incident.facts if incident else [])
            if fact.found_in == clue
        ]
        return any(added)

    def _add(self, entry: JournalEntry, *, by_anyone: bool) -> bool:
        """Adds `entry` and closes the leads to its fact, unless it adds nothing new."""
        journal = list(self.investigation.journal)
        for n, old in enumerate(journal):
            if (old.fact_id, old.text) == (entry.fact_id, entry.text) and (
                by_anyone or old.source.id == entry.source.id
            ):
                if old.flushed or not entry.flushed:
                    return False
                del journal[n]
                break
        learned = {old.fact_id for old in journal} | {entry.fact_id}
        entry.leads = [lead for lead in entry.leads if lead.fact_id not in learned]
        for old in journal:
            if any(lead.fact_id == entry.fact_id for lead in old.leads):
                old.leads = [lead for lead in old.leads if lead.fact_id != entry.fact_id]
        self.investigation.journal = [*journal, entry]
        return True
