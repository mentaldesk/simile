import re
from collections.abc import Sequence
from pathlib import Path

from simile.npc.generate import Brief, craft_label, first_sentence
from simile.npc.values import format_scores, ranked
from simile.schema import Npc

NPCS_DIR = Path(__file__).resolve().parents[3] / "content" / "npcs"


def write_npcs(
    npcs: Sequence[Npc], directory: Path, seed: int, briefs: Sequence[Brief] = ()
) -> list[Path]:
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
    readme_path.write_text(readme(npcs, seed, briefs), encoding="utf-8")
    return [*written, readme_path]


def load_npcs(directory: Path = NPCS_DIR) -> list[Npc]:
    return [
        Npc.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(directory.glob("*.json"))
    ]


def readme_seed(directory: Path = NPCS_DIR) -> int:
    """The seed the README says made the NPCs in `directory`."""
    if found := re.search(r"--seed (\d+)", (directory / "README.md").read_text(encoding="utf-8")):
        return int(found[1])
    raise ValueError(f"{directory / 'README.md'} doesn't say which seed made the NPCs")


def readme(npcs: Sequence[Npc], seed: int, briefs: Sequence[Brief] = ()) -> str:
    facts = {brief.home: brief.facts for brief in briefs if brief.facts}
    command = f"uv run simile generate-npcs --count {len(npcs)} --seed {seed}"
    if facts:
        command += " --rich-brief --out <dir>"
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
        "- **Crafts**, what each resident makes in their own time, can be chosen again without",
        "  changing anything else with `uv run simile npc crafts`, one Sonnet call per NPC.",
        "- `voice.reference_clip` stays null until N2 records each voice. Sprites come from",
        "  `uv run simile art --npcs`.",
        "",
        "Each NPC's strongest and weakest values next to their craft and the first line of their",
        "persona, to check at a glance that the values drive the personality:",
        "",
        "| NPC | Age | Occupation | Craft | Cares most about | Cares least about | Persona |",
        "|---|--:|---|---|---|---|---|",
    ]
    for npc in sorted(npcs, key=lambda npc: npc.id):
        order = ranked(npc.values)
        cells = [
            f"`{npc.id}` {npc.name}",
            str(npc.age),
            npc.occupation,
            craft_label(npc.craft),
            format_scores(order[:3]),
            format_scores(order[::-1][:3]),
            first_sentence(npc.persona),
        ]
        lines.append(_row(cells))
    if facts:
        lines += [
            "",
            "## Sampled facts",
            "",
            "With `--rich-brief`, each resident's name, origin, occupation and life events are",
            "sampled in code too, from the tables in `server/simile/npc/tables.py`, and Claude",
            "writes the rest around them:",
            "",
            "| NPC | Origin | Occupation | Life events |",
            "|---|---|---|---|",
        ]
        for npc in sorted(npcs, key=lambda npc: npc.id):
            if sampled := facts.get(npc.home):
                events = "; ".join(f"{age}: {event}" for age, event in sampled.events)
                lines.append(
                    _row([f"`{npc.id}` {npc.name}", sampled.origin, sampled.occupation, events])
                )
    return "\n".join(lines) + "\n"


def _row(cells: Sequence[str]) -> str:
    return "| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |"
