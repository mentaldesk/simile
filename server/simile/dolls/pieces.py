"""A doll's pieces as pictures: each with its pivot and the joints its children hang from."""

from dataclasses import dataclass

from PIL import Image

from simile.dolls.look import Look
from simile.dolls.shapes import PIECES, SHAPES, Pen

Px = tuple[float, float]


@dataclass
class Piece:
    image: Image.Image
    pivot: Px
    joints: dict[str, Px]

    def trimmed(self, pad: int = 2) -> "Piece":
        box = self.image.getchannel("A").getbbox()
        if box is None:
            return self
        x0, y0 = max(0, box[0] - pad), max(0, box[1] - pad)
        x1 = min(self.image.width, box[2] + pad)
        y1 = min(self.image.height, box[3] + pad)

        def shift(p: Px) -> Px:
            return p[0] - x0, p[1] - y0

        return Piece(
            self.image.crop((x0, y0, x1, y1)),
            shift(self.pivot),
            {k: shift(v) for k, v in self.joints.items()},
        )


def flat_piece(name: str, look: Look, scale: float) -> Piece:
    shape = SHAPES[name]
    pen = Pen(shape.box, scale)
    shape.draw(pen, look)
    joints = {k: pen.px(v) for k, v in shape.joints(look).items()}
    return Piece(pen.image(), pen.px((0.0, 0.0)), joints).trimmed()


def flat_pieces(look: Look, scale: float, names: tuple[str, ...] = PIECES) -> dict[str, Piece]:
    """`scale` is pixels per unit."""
    return {name: flat_piece(name, look, scale) for name in names}
