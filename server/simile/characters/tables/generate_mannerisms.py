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
    Prompt("speech", {}, "anyone at all, about the way they talk"),
    Prompt("hands", {}, "anyone at all, about what they do with their hands, face and body"),
    Prompt(
        "routines", {}, "anyone at all, about small daily habits with food, objects and routines"
    ),
)
PER_PROMPT = 40

SYSTEM = """You write character notes for a slice-of-life game set in a small village today. \
Residents are ordinary adults of every age from 18 to 90, every gender, background and job."""

RULES = """Write {count} distinct mannerisms for {who}.

Each one is a small, specific habit a neighbour would notice: a verbal habit (described, not \
quoted), a gesture, a way of sitting or standing, how they handle objects, food or drink, or a \
little routine.
- A verb phrase in the present tense with no subject, 4 to 14 words, e.g. "taps the table twice \
before giving an opinion".
- Hint at the kind of person without naming the trait.
- Anyone of any age, gender, culture or job could have it: say "their", never he or she, and \
nothing tied to a job, a religion or gendered clothing.
- Plain and kind: nothing about illness, disability, medication, smoking, alcohol, sex or bodily \
functions, and no brands or real people.
- Avoid the stock ones (twirling hair, biting nails, cracking knuckles) and don't repeat \
yourself."""

BANNED = re.compile(
    r"\b(he|she|his|her|him|hers|smok\w*|cigar\w*|vap\w*|beer|wine|whisky|alcohol|pills?|"
    r"medic\w*|church\w*|mosque|temple|pray\w*)\b",
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
        "# Curated by hand afterwards: delete or reword freely, but keep the groups.",
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
    if not 3 <= len(words) <= 16 or BANNED.search(text) or words[0] in ("they", "i", "you"):
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
