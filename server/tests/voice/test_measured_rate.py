import pytest

from simile.npc import load_npcs
from simile.voice.measure import seconds_to_say
from simile.voice.rates import REPO_ROOT, load_rates

pytestmark = pytest.mark.mlx

HELD_OUT = (
    "Oh, hello.",
    "You must be the one who moved in by the mill.",
    "Welcome to the village.",
    "I've lived on this street for nearly thirty years.",
    "I still get lost behind the station.",
    "Don't let the queue put you off.",
    "It moves quickly once the second till opens.",
    "Honestly?",
    "I'd rather walk.",
    "The bus never comes when it says it will, and the driver always looks at me like I've done "
    "something wrong.",
    "We should ask the library about the back room.",
    "Right.",
    "If nobody else is going to say it, I will: the new mural is hideous.",
    "Thanks for the soup, by the way.",
    "It was exactly what I needed after that cold.",
    "Is that the same dog from last week?",
    "The trouble with a small village is that everyone knows your business before you do.",
    "Have you noticed how the light changes over the square before it rains?",
    "Go on, then.",
    "Tell them I sent you.",
)


def test_a_measured_rate_predicts_how_long_the_slowest_voice_takes_to_reply() -> None:
    from simile.voice.qwen import QwenSynthesiser

    rates = load_rates()
    predicted = {id: sum(rate.seconds(line) for line in HELD_OUT) for id, rate in rates.items()}
    slowest = max(predicted, key=predicted.__getitem__)
    npc = next(npc for npc in load_npcs() if npc.id == slowest)
    assert npc.voice.reference_clip is not None
    synthesiser = QwenSynthesiser(seed=1)
    synthesiser.load()
    synthesiser.add_voice(npc.id, REPO_ROOT / npc.voice.reference_clip, npc.voice.reference_line)

    spoken = sum(seconds_to_say(synthesiser, npc.id, line) for line in HELD_OUT)

    # Some voices' rates run up to about 12% long, which only keeps a bubble up a little longer.
    assert 0.85 * predicted[slowest] <= spoken <= 1.05 * predicted[slowest]
