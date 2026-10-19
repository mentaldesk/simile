import math
import random
from collections.abc import Mapping

from simile.characters.tables import Village
from simile.characters.tables.conditions import LEAN, choose
from simile.schema import Humour, HumourStyle

S = HumourStyle

STYLES: dict[HumourStyle, tuple[float, dict[str, float]]] = {
    S.DRY: (1.0, {"knowledge": 1, "discipline": 0.5, "extraversion": -0.5}),
    S.DEADPAN: (1.0, {"honesty": -1, "emotionality": -0.5, "extraversion": -0.5}),
    S.SARCASTIC: (1.0, {"compassion": -1, "self_respect": 1}),
    S.CYNICAL: (1.0, {"optimism": -1, "obedience": -0.5, "justice": 0.5}),
    S.PUNNING: (1.0, {"tradition": -1, "creativity": 1, "knowledge": 0.5}),
    S.SILLY: (1.0, {"tradition": -1, "creativity": 1, "pleasure": 0.5}),
    S.TEASING: (1.0, {"connection": 1, "extraversion": 1, "agreeableness": 0.5}),
    S.GALLOWS: (0.8, {"optimism": -0.5, "security": -1, "peace_of_mind": -0.5}),
    S.NONE: (0.5, {"tradition": 1, "obedience": 1, "pleasure": -1, "openness": -0.5}),
}
"""Each style's base weight and its leans on core values and HEXACO scores, as tables lean."""

SERIOUS: dict[str, float] = {
    "discipline": 1,
    "responsibility": 0.5,
    "tradition": 0.5,
    "pleasure": -1,
    "creativity": -0.5,
    "liveliness": -1,
}
"""How each score pulls seriousness up or down."""
CENTRE, GAIN, NOISE = 0.5, 1.6, 0.7
LEAST, MOST = 0.1, 0.95
SPREAD = 2
"""A style the village has already is damped this many times over, so styles spread."""

KINDS: dict[HumourStyle, str] = {
    S.DRY: "dry: understatement and wry asides, said plainly",
    S.DEADPAN: "deadpan: absurd or ironic remarks made with a perfectly straight face",
    S.SARCASTIC: "sarcastic: saying the opposite of what {they} mean, dry rather than cutting",
    S.CYNICAL: "cynical: wry remarks about people's motives and how things really work",
    S.PUNNING: "punning: wordplay and puns, the more groan-worthy the better",
    S.SILLY: "silly: playful nonsense and daft flights of fancy",
    S.TEASING: "teasing: gentle ribbing of people {they} get on with",
    S.GALLOWS: "dark, gallows humour about {their} own troubles and bad luck",
}
BANDS = ((0.35, "a lot"), (0.65, "often"), (0.9, "now and then"))
RARELY = "rarely"
OFTEN = {
    "a lot": "{who} {joke} a lot, in most of what {they} say, but never in every line.",
    "often": "{who} {joke} often, but never in every line.",
    "now and then": "{who} {joke} now and then, never in every line.",
    RARELY: "{who} rarely {joke}: most of what {they} say is meant plainly.",
}
NO_JOKES = "{who} {are} not one for jokes: {they} say what {they} mean."
KIND = (
    "{whose} jokes are never cruel and never punch down, and any sarcasm stays dry, never "
    "insulting."
)


def sample_humour(
    rng: random.Random, scores: Mapping[str, float], *, village: Village | None = None
) -> Humour:
    """A style leaning on their core values and temperament (`scores`), styles the `village`
    already has less likely, and a seriousness pulled up by discipline and down by pleasure and
    liveliness. A roll in each keeps them varied."""
    taken = village or Village()
    styles = list(STYLES)
    weights = [
        base
        * math.prod(math.exp(LEAN * s * (scores.get(k, 0.5) - 0.5)) for k, s in lean.items())
        * taken.damping(key(style)) ** SPREAD
        for style, (base, lean) in STYLES.items()
    ]
    style = choose(rng, styles, weights) or S.DRY
    if village is not None:
        village.drawn[key(style)] += 1
    if style is S.NONE:
        return Humour(style=style, seriousness=1)
    norm = math.sqrt(sum(s * s for s in SERIOUS.values()))
    pull = sum(s * (2 * scores.get(k, 0.5) - 1) for k, s in SERIOUS.items()) / norm
    drawn = 1 / (1 + math.exp(-(CENTRE + GAIN * pull + rng.gauss(0, NOISE))))
    return Humour(style=style, seriousness=round(min(max(drawn, LEAST), MOST), 2))


def how_often(humour: Humour) -> str:
    """How often they joke, in words: "a lot", "often", "now and then" or "rarely"."""
    return next((words for below, words in BANDS if humour.seriousness < below), RARELY)


def describe_humour(humour: Humour, name: str | None = None, *, kind: bool = False) -> str:
    """Their humour's style and how often they joke, told to them or, with `name`, about them,
    with `kind`, the bounds on their jokes."""
    words = (
        {"who": name, "whose": f"{name}'s", "joke": "jokes", "are": "is"}
        if name
        else {"who": "You", "whose": "Your", "joke": "joke", "are": "are"}
    )
    words |= {"they": "they", "their": "their"} if name else {"they": "you", "their": "your"}
    if humour.style is S.NONE:
        return NO_JOKES.format(**words)
    parts = [
        f"{words['whose']} humour is {KINDS[humour.style].format(**words)}.",
        OFTEN[how_often(humour)].format(**words),
    ]
    if kind:
        parts.append(KIND.format(**words))
    return " ".join(parts)


def sketch(humour: Humour) -> str:
    """Their humour in a few words, for a character brief."""
    if humour.style is S.NONE:
        return "not one for jokes, says what they mean"
    kind = KINDS[humour.style].format(they="they", their="their")
    if ": " in kind:
        kind = kind.replace(": ", " (", 1) + ")"
    return f"{kind}, jokes {how_often(humour)}"


def key(style: HumourStyle) -> str:
    return f"humour:{style}"
