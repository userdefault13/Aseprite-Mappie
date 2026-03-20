import unittest

from tilemap_generator.paint_map_png import (
    LAKE_WATER_CHARS,
    _lake_mask_with_diagonal_inference,
    _ocean_connected_water_cells,
    close_lake_shoreline_gaps,
    close_ocean_shoreline_gaps,
    filter_isolated_lake_shoreline,
    count_adjacent_shoreline_cells,
    get_water_adjacency_bitmask,
    get_water_adjacency_with_type,
    match_lake_shoreline_special_tile,
    match_ocean_inset_special_tile,
    match_ocean_shoreline_special_tile,
    propagate_shore_masks,
    resolve_center_ocean_inset_tile,
    resolve_bottom_ocean_inset_tile,
)


class PropagateShoreMasksTests(unittest.TestCase):
    def _water_mask_grid(self, ascii_lines: list[str]) -> list[list[int]]:
        height = len(ascii_lines)
        width = max((len(row) for row in ascii_lines), default=0)
        grid = [[0] * width for _ in range(height)]
        for y in range(height):
            for x in range(width):
                grid[y][x], _ = get_water_adjacency_with_type(
                    ascii_lines,
                    x,
                    y,
                    border_width=0,
                    ascii_water_border=0,
                )
        return grid

    def test_propagates_across_expanded_continent_shore(self) -> None:
        ascii_lines = [
            "~~~~..",
            "~BBB..",
            "~BBB..",
            "~BBB..",
            "......",
        ]

        masks = propagate_shore_masks(ascii_lines, self._water_mask_grid(ascii_lines))

        self.assertEqual(masks[3][3], 9)

    def test_does_not_cross_into_other_shore_types(self) -> None:
        ascii_lines = [
            "~..",
            "LB.",
            "...",
        ]

        masks = propagate_shore_masks(ascii_lines, self._water_mask_grid(ascii_lines))

        self.assertEqual(masks[1][1], 0)

    def test_ocean_connected_water_is_not_classified_as_lake(self) -> None:
        ascii_lines = [
            "...~...",
            "...~...",
            "..B~...",
            "...~...",
            ".......",
            ".......",
            ".......",
        ]

        ocean_connected = _ocean_connected_water_cells(
            ascii_lines,
            width=max(len(row) for row in ascii_lines),
            height=len(ascii_lines),
        )

        mask, is_lake = get_water_adjacency_with_type(
            ascii_lines,
            2,
            2,
            border_width=2,
            ascii_water_border=2,
            ocean_connected=ocean_connected,
        )

        self.assertEqual(mask, 2)
        self.assertFalse(is_lake)

    def test_surrounded_inset_does_not_force_special_tile(self) -> None:
        tile = match_ocean_inset_special_tile(
            has_n=True,
            has_e=True,
            has_s=True,
            has_w=True,
            edge_tiles={"bottom": 33},
            corner_tiles={},
        )

        self.assertIsNone(tile)

    def test_horizontal_inset_uses_top_left_corner_tile_from_diagonal(self) -> None:
        tile = match_ocean_inset_special_tile(
            has_n=False,
            has_e=True,
            has_s=False,
            has_w=True,
            edge_tiles={},
            corner_tiles={"top_left": 36},
            direct_corner_tiles={},
            has_nw=True,
        )

        self.assertEqual(tile, 36)

    def test_vertical_inset_uses_bottom_right_corner_tile_from_diagonal(self) -> None:
        tile = match_ocean_inset_special_tile(
            has_n=True,
            has_e=False,
            has_s=True,
            has_w=False,
            edge_tiles={},
            corner_tiles={"bottom_right": 39},
            direct_corner_tiles={},
            has_se=True,
        )

        self.assertEqual(tile, 39)

    def test_direct_top_left_inset_prefers_direct_corner_tile(self) -> None:
        tile = match_ocean_inset_special_tile(
            has_n=False,
            has_e=False,
            has_s=True,
            has_w=True,
            edge_tiles={},
            corner_tiles={"top_left": 36},
            direct_corner_tiles={"direct_top_left": 37},
        )

        self.assertEqual(tile, 37)

    def test_direct_bottom_left_inset_prefers_direct_corner_tile(self) -> None:
        tile = match_ocean_inset_special_tile(
            has_n=True,
            has_e=False,
            has_s=False,
            has_w=True,
            edge_tiles={},
            corner_tiles={"bottom_left": 38},
            direct_corner_tiles={"direct_bottom_left": 41},
        )

        self.assertEqual(tile, 41)

    def test_direct_bottom_right_inset_prefers_direct_corner_tile(self) -> None:
        tile = match_ocean_inset_special_tile(
            has_n=True,
            has_e=True,
            has_s=False,
            has_w=False,
            edge_tiles={},
            corner_tiles={"bottom_right": 39},
            direct_corner_tiles={"direct_bottom_right": 40},
        )

        self.assertEqual(tile, 40)

    def test_bottom_inset_uses_left_variant_when_north_tile_is_10(self) -> None:
        tile = resolve_bottom_ocean_inset_tile(
            10,
            edge_tiles={"bottom": 33},
            direct_corner_tiles={"direct_bottom_left": 41, "direct_bottom_right": 40},
        )

        self.assertEqual(tile, 41)

    def test_bottom_inset_uses_right_variant_when_north_tile_is_4(self) -> None:
        tile = resolve_bottom_ocean_inset_tile(
            4,
            edge_tiles={"bottom": 33},
            direct_corner_tiles={"direct_bottom_left": 41, "direct_bottom_right": 40},
        )

        self.assertEqual(tile, 40)

    def test_center_inset_uses_tile_42_for_north_10_east_7(self) -> None:
        tile = resolve_center_ocean_inset_tile(
            10,
            7,
            edge_tiles={"center": 42},
        )

        self.assertEqual(tile, 42)

    def test_explicit_shoreline_tee_west_uses_special_tile(self) -> None:
        tile = match_ocean_shoreline_special_tile(
            has_n=True,
            has_e=True,
            has_s=True,
            has_w=False,
            water_mask=8,
            special_tiles={"tee_west": 32},
        )

        self.assertEqual(tile, 32)

    def test_explicit_shoreline_west_water_vertical_uses_special_tile(self) -> None:
        tile = match_ocean_shoreline_special_tile(
            has_n=True,
            has_e=False,
            has_s=True,
            has_w=False,
            water_mask=8,
            special_tiles={"lake_east": 9},
        )

        self.assertEqual(tile, 9)

    def test_explicit_shoreline_tee_east_uses_special_tile(self) -> None:
        tile = match_ocean_shoreline_special_tile(
            has_n=True,
            has_e=False,
            has_s=True,
            has_w=True,
            water_mask=2,
            special_tiles={"tee_east": 33},
        )

        self.assertEqual(tile, 33)

    def test_explicit_lakebank_beach_west_uses_special_tile(self) -> None:
        tile = match_lake_shoreline_special_tile(
            has_n=False,
            has_e=False,
            has_s=False,
            has_w=False,
            water_mask=2,
            special_tiles={"beach_west": 7},
            has_w_beach=True,
        )

        self.assertEqual(tile, 7)

    def test_counts_adjacent_shoreline_cells(self) -> None:
        ascii_lines = [
            ".B.",
            "BG.",
            "...",
        ]

        self.assertEqual(count_adjacent_shoreline_cells(ascii_lines, 1, 1), 2)

    def test_closes_single_land_gap_between_shoreline_cells(self) -> None:
        ascii_lines = [
            "BBB",
            "BGB",
            "BBB",
        ]

        closed = close_ocean_shoreline_gaps(ascii_lines)

        self.assertEqual(closed[1][1], "B")

    def test_does_not_flood_fill_interior_land(self) -> None:
        ascii_lines = [
            "BBBB",
            "BGGG",
            "BGGG",
            "BGGG",
        ]

        closed = close_ocean_shoreline_gaps(ascii_lines)

        self.assertEqual(closed, ascii_lines)

    def test_promotes_tree_bridge_for_diagonal_shoreline_connection(self) -> None:
        ascii_lines = [
            "B~",
            "TB",
        ]

        closed = close_ocean_shoreline_gaps(ascii_lines)

        self.assertEqual(closed[1][0], "B")

    def test_extends_coastal_shoreline_through_path_cells(self) -> None:
        ascii_lines = [
            "~B",
            "~B",
            "~P",
            "~P",
        ]

        closed = close_ocean_shoreline_gaps(ascii_lines)

        self.assertEqual(closed[2][1], "B")
        self.assertEqual(closed[3][1], "B")

    def test_all_ocean_adjacent_land_becomes_shoreline(self) -> None:
        ascii_lines = [
            "~~~~",
            "~PGJ",
            "~GGG",
            "~~~~",
        ]

        closed = close_ocean_shoreline_gaps(ascii_lines)

        self.assertEqual(closed[1][1], "B")
        self.assertEqual(closed[1][3], "B")
        self.assertEqual(closed[2][1], "B")

    def test_trims_landward_corner_from_2x2_shoreline_block(self) -> None:
        ascii_lines = [
            "GGGG",
            "~BBG",
            "~BBG",
            "~~~~",
        ]

        closed = close_ocean_shoreline_gaps(ascii_lines)

        self.assertEqual(closed[1][2], "G")


class CloseLakeShorelineGapsTests(unittest.TestCase):
    def test_closes_diagonal_water_gap_between_l_cells(self) -> None:
        ascii_lines = [
            "LL",
            "~L",
        ]

        closed = close_lake_shoreline_gaps(ascii_lines)

        self.assertEqual(closed[1][0], "L")

    def test_closes_straight_water_gap_between_l_cells(self) -> None:
        ascii_lines = [
            "L~L",
        ]

        closed = close_lake_shoreline_gaps(ascii_lines)

        self.assertEqual(closed[0][1], "L")

    def test_no_promotion_when_water_not_between_l_cells(self) -> None:
        ascii_lines = [
            "~~~",
            "~L~",
            "~~~",
        ]

        closed = close_lake_shoreline_gaps(ascii_lines)

        self.assertEqual(closed[0][1], "~")
        self.assertEqual(closed[1][0], "~")
        self.assertEqual(closed[1][2], "~")
        self.assertEqual(closed[2][1], "~")

    def test_promotes_water_with_two_l_neighbors(self) -> None:
        ascii_lines = [
            "L~L",
            "~L~",
        ]

        closed = close_lake_shoreline_gaps(ascii_lines)

        self.assertEqual(closed[0][1], "L")
        self.assertEqual(closed[1][0], "L")
        self.assertEqual(closed[1][2], "L")


class FilterIsolatedLakeShorelineTests(unittest.TestCase):
    """Lake outline rule: L needs at least 2 NESW lake neighbors (water or L) to avoid diagonals."""

    def test_demotes_l_with_one_lake_neighbor(self) -> None:
        # L at (1,0) touches only ~ at (0,0) -> 1 neighbor -> demote to G
        ascii_lines = [
            "~L.",
            "...",
        ]
        out = filter_isolated_lake_shoreline(ascii_lines)
        self.assertEqual(out[0][1], "G")

    def test_keeps_l_with_two_lake_neighbors(self) -> None:
        # L at (1,1) touches ~ at (0,1) and (2,1) -> 2 neighbors -> keep L
        ascii_lines = [
            "...",
            "~L~",
            "...",
        ]
        out = filter_isolated_lake_shoreline(ascii_lines)
        self.assertEqual(out[1][1], "L")

    def test_demotion_cascades(self) -> None:
        # L at (0,1) has only L(1,0) -> demote. Then L at (1,0) has only ~(0,0) -> demote.
        ascii_lines = [
            "~L",
            "L.",
        ]
        out = filter_isolated_lake_shoreline(ascii_lines)
        self.assertEqual(out[0][1], "G")
        self.assertEqual(out[1][0], "G")


class LakeMaskDiagonalInferenceTests(unittest.TestCase):
    def test_n_edge_with_ne_water_upgrades_to_n_e_corner(self) -> None:
        ascii_lines = [
            "~L~",
            "L.L",
            "...",
        ]
        mask = _lake_mask_with_diagonal_inference(ascii_lines, 1, 1, 1)
        self.assertEqual(mask, 3)

    def test_n_edge_with_nw_water_upgrades_to_n_w_corner(self) -> None:
        ascii_lines = [
            "~L",
            "L.",
            "..",
        ]
        mask = _lake_mask_with_diagonal_inference(ascii_lines, 1, 1, 1)
        self.assertEqual(mask, 9)

    def test_single_edge_without_diagonal_water_unchanged(self) -> None:
        ascii_lines = [
            ".L.",
            "L.G",
            "...",
        ]
        mask = _lake_mask_with_diagonal_inference(ascii_lines, 1, 1, 1)
        self.assertEqual(mask, 1)


class LakeWaterCharsMaskTests(unittest.TestCase):
    """Lake mask should treat L/R as water so straight edges get correct tiles."""

    def test_vertical_strip_gets_mask_7_with_lake_chars(self) -> None:
        # West column: N=~, E=~, S=L, W=G. With LAKE_WATER_CHARS, S=L counts -> mask 7
        ascii_lines = [
            "G~GG",
            "GL~G",
            "GL~G",
            "G~GG",
        ]
        mask = get_water_adjacency_bitmask(
            ascii_lines, 1, 1, water_chars=LAKE_WATER_CHARS, border_width=0
        )
        self.assertEqual(mask, 7, "N+E+S water -> vertical strip (tile 8)")

    def test_water_chars_only_gives_mask_3_for_same_layout(self) -> None:
        # With WATER_CHARS only, S=L does not count -> mask 3 (corner)
        from tilemap_generator.paint_map_png import WATER_CHARS

        ascii_lines = [
            "G~GG",
            "GL~G",
            "GL~G",
            "G~GG",
        ]
        mask = get_water_adjacency_bitmask(
            ascii_lines, 1, 1, water_chars=WATER_CHARS, border_width=0
        )
        self.assertEqual(mask, 3, "N+E only -> corner (wrong for straight edge)")


if __name__ == "__main__":
    unittest.main()
