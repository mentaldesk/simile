import re
from collections.abc import Sequence
from pathlib import Path

from simile.npc.values import format_scores, ranked
from simile.schema import Npc

NPCS_DIR = Path(__file__).resolve().parents[3] / "content" / "npcs"


def write_npcs(npcs: Sequence[Npc], directory: Path, seed: int) -> list[Path]:
    """Write each NPC as `<id>.json` plus a README, replacing any NPCs already there."""
    directory.mkdir(parents=True, exist_ok=True)
    ids = {npc.id for npc in npcs}
    for stale in directory.glob("*.json"):
        if stale.stem not in ids:
            stale.unlink()
    written = []
    for npc in npcs:
        path = directory / f"{npc.id}.json"
        path.write_text(npc.model_dump_json(indent=2) + "\n", encoding="utf-8")
        written.append(path)
    readme_path = directory / "README.md"
    readme_path.write_text(readme(npcs, seed), encoding="utf-8")
    return [*written, readme_path]


def load_npcs(directory: Path = NPCS_DIR) -> list[Npc]:
    return [
        Npc.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(directory.glob("*.json"))
    ]


def readme(npcs: Sequence[Npc], seed: int) -> str:
    command = f"uv run simile generate-npcs --count {len(npcs)} --seed {seed}"
    lines = [
        "# NPCs",
        "",
        "The village's residents. Each `<id>.json` is an F2 `Npc`, generated from `server/` by",
        "",
        "```bash",
        command,
        "```",
        "",
        "Don't edit them by hand: rerun the command, which replaces them all.",
        "",
        "- **Values** are sampled in code, so the seed always gives the same ones: correlated",
        "  through four latent traits, then spread across value space by farthest-point sampling",
        "  (`server/simile/npc/values.py`). Age, gender and home are fixed in code too.",
        "- **Everything else** is written by Claude, one Sonnet call per NPC, from those values,",
        "  so a rerun gives new names and stories.",
        "- `voice.reference_clip` stays null until N2 records each voice. Sprites come from",
        "  `uv run simile art --npcs`.",
        "",
        "Each NPC's strongest and weakest values next to the first line of their persona, to",
        "check at a glance that the values drive the personality:",
        "",
        "| NPC | Age | Occupation | Cares most about | Cares least about | Persona |",
        "|---|--:|---|---|---|---|",
    ]
    for npc in sorted(npcs, key=lambda npc: npc.id):
        order = ranked(npc.values)
        cells = [
            f"`{npc.id}` {npc.name}",
            str(npc.age),
            npc.occupation,
            format_scores(order[:3]),
            format_scores(order[::-1][:3]),
            first_sentence(npc.persona),
        ]
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")
    return "\n".join(lines) + "\n"


def first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0]
