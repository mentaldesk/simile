import subprocess
import sys

HEAVY = ("mflux", "mlx", "torch", "onnxruntime", "cv2")


def test_the_command_and_the_build_import_nothing_heavy() -> None:
    modules = ", ".join(
        f"simile.papercraft.{m}" for m in ("cli", "build", "catalogue", "layout", "preview")
    )
    code = f"import sys, {modules}; print(' '.join(m for m in {HEAVY!r} if m in sys.modules))"

    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)

    assert out.stdout.strip() == ""
