from pathlib import Path

import pytest
from PIL import Image

from simile.art.iso import blender, camera, scenery
from simile.art.iso.lighting import SETS
from simile.art.iso.town import Town

from .conftest import VILLAGE

needs_blender = pytest.mark.skipif(not blender.available(), reason="needs Blender")


def test_blender_is_found_from_the_environment_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BLENDER", "/opt/blender/blender")
    assert blender.find() == "/opt/blender/blender"


def test_without_blender_running_says_how_to_get_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("BLENDER", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(blender, "MAC_APP", tmp_path / "missing")

    assert not blender.available()
    with pytest.raises(blender.BlenderError, match="BLENDER"):
        blender.run("render_scenery.py", {}, tmp_path)


def test_a_failing_script_reports_blenders_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = tmp_path / "blender"
    fake.write_text("#!/bin/sh\necho 'Error: no such thing'\nexit 1\n")
    fake.chmod(0o755)
    monkeypatch.setenv("BLENDER", str(fake))

    with pytest.raises(blender.BlenderError, match="no such thing"):
        blender.run("render_scenery.py", {}, tmp_path)


def test_a_crashed_blender_is_run_again(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = tmp_path / "blender"
    fake.write_text(
        "#!/bin/sh\n"
        f"if [ ! -f {tmp_path}/crashed ]; then touch {tmp_path}/crashed; kill -ABRT $$; fi\n"
        'for last; do :; done; echo \'{"ok": true}\' > "$last"\n'
    )
    fake.chmod(0o755)
    monkeypatch.setenv("BLENDER", str(fake))
    lines: list[str] = []

    assert blender.run("render_scenery.py", {}, tmp_path / "work", lines.append) == {"ok": True}
    assert lines == ["Blender crashed (-6); running it again"]


@needs_blender
def test_blender_renders_a_sprite_and_says_where_it_landed(tmp_path: Path) -> None:
    town = Town(VILLAGE)
    bollard = next(p for p in town.props if p.kind == "bollard")
    plan = scenery.plan(town, SETS["afternoon"])
    build = scenery.SetBuild(plan, tmp_path / "content", tmp_path, force=True)
    job = build.job([plan.sprites[bollard.id]], ground=False, light_map=False)
    job["look"] = {**job["look"], "samples": 4}

    result = blender.run("render_scenery.py", job, tmp_path / "work", progress=lambda _: None)

    x0, y0, w, h = result["sprites"][bollard.id]["rect"]
    ax, ay = camera.project(bollard.x, bollard.y)
    with Image.open(tmp_path / "work" / "sprites" / f"{bollard.id}.png") as image:
        assert image.size == (w, h)
        assert image.mode == "RGBA"
        alpha = image.getchannel("A")
        assert alpha.getpixel((0, 0)) == 0
        assert alpha.getpixel((round(ax) - x0, round(ay) - y0 - 5)) == 255
