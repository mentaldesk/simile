from pathlib import Path

from simile.schema import Npc

TUNNELS_DIR = Path(__file__).resolve().parents[3] / "content" / "npcs" / "tunnels"
"""People who live in the tunnels, not the village, so `load_npcs` never makes them residents."""
DOCTOR = "annelie"


def load_doctor(directory: Path = TUNNELS_DIR) -> Npc:
    return Npc.model_validate_json((directory / f"{DOCTOR}.json").read_text(encoding="utf-8"))
