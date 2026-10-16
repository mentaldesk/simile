import re
from pathlib import Path

from simile.voicing import DEFAULT_CONFIG

CLIENT = Path(__file__).resolve().parents[3] / "client" / "src"


def client_constant(path: str, name: str) -> float:
    source = (CLIENT / path).read_text()
    match = re.search(rf"^export const {name} = ([\d.]+);$", source, re.MULTILINE)
    assert match, f"no `export const {name} = <number>;` in client/src/{path}"
    return float(match[1])


def test_bubbles_show_as_far_as_voicing_starts() -> None:
    assert client_constant("ui/tuning.ts", "EARSHOT_TILES") == DEFAULT_CONFIG.earshot


def test_overheard_voices_fall_silent_where_voicing_stops() -> None:
    assert client_constant("audio/spatial.ts", "SILENT_BEYOND") == DEFAULT_CONFIG.out_of_earshot
