from dataclasses import dataclass

from simile.protocol import SAMPLE_RATE
from simile.schema import Id, Npc
from simile.voice.rates import MeasuredRate, SpeakingRate, voice_digest
from simile.voice.service import REPO_ROOT, Synthesiser

CALIBRATION = (
    "Morning.",
    "No.",
    "Fair enough, I suppose.",
    "I'm not sure that's true.",
    "You're right. I should have called.",
    "I wouldn't count on it, not this week.",
    "Let's talk about it over coffee tomorrow, if you're free.",
    "Oh, go on then, but only a small slice!",
    "Have you tried the new bread at the bakery? It's better than it looks.",
    "That's kind of you to say, but I think the garden did most of the work this year.",
    "Who told you that? Because it certainly wasn't me, and I'd like to know who's been talking.",
    "I heard the council wants to close the library on Sundays, and honestly I can't see who "
    "that helps.",
    "The fountain's been dry since March, and every time I ask about it someone tells me it's on "
    "a list somewhere.",
    "The best thing about this village is that nobody's in a hurry, and the worst thing is "
    "exactly the same.",
    "Honestly, I think we all need a bit more patience with each other, especially now, with "
    "everything changing so quickly around here.",
    "When I was your age we walked everywhere, rain or shine, and nobody thought twice about it. "
    "Mind you, the hills were smaller then.",
    "Well, that's one way of looking at it, I suppose, though I'd rather hear what the others "
    "think before we decide anything at all about the square.",
    "It's a funny thing, but the older I get, the less I trust anyone who's certain about "
    "anything, myself most of all.",
    "Do you ever wonder what this place looked like before the mill closed? My grandmother used "
    "to say the whole street smelled of flour and engine oil, and that the noise never stopped, "
    "not even at night.",
    "If you'd asked me a year ago whether I'd be running the market stall on my own, I'd have "
    "laughed, but here we are, and I've rather come to like it.",
    "I've been meaning to ask you about the old footbridge. Is it true they want to pull it down, "
    "or is that just another rumour from the noodle bar?",
    "Thank you. Really, I mean it.",
    "Some days I think I should have stayed in the city, and other days I can't imagine living "
    "anywhere else.",
    "We could fix the bench ourselves, you know. It only needs a few new slats, some screws and an "
    "afternoon, and I've got the tools in my shed doing nothing.",
)


@dataclass(frozen=True)
class Measurement:
    rate: MeasuredRate
    error: float
    """Root-mean-square seconds between a calibration line's audio and what the rate predicts."""


def measure(
    synthesiser: Synthesiser, npc: Npc, lines: tuple[str, ...] = CALIBRATION
) -> Measurement:
    """Speak `lines` in the NPC's voice and fit its rate to how long they took."""
    if npc.voice.reference_clip is None:
        raise ValueError(f"{npc.id} has no voice yet")
    synthesiser.add_voice(npc.id, REPO_ROOT / npc.voice.reference_clip, npc.voice.reference_line)
    spoken = [(line, seconds_to_say(synthesiser, npc.id, line)) for line in lines]
    fitted = SpeakingRate.fit(spoken)
    squares = [(seconds - fitted.seconds(line)) ** 2 for line, seconds in spoken]
    rate = MeasuredRate(**fitted.model_dump(), digest=voice_digest(npc.voice))
    return Measurement(rate, (sum(squares) / len(squares)) ** 0.5)


def seconds_to_say(synthesiser: Synthesiser, npc_id: Id, line: str) -> float:
    samples = sum(len(pcm) for pcm in synthesiser.generate(npc_id, line)) // 2
    return samples / SAMPLE_RATE
