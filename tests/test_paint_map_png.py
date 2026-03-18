import unittest

from tilemap_generator.paint_map_png import (
    _ocean_connected_water_cells,
    close_ocean_shoreline_gaps,
    count_adjacent_shoreline_cells,
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


if __name__ == "__main__":
    unittest.main()
