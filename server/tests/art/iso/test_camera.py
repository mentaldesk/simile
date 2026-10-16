import pytest

from simile.art.iso import camera


def test_tiles_are_two_to_one_diamonds() -> None:
    assert camera.project(0, 0) == (0, 0)
    assert camera.project(1, 0) == (48, 24)
    assert camera.project(0, 1) == (-48, 24)
    assert camera.project(1, 1) == (0, 48)


def test_height_moves_up_the_screen() -> None:
    _, ground = camera.project(3, 4)
    _, raised = camera.project(3, 4, 3.0)
    assert ground - raised == pytest.approx(3.0 * camera.UPRIGHT_PX_PER_M)
    assert round(camera.UPRIGHT_PX_PER_M, 2) == 53.44


@pytest.mark.parametrize("point", [(0, 0, 0), (12.5, 30.25, 0), (64, 42, 9.7), (-3, 5, 1.8)])
def test_blender_space_projects_like_the_map(point: tuple[float, float, float]) -> None:
    sx, sy = camera.screen(camera.world(*point))
    assert (sx, sy) == pytest.approx(camera.project(*point))


def test_camera_axes_are_orthonormal() -> None:
    axes = (camera.RIGHT, camera.UP, camera.FORWARD)
    for i, a in enumerate(axes):
        for j, b in enumerate(axes):
            dot = sum(x * y for x, y in zip(a, b, strict=True))
            assert dot == pytest.approx(1.0 if i == j else 0.0, abs=1e-9)


@pytest.mark.parametrize("tile", [(0, 0), (10.5, 3.25), (63, 41)])
def test_unproject_inverts_project_on_the_ground(tile: tuple[float, float]) -> None:
    assert camera.unproject(*camera.project(*tile)) == pytest.approx(tile)
