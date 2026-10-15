import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
NPCS = REPO_ROOT / "content" / "npcs"
VOICES = REPO_ROOT / "content" / "voices"
SAMPLES = VOICES / "samples"

SAMPLE_LINES = [
    "Morning. Have you seen who's moved into the empty house by the square?",
    "The bus was forty minutes late again, so I walked the long way round, "
    "past the bakery, the library and the old mill.",
    "No, I don't think that's fair, and I'll say so at the meeting tomorrow.",
]


def load_npcs(ids: list[str] | None = None) -> dict[str, dict]:
    npcs = {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in sorted(NPCS.glob("*.json"))}
    if unknown := set(ids or []) - set(npcs):
        raise SystemExit(f"no such NPC: {', '.join(sorted(unknown))}")
    return {npc_id: npcs[npc_id] for npc_id in ids} if ids else npcs


def clip_path(npc_id: str) -> Path:
    return VOICES / f"{npc_id}.wav"


def has_voice(npc_id: str, npc: dict) -> bool:
    clip = clip_path(npc_id)
    return clip.exists() and npc["voice"]["reference_clip"] == clip.relative_to(REPO_ROOT).as_posix()


def sample_paths(npc_id: str) -> list[Path]:
    return [SAMPLES / f"{npc_id}_{i}.m4a" for i in range(1, len(SAMPLE_LINES) + 1)]


def set_reference_clip(npc_id: str, clip: Path) -> None:
    path = NPCS / f"{npc_id}.json"
    npc = json.loads(path.read_text(encoding="utf-8"))
    npc["voice"]["reference_clip"] = clip.relative_to(REPO_ROOT).as_posix()
    path.write_text(json.dumps(npc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def remove_voice(npc_id: str) -> None:
    for path in [clip_path(npc_id), clip_path(npc_id).with_suffix(".txt"), *sample_paths(npc_id)]:
        path.unlink(missing_ok=True)


NUMBERS = dict(enumerate("zero one two three four five six seven eight nine ten eleven twelve".split()))
NUMBERS |= dict(zip(range(20, 100, 10), "twenty thirty forty fifty sixty seventy eighty ninety".split(), strict=True))


def words(text: str) -> list[str]:
    spoken = re.sub(r"[^a-z0-9' ]", " ", text.lower().replace("’", "'")).split()
    return [NUMBERS.get(int(word), word) if word.isdigit() else word for word in spoken]


def word_error_rate(expected: str, heard: str) -> float:
    want, got = words(expected), words(heard)
    row = list(range(len(got) + 1))
    for i, word in enumerate(want, 1):
        previous, row[0] = row[0], i
        for j, other in enumerate(got, 1):
            previous, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, previous + (word != other))
    return row[-1] / len(want)
