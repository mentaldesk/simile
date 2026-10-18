import asyncio
import difflib
import json
import re
import sys
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from simile.characters.tables.load import TABLES_DIR
from simile.llm import CallRecord, LLMClient, Model

MAX_LENGTH = 120
"""The longest mannerism a character can store."""


@dataclass(frozen=True)
class Prompt:
    id: str
    lean: Mapping[str, float]
    who: str


PROMPTS = (
    Prompt("honesty_humility_high", {"honesty_humility": 1}, "sincere, fair, modest people"),
    Prompt(
        "honesty_humility_low", {"honesty_humility": -1}, "sly, flattering, status-hungry people"
    ),
    Prompt("emotionality_high", {"emotionality": 1}, "anxious, sentimental, easily worried people"),
    Prompt("emotionality_low", {"emotionality": -1}, "unflappable, tough, unsentimental people"),
    Prompt("extraversion_high", {"extraversion": 1}, "sociable, lively, confident people"),
    Prompt(
        "extraversion_low", {"extraversion": -1}, "quiet, reserved people who keep to themselves"
    ),
    Prompt("agreeableness_high", {"agreeableness": 1}, "patient, gentle, forgiving people"),
    Prompt("agreeableness_low", {"agreeableness": -1}, "prickly, stubborn, quick-tempered people"),
    Prompt(
        "conscientiousness_high", {"conscientiousness": 1}, "orderly, careful, hard-working people"
    ),
    Prompt(
        "conscientiousness_low",
        {"conscientiousness": -1},
        "disorganised, impulsive, easy-going people",
    ),
    Prompt("openness_high", {"openness": 1}, "curious, imaginative, unconventional people"),
    Prompt(
        "openness_low",
        {"openness": -1},
        "conventional people who like things as they've always been",
    ),
    Prompt(
        "speech",
        {},
        "anyone at all, about their verbal habits: pet phrases, hedging, over-explaining, "
        "clipped answers, answering with a question, trailing off",
    ),
    Prompt(
        "conversation",
        {},
        "anyone at all, about the shape of their conversations: small talk first or straight to "
        "the point, follow-up questions or steering back to their own topic, changing the subject, "
        "ending abruptly, long stories, interrupting",
    ),
    Prompt(
        "humour",
        {},
        "anyone at all, about their humour and tone: dry, self-deprecating, teasing, earnest, "
        "deflecting with jokes",
    ),
)
PER_PROMPT = 18

SYSTEM = """You write character notes for a slice-of-life game set in a small, modern, \
fast-growing town with a Shenzhen flavour. Residents are ordinary adults of every age from 18 to \
90, every gender, background and job, from many countries."""

RULES = """Write {count} distinct conversational mannerisms for {who}.

Each one is a habit you would notice from their words alone, in any conversation: a verbal \
habit, the shape of how they talk with people, or their humour and tone.
- A verb phrase in the present tense with no subject, 4 to 14 words, e.g. "answers a question \
with another question" or "steers every topic back to their own work".
- Hint at the kind of person without naming the trait.
- Only what they say and how: no gestures, faces, posture, voice quality, objects, food or drink, \
and no good deeds or favours.
- Describe the habit rather than quoting it. Quote a word or two only for a pet phrase anyone \
might say in plain English.
- Anyone of any age, gender, origin or job could have it: say "their", never he or she, and \
nothing tied to a language, a place, a job or a religion.
- No English-village clichés: nothing about tea, the weather, the lane, the pub or the till.
- Plain and kind: nothing about illness, disability, medication, smoking, alcohol, sex, bodily \
functions or swearing, and no brands or real people.
- Don't repeat yourself."""

BANNED = re.compile(
    r"\b(he|she|his|her|him|hers|smok\w*|cigar\w*|vap\w*|beer|wine|whisky|alcohol|pills?|"
    r"medic\w*|church\w*|mosque|temple|pray\w*|tea|kettle|lane|pub|weather|nods?|shrugs?|winks?|"
    r"smil\w*|frown\w*|grins?|gestur\w*|fingers?|fidget\w*|eyebrows?|glanc\w*)\b",
    re.IGNORECASE,
)
STOP = frozenset(
    {"a", "an", "the", "their", "they", "them", "to", "of", "and", "or", "when", "while", "with"}
    | {"before", "after", "in", "into", "on", "over", "at", "for", "up", "it", "its", "as"}
    | {"from", "by", "every", "each", "one"}
)


class Batch(BaseModel):
    mannerisms: list[str]


async def generate(
    llm: LLMClient, prompts: Sequence[Prompt] = PROMPTS, count: int = PER_PROMPT
) -> list[tuple[Prompt, list[str]]]:
    """One Haiku call per prompt through L1, then deduplicated across all of them."""
    batches = await asyncio.gather(
        *(
            llm.structured(
                RULES.format(count=count, who=prompt.who),
                Batch,
                system=SYSTEM,
                model=Model.HAIKU,
                purpose="mannerisms",
            )
            for prompt in prompts
        )
    )
    return dedupe([(p, batch.mannerisms) for p, batch in zip(prompts, batches, strict=True)])


def dedupe(batches: Sequence[tuple[Prompt, Sequence[str]]]) -> list[tuple[Prompt, list[str]]]:
    """Drop exact and near repeats (keeping the first), and anything breaking the rules."""
    kept: list[str] = []
    result = []
    for prompt, items in batches:
        mine = []
        for item in items:
            text = _tidy(item)
            if text is None or any(_similar(text, other) for other in kept):
                continue
            kept.append(text)
            mine.append(text)
        result.append((prompt, mine))
    return result


def to_toml(batches: Sequence[tuple[Prompt, Sequence[str]]]) -> str:
    lines = [
        "# Generated once through L1 with Haiku by `uv run python -m "
        "simile.characters.tables.generate_mannerisms`.",
        "# Curated by hand afterwards: delete or reword freely, but keep the groups, and keep",
        "# every item something a listener would notice from their words alone.",
    ]
    for prompt, items in filter(lambda batch: batch[1], batches):
        lean = ", ".join(f"{key} = {value:g}" for key, value in prompt.lean.items())
        lines += ["", "[[group]]", f'id = "{prompt.id}"']
        if lean:
            lines.append(f"lean = {{ {lean} }}")
        lines.append("items = [")
        lines += [f"  {json.dumps(item, ensure_ascii=False)}," for item in items]
        lines.append("]")
    return "\n".join(lines) + "\n"


def read_toml(path: Path) -> list[tuple[Prompt, list[str]]]:
    with path.open("rb") as f:
        groups = tomllib.load(f)["group"]
    return [(Prompt(g["id"], g.get("lean", {}), ""), g["items"]) for g in groups]


def _tidy(item: str) -> str | None:
    text = " ".join(item.strip().strip(".").split())
    text = text[:1].lower() + text[1:]
    words = text.split()
    if not 3 <= len(words) <= 16 or len(text) > MAX_LENGTH or BANNED.search(text):
        return None
    if words[0] in ("they", "i", "you"):
        return None
    return text


def _similar(a: str, b: str) -> bool:
    x, y = _stems(a), _stems(b)
    if not x or not y:
        return x == y
    shared = len(x & y)
    if shared / min(len(x), len(y)) >= 0.75 or shared / len(x | y) >= 0.6:
        return True
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() >= 0.85


def _stems(text: str) -> frozenset[str]:
    words = (w for w in re.findall(r"[a-z]+", text.lower()) if w not in STOP)
    return frozenset(re.sub(r"(ing|ed|es|s)$", "", w) if len(w) > 4 else w for w in words)


async def _main(path: Path, dedupe_only: bool) -> None:
    if dedupe_only:
        batches = dedupe(read_toml(path))
        print(f"{sum(len(items) for _, items in batches)} mannerisms after deduplicating")
    else:
        calls: list[CallRecord] = []
        llm = LLMClient(listeners=[calls.append])
        try:
            batches = await generate(llm)
        finally:
            await llm.aclose()
        failed = sum(call.error is not None for call in calls)
        total = sum(len(items) for _, items in batches)
        print(f"{total} mannerisms from {len(calls)} calls ({failed} failed)")
    path.write_text(to_toml(batches))


if __name__ == "__main__":
    asyncio.run(_main(TABLES_DIR / "mannerisms.toml", "--dedupe-only" in sys.argv))
