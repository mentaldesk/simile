from simile.schema import Item, ItemKind, Material


def plastic(amount: float = 1.0) -> Item:
    return Item(
        id="plastic",
        kind=ItemKind.MATERIAL,
        name="Plastic",
        weight=0.5,
        amount=amount,
        material=Material.PLASTIC,
    )
