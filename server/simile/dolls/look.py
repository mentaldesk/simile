"""The colours and options a doll is cut from, read from an `Appearance`."""

from dataclasses import dataclass

from simile.dolls.colour import RGB, luminance, muted, rgb
from simile.schema import Appearance

BUILD = {"slim": 0.86, "average": 1.0, "broad": 1.2}


@dataclass(frozen=True)
class Look:
    skin: RGB
    hair: RGB
    top: RGB
    bottom: RGB
    shoe: RGB
    accent: RGB
    apron: RGB
    hair_style: str
    width: float
    accessories: frozenset[str]

    @classmethod
    def of(cls, appearance: Appearance, seed: str | None) -> "Look":
        """Skin is kept exactly; everything else is muted to sit in the papercraft world. The
        accent and apron follow A1's sprites (`Colours`), seeded by the character's id."""
        from simile.art.characters import Colours
        from simile.art.palette import PALETTE

        sprite = Colours.of(appearance, seed=seed)
        return cls(
            skin=rgb(appearance.skin),
            hair=muted(rgb(appearance.hair_colour)),
            top=muted(rgb(appearance.top_colour)),
            bottom=muted(rgb(appearance.bottom_colour)),
            shoe=muted(rgb(appearance.shoe_colour)),
            accent=muted(rgb(PALETTE[sprite.accent])),
            apron=muted(rgb(PALETTE[sprite.apron])),
            hair_style=appearance.hair_style.value,
            width=BUILD[appearance.build.value],
            accessories=frozenset(a.value for a in appearance.accessories),
        )

    @property
    def light_hair(self) -> bool:
        return luminance(self.hair) > 0.5
