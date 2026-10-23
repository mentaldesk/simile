from simile.conversation.player import PlayerTalk
from simile.conversation.telling import Stance
from simile.schema import PLAYER_ID, Line, Player
from simile.story.journal import flushed as eye_sees
from simile.story.saying import says


def lying(talk: PlayerTalk, line: Line) -> bool:
    """Whether `line` gives a cover story the code decided its speaker lies with: it says the
    cover, or completes it, as the journal reads their lines joined."""
    if line.speaker == PLAYER_ID or line.conversation_id != talk.conversation.id:
        return False
    lines = talk.conversation.lines
    at = next((n for n, each in enumerate(lines) if each.id == line.id), len(lines))
    before = " ".join(each.text for each in lines[:at] if each.speaker == line.speaker)
    covers = [
        telling.knower.cover
        for telling in talk.tellings.values()
        if telling.stance is Stance.LIE and telling.knower.cover
    ]
    return any(
        says(line.text, cover) or (says(f"{before} {line.text}", cover) and not says(before, cover))
        for cover in covers
    )


def flushed(talk: PlayerTalk | None, line: Line, player: Player) -> bool:
    """The infrared eye's flush on a lie, which the journal's entry for it agrees with."""
    return talk is not None and bool(eye_sees(lying(talk, line), player))
