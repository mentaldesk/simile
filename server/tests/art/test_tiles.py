import pytest

from simile.art.palette import PALETTE
from simile.art.tiles import (
    COLUMNS,
    FINISHES,
    MATERIALS,
    TERRAINS,
    TILE_SIZE,
    edge_variant,
    groups,
    layout,
    tile_ids,
    tileset_canvas,
    tileset_json,
)

CELLS = layout()
TILES = {tile.name: tile for tile in CELLS if tile is not None}
OPAQUE_GROUPS = {
    "ground",
    "grass edges",
    "road edges",
    "water edges",
    "roofs",
    "green roofs",
    "cream facades",
    "slate facades",
    "floors",
    "interior walls",
}


def column(name: str, x: int) -> list[str | None]:
    return [TILES[name].canvas.get(x, y) for y in range(TILE_SIZE)]


def row(name: str, y: int) -> list[str | None]:
    return [TILES[name].canvas.get(x, y) for x in range(TILE_SIZE)]


def test_tiles_are_16px_and_use_only_the_palette() -> None:
    for tile in TILES.values():
        assert (tile.canvas.width, tile.canvas.height) == (TILE_SIZE, TILE_SIZE)
        assert tile.canvas.colours() <= set(PALETTE), tile.name


def test_tile_names_are_unique() -> None:
    names = [tile.name for group in groups() for tile in group.tiles]
    assert len(names) == len(set(names))


def test_ground_building_and_roof_tiles_are_opaque() -> None:
    for group in groups():
        if group.name in OPAQUE_GROUPS:
            for tile in group.tiles:
                assert None not in {c for r in tile.canvas.pixels for c in r}, tile.name


def test_tileset_image_places_each_tile_at_its_id() -> None:
    image = tileset_canvas(CELLS).to_image()
    assert len(CELLS) % COLUMNS == 0
    assert image.size == (COLUMNS * TILE_SIZE, len(CELLS) // COLUMNS * TILE_SIZE)
    for name, i in tile_ids(CELLS).items():
        x, y = i % COLUMNS * TILE_SIZE, i // COLUMNS * TILE_SIZE
        piece = image.crop((x, y, x + TILE_SIZE, y + TILE_SIZE))
        assert piece.tobytes() == TILES[name].canvas.to_image().tobytes(), name


def test_tiled_tileset_is_consistent() -> None:
    data = tileset_json(CELLS)
    assert data["type"] == "tileset"
    assert data["imagewidth"] == data["columns"] * data["tilewidth"]
    assert data["tilecount"] == data["columns"] * data["imageheight"] // data["tileheight"]
    names = {}
    for tile in data["tiles"]:
        assert 0 <= tile["id"] < data["tilecount"]
        props = {p["name"]: p for p in tile["properties"]}
        assert set(props) == {"name", "collides", "above"}
        assert props["collides"]["type"] == props["above"]["type"] == "bool"
        names[props["name"]["value"]] = tile["id"]
    assert names == tile_ids(CELLS)

    by_id = {i: name for name, i in names.items()}
    assert [w["name"] for w in data["wangsets"]] == list(TERRAINS)
    for wangset in data["wangsets"]:
        assert wangset["type"] == "corner"
        corners = set()
        for wangtile in wangset["wangtiles"]:
            name = by_id[wangtile["tileid"]]
            assert name == "pavement" or name.startswith(wangset["name"])
            wangid = wangtile["wangid"]
            assert wangid[0::2] == [0, 0, 0, 0]
            assert set(wangid[1::2]) <= {1, 2}
            corners.add(tuple(wangid))
        assert len(corners) == len(wangset["wangtiles"]) == 14


@pytest.mark.parametrize(
    ("paved", "expected"),
    [
        (set(), "grass"),
        ({(0, -1)}, "grass_n"),
        ({(-1, 0)}, "grass_w"),
        ({(0, -1), (1, 0), (1, -1)}, "grass_ne"),
        ({(0, 1), (-1, 0)}, "grass_sw"),
        ({(1, -1)}, "grass_ne_nook"),
        ({(-1, 1)}, "grass_sw_nook"),
    ],
)
def test_edge_variant_names_the_tile_for_its_neighbours(
    paved: set[tuple[int, int]], expected: str
) -> None:
    assert edge_variant("grass", lambda dx, dy: (dx, dy) not in paved) == expected
    assert expected in TILES


def test_edge_bands_are_uniform_so_neighbouring_edges_join() -> None:
    for terrain in TERRAINS:
        for side in ("n", "s"):
            for y in range(TILE_SIZE):
                if row(f"{terrain}_{side}", y) != row(terrain, y):
                    assert len(set(row(f"{terrain}_{side}", y))) == 1, (terrain, side, y)
        for side in ("e", "w"):
            for x in range(TILE_SIZE):
                if column(f"{terrain}_{side}", x) != column(terrain, x):
                    assert len(set(column(f"{terrain}_{side}", x))) == 1, (terrain, side, x)


def test_facade_pieces_share_edges_so_any_two_join() -> None:
    for m in MATERIALS:
        rows = [
            ([f"wall_{m}", f"window_{m}", f"door_{m}_top"], f"wall_{m}_l", f"wall_{m}_r"),
            ([f"base_{m}", f"base_window_{m}", f"door_{m}"], f"base_{m}_l", f"base_{m}_r"),
        ]
        for pieces, left_end, right_end in rows:
            reference = pieces[0]
            for name in pieces:
                assert column(name, 0) == column(reference, 0), name
                assert column(name, 15) == column(reference, 15), name
            assert column(left_end, 15) == column(reference, 15)
            assert column(right_end, 0) == column(reference, 0)


def test_collision_and_draw_order_flags() -> None:
    assert TILES["water"].collides
    assert TILES["water_ne_nook"].collides
    assert not TILES["pavement"].collides
    assert not TILES["grass_n"].collides
    assert TILES["roof"].collides
    assert TILES["door_cream"].collides
    for name in ("tree_tl", "tree_tr", "terminal_top", "lamp_top", "palm_top", "vending_top"):
        assert TILES[name].above and not TILES[name].collides, name
    for name in ("tree_bl", "terminal", "lamp", "palm", "vending", "bench_l", "fountain_br"):
        assert TILES[name].collides and not TILES[name].above, name


def test_rooms_are_walked_on_their_floors_mats_and_stools_and_nothing_else() -> None:
    interior = groups()[-7:]
    walk_on = {"mat", "stool"}
    on_walls = {"shelf", "menu_board_l", "menu_board_r", "lantern", "pegboard_l", "pegboard_r"}
    on_walls |= {"frame_l", "frame_r"}

    assert interior[0].name == "floors"
    for group in interior:
        for tile in group.tiles:
            walkable = group.name == "floors" or tile.name in walk_on | on_walls
            assert tile.collides != walkable, tile.name
            assert not tile.above, tile.name


def test_interior_walls_come_in_every_finish_with_ends_for_free_standing_walls() -> None:
    for material in FINISHES:
        for row in (f"inwall_{material}", f"inwall_{material}_base"):
            for name in (f"{row}_l", row, f"{row}_r"):
                assert TILES[name].collides, name
            assert column(f"{row}_l", 15) == column(row, 15)
            assert column(f"{row}_r", 0) == column(row, 0)


def test_interior_tiles_are_added_after_the_village_tiles() -> None:
    ids = tile_ids(CELLS)
    village = max(ids[name] for name in ("blocked", "fountain_br", "vending"))
    assert min(ids[name] for name in ("floor_wood", "mat", "inwall_plaster", "plinth")) > village
    assert ids["blocked"] == 208
