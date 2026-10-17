import json
import math
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image
from typer.testing import CliRunner

from simile.art.iso import blender, camera, characters, formats
from simile.art.iso.lighting import NEUTRAL, SETS
from simile.cli import create_cli
from simile.world.map import WALKING_SPEED

NPCS = characters.CONTENT_DIR / "npcs"
FOLDER = Path("art") / "iso" / "characters"


class FakeBlender:
    """Writes frames and probes shaped like Blender's, each frame's colour saying where it is."""

    def __init__(self) -> None:
        self.jobs: list[dict[str, Any]] = []
        self.figure = (4, 4, 12, 20)

    def __call__(self, job: dict[str, Any], work: Path) -> dict[str, Any]:
        self.jobs.append(job)
        f = job["frame"]
        done = {}
        for spec in job["characters"]:
            folder = work / spec["key"]
            folder.mkdir(parents=True, exist_ok=True)
            cols = sum(a["frames"] for a in job["animations"].values())
            for row in range(len(job["directions"])):
                for col in range(cols):
                    image = Image.new("RGBA", (f["width"], f["height"]))
                    image.paste((row * 20, col * 10, 50, 255), self.figure)
                    image.save(folder / f"{row}-{col}.png")
            done[spec["key"]] = {"frames": len(job["directions"]) * cols, "seconds": 1.0}
        if probe := job.get("probe"):
            _, _, w, h = probe["rect"]
            for light in [job["light"], *probe["sets"]]:
                (work / "probe" / light["name"]).mkdir(parents=True, exist_ok=True)
                for name in job["directions"]:
                    image = Image.new("RGBA", (w, h))
                    if light["name"] == "neutral":
                        image.paste((200, 200, 200, 255), (100, 50, 120, 150))
                    else:
                        image.paste((100, 150, 200, 255), (100, 50, 120, 150))
                        image.paste((0, 0, 0, 128), (200, 140, 300, 160))
                    image.save(work / "probe" / light["name"] / f"{name}.png")
        return {"characters": done, "seconds": {"total": 0.0}}

    def rendered(self) -> list[str]:
        return [spec["key"] for job in self.jobs for spec in job["characters"]]


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeBlender:
    small = {"width": 16, "height": 24, "anchor": [8, 21]}
    monkeypatch.setattr(characters, "frame", lambda: small)
    quick = formats.Format("quick", "webp", (("lossless", True), ("method", 0)))
    monkeypatch.setattr(formats, "CHARACTERS", quick)
    return FakeBlender()


@pytest.fixture
def content(tmp_path: Path) -> Path:
    npcs = tmp_path / "content" / "npcs"
    npcs.mkdir(parents=True)
    for name in ("ingrid", "lachlan"):
        shutil.copy(NPCS / f"{name}.json", npcs)
    return tmp_path / "content"


def build(content: Path, fake: FakeBlender, **kwargs) -> characters.Report:
    return characters.build(content, work=content.parent / "work", render=fake, **kwargs)


def manifest(content: Path) -> dict:
    return json.loads((content / FOLDER / characters.MANIFEST).read_text())


def files(content: Path) -> dict[str, int]:
    return {p.name: p.stat().st_mtime_ns for p in (content / FOLDER).iterdir()}


def add_resident(content: Path, source: str, new_id: str) -> None:
    npc = json.loads((NPCS / f"{source}.json").read_text())
    npc["id"] = new_id
    (content / "npcs" / f"{new_id}.json").write_text(json.dumps(npc))


def test_first_build_renders_the_player_and_every_resident(
    content: Path, fake: FakeBlender
) -> None:
    report = build(content, fake)

    assert fake.rendered() == ["player", "ingrid", "lachlan"]
    assert report.probed
    m = manifest(content)
    assert list(m["characters"]) == ["player", "ingrid", "lachlan"]
    for sheet in m["characters"].values():
        assert (content / FOLDER / sheet["image"]).exists()
        assert sheet["image"].endswith(f".{formats.CHARACTERS.ext}")


def test_a_second_build_renders_and_writes_nothing(content: Path, fake: FakeBlender) -> None:
    build(content, fake)
    before = files(content)
    fake.jobs.clear()

    report = build(content, fake)

    assert fake.jobs == []
    assert not report.rendered and not report.written and not report.removed
    assert not report.probed
    assert files(content) == before


def test_adding_a_resident_renders_only_that_resident(content: Path, fake: FakeBlender) -> None:
    build(content, fake)
    before = files(content)
    fake.jobs.clear()
    add_resident(content, "odalys", "odalys")

    report = build(content, fake)

    [job] = fake.jobs
    assert fake.rendered() == ["odalys"]
    assert "probe" not in job
    assert sorted(report.written) == sorted([characters.MANIFEST, "odalys.webp"])
    after = files(content)
    assert {k: v for k, v in after.items() if k in before and k != characters.MANIFEST} == {
        k: v for k, v in before.items() if k != characters.MANIFEST
    }


def test_changing_an_appearance_renders_only_that_resident(
    content: Path, fake: FakeBlender
) -> None:
    build(content, fake)
    fake.jobs.clear()
    path = content / "npcs" / "lachlan.json"
    npc = json.loads(path.read_text())
    npc["appearance"]["accessories"] = ["scarf"]
    path.write_text(json.dumps(npc))

    build(content, fake)

    assert fake.rendered() == ["lachlan"]


def test_a_resident_who_leaves_takes_their_sheet(content: Path, fake: FakeBlender) -> None:
    build(content, fake)
    (content / "npcs" / "lachlan.json").unlink()

    report = build(content, fake)

    assert report.removed == ["lachlan.webp"]
    assert "lachlan" not in manifest(content)["characters"]
    assert not (content / FOLDER / "lachlan.webp").exists()


def test_a_missing_sheet_is_rendered_again(content: Path, fake: FakeBlender) -> None:
    build(content, fake)
    fake.jobs.clear()
    (content / FOLDER / "ingrid.webp").unlink()

    build(content, fake)

    assert fake.rendered() == ["ingrid"]


def test_force_renders_everything(content: Path, fake: FakeBlender) -> None:
    build(content, fake)
    fake.jobs.clear()

    report = build(content, fake, force=True)

    assert fake.rendered() == ["player", "ingrid", "lachlan"]
    assert report.probed


def test_a_sheet_has_a_row_per_direction_and_a_column_per_frame(
    content: Path, fake: FakeBlender
) -> None:
    build(content, fake)
    m = manifest(content)
    w, h = m["frame"]["width"], m["frame"]["height"]
    cols = m["columns"]
    sheet = m["characters"]["ingrid"]
    assert (sheet["width"], sheet["height"]) == (cols * w, len(m["directions"]) * h)
    assert [d["name"] for d in m["directions"]] == list(characters.DIRECTIONS)
    assert [d["row"] for d in m["directions"]] == list(range(8))

    with Image.open(content / FOLDER / sheet["image"]) as image:
        rgba = image.convert("RGBA")
        assert rgba.size == (sheet["width"], sheet["height"])
        for animation in ("walk", "idle"):
            for d in m["directions"]:
                for index in m["animations"][animation]["frames"][d["name"]]:
                    row, col = divmod(index, cols)
                    x, y = col * w + 8, row * h + 10
                    assert rgba.getpixel((x, y)) == (row * 20, col * 10, 50, 255)
                    assert row == d["row"]


def test_frames_are_walk_then_idle_in_each_row(content: Path, fake: FakeBlender) -> None:
    build(content, fake)
    m = manifest(content)
    walk, idle = m["animations"]["walk"], m["animations"]["idle"]
    assert walk["frames"]["s"] == list(range(characters.WALK_FRAMES))
    assert idle["frames"]["se"] == [m["columns"] + c for c in range(8, 12)]
    assert m["columns"] == characters.WALK_FRAMES + characters.IDLE_FRAMES


def test_directions_point_where_the_figure_faces(content: Path, fake: FakeBlender) -> None:
    build(content, fake)
    vectors = {d["name"]: d["vector"] for d in manifest(content)["directions"]}
    assert vectors == {
        "s": [0, 1],
        "se": [1, 1],
        "e": [1, 0],
        "ne": [1, -1],
        "n": [0, -1],
        "nw": [-1, -1],
        "w": [-1, 0],
        "sw": [-1, 1],
    }


def test_the_walk_keeps_pace_with_the_residents(content: Path, fake: FakeBlender) -> None:
    build(content, fake)
    walk = manifest(content)["animations"]["walk"]
    speed = walk["fps"] / characters.WALK_FRAMES * walk["tiles_per_cycle"]
    assert speed == pytest.approx(WALKING_SPEED, rel=0.05)


def test_the_frame_is_centred_on_the_feet_with_room_for_a_tall_figure() -> None:
    f = characters.frame()
    ax, ay = f["anchor"]
    assert ax == f["width"] / 2
    assert 0.8 * f["height"] < ay < f["height"]
    assert ay > characters.HEIGHT_M * camera.UPRIGHT_PX_PER_M


def test_a_figure_reaching_the_edge_of_its_frame_fails(content: Path, fake: FakeBlender) -> None:
    fake.figure = (0, 4, 12, 20)
    with pytest.raises(characters.ClippedError, match="enlarge frame"):
        build(content, fake)


def test_per_set_constants_come_from_the_probe_and_the_sun(
    content: Path, fake: FakeBlender
) -> None:
    build(content, fake)
    sets = manifest(content)["sets"]

    assert list(sets) == list(SETS)
    for name, light in SETS.items():
        s = sets[name]
        assert s["tint"] == [0.5, 0.75, 1.0]
        assert s["shadow"]["strength"] == pytest.approx(128 / 255, abs=0.01)
        assert s["sun"] == {"azimuth": light.azimuth, "elevation": light.elevation}
        length = characters.FIGURE_M / math.tan(math.radians(light.elevation)) / 1.1
        assert s["shadow"]["length"] == pytest.approx(length, abs=0.001)
        dx, dy = s["shadow"]["direction"]
        assert math.hypot(dx, dy) == pytest.approx(1, abs=0.001)
    assert sets["evening"]["shadow"]["length"] > 4 * sets["afternoon"]["shadow"]["length"]


def test_shadows_point_away_from_the_sun(content: Path, fake: FakeBlender) -> None:
    build(content, fake)
    sets = manifest(content)["sets"]
    tip_x, tip_y = sets["afternoon"]["shadow"]["tip"]
    assert tip_x > 0
    dx, dy = sets["morning"]["shadow"]["direction"]
    assert dx < 0 and dy < 0
    assert sets["morning"]["shadow"]["tip"][1] < 0


def test_changing_a_set_measures_again_without_rendering_sheets(
    content: Path, fake: FakeBlender, monkeypatch: pytest.MonkeyPatch
) -> None:
    build(content, fake)
    fake.jobs.clear()
    dimmer = {**SETS, "night": replace(SETS["night"], sun_energy=0.2)}
    monkeypatch.setattr(characters, "SETS", dimmer)

    report = build(content, fake)

    [job] = fake.jobs
    assert job["characters"] == []
    assert report.probed
    assert [s["sun_energy"] for s in job["probe"]["sets"] if s["name"] == "night"] == [0.2]


def test_measure_compares_solid_pixels_and_the_shadow_around_the_body() -> None:
    neutral = np.zeros((40, 60, 4), np.uint8)
    neutral[5:30, 5:15] = (200, 100, 50, 255)
    lit = neutral.copy()
    lit[5:30, 5:15] = (100, 50, 50, 255)
    lit[30:34, 30:50] = (0, 0, 0, 153)

    tint, strength = characters.measure([neutral], [lit])

    assert tint == [0.5, 0.5, 1.0]
    assert strength == pytest.approx(0.6)


def test_a_tint_brighter_than_neutral_is_scaled_down_keeping_its_hue() -> None:
    neutral = np.zeros((10, 10, 4), np.uint8)
    neutral[2:8, 2:8] = (100, 100, 100, 255)
    lit = neutral.copy()
    lit[2:8, 2:8] = (120, 90, 60, 255)

    tint, _ = characters.measure([neutral], [lit])

    assert tint == [1.0, 0.75, 0.5]


def test_the_neutral_light_is_the_one_the_sheets_are_rendered_in(
    content: Path, fake: FakeBlender
) -> None:
    build(content, fake)
    [job] = fake.jobs
    assert job["light"] == NEUTRAL.params()
    assert job["probe"]["character"]["key"] == characters.PROBE


def test_the_command_reports_each_sheet(
    content: Path, fake: FakeBlender, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(characters, "blender_renderer", fake)
    args = ["art", "iso", "characters", "--content", str(content)]

    result = CliRunner().invoke(create_cli(), args)

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0].startswith("player: rendered in 1 s, ")
    assert any(line.startswith("lachlan: rendered") for line in lines)
    assert "Measured the per-set tint and shadow" in lines
    assert lines[-1].startswith("Wrote 4, removed 0")


needs_blender = pytest.mark.skipif(not blender.available(), reason="needs Blender")


@needs_blender
def test_blender_renders_a_frame_standing_on_the_anchor(content: Path, tmp_path: Path) -> None:
    job = characters.Build(content, tmp_path, force=True).job(["lachlan"], probe=False)
    job["look"] = {**job["look"], "samples": 4}
    job["directions"] = {"se": 45}
    job["animations"] = {"walk": {**job["animations"]["walk"], "frames": 1}}

    result = blender.run("render_characters.py", job, tmp_path / "work", lambda _: None)

    assert result["characters"]["lachlan"]["frames"] == 1
    f = characters.frame()
    ax, ay = f["anchor"]
    with Image.open(tmp_path / "work" / "lachlan" / "0-0.png") as image:
        assert image.size == (f["width"], f["height"])
        alpha = np.asarray(image.getchannel("A"))
    ys, xs = np.nonzero(alpha > 128)
    assert abs(ys.max() - ay) <= 6
    assert abs((xs.min() + xs.max()) / 2 - ax) <= 4
    assert ay - ys.min() > 0.9 * characters.FIGURE_M * camera.UPRIGHT_PX_PER_M
    assert not (alpha[0].any() or alpha[-1].any() or alpha[:, 0].any() or alpha[:, -1].any())


@needs_blender
def test_blender_probes_a_darker_bluer_light_at_night(content: Path, tmp_path: Path) -> None:
    job = characters.Build(content, tmp_path, force=True).job([], probe=True)
    job["look"] = {**job["look"], "samples": 4}
    job["directions"] = {"se": 45}
    job["probe"]["sets"] = [s for s in job["probe"]["sets"] if s["name"] in ("night", "morning")]

    blender.run("render_characters.py", job, tmp_path / "work", lambda _: None)

    def rgba(name: str) -> np.ndarray:
        with Image.open(tmp_path / "work" / "probe" / name / "se.png") as image:
            return np.asarray(image.convert("RGBA"))

    night, _ = characters.measure([rgba("neutral")], [rgba("night")])
    morning, shadow = characters.measure([rgba("neutral")], [rgba("morning")])
    assert sum(night) < 0.5 * sum(morning)
    assert night[2] > night[0]
    assert 0.3 < shadow < 0.9
