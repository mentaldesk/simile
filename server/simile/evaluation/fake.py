import json
from itertools import count

from simile.llm import Request

STOCK = "stock"
"""The model name a run without Claude gives its replies and stances."""

LINES = (
    "Oh, go on then, I've got a minute. [values: compassion]",
    "Not today, sorry. I'm run off my feet. [values: independence]",
    "Hmm, I'd want to know a bit more first. [values: security]",
    "Funny you should say that, have you tried the new bakery? [values: pleasure]",
)
JOKING = 3
"""Every this many replies, the stock judge says one jokes."""
BREAKING = 7
"""Every this many replies, the stock judge says one breaks a tone bound."""


class Stock:
    """Answers without Claude: replies from `LINES` in turn, and stances for the judge's call,
    each reply's labels in turn, with no lies, a joke every `JOKING` replies, in each style in
    turn, and a broken bound every `BREAKING` replies, each bound in turn."""

    def __init__(self) -> None:
        self._turn = count()

    def __call__(self, request: Request) -> str:
        if "no code fence:\n" not in request.system:
            return LINES[next(self._turn) % len(LINES)]
        schema = json.loads(request.system.split("no code fence:\n", 1)[1])
        labels = {
            name: field["enum"][n % len(field["enum"])] if "enum" in field else []
            for n, (name, field) in enumerate(schema["properties"].items())
        }
        numbers = [name for name in labels if name not in ("lies", "jokes", "breaks")]
        if "jokes" in labels:
            styles = schema["$defs"]["Joke"]["properties"]["style"]["enum"]
            labels["jokes"] = [
                {"reply": number, "style": styles[n // JOKING % len(styles)]}
                for n, number in enumerate(numbers)
                if n % JOKING == 0
            ]
        if "breaks" in labels:
            bounds = schema["$defs"]["Break"]["properties"]["bound"]["enum"]
            labels["breaks"] = [
                {"reply": number, "bound": bounds[n // BREAKING % len(bounds)]}
                for n, number in enumerate(numbers)
                if n % BREAKING == BREAKING - 1
            ]
        return json.dumps(labels)
