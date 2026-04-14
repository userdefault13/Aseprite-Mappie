import unittest
from unittest.mock import patch

from tilemap_generator.paint_map_png import (
    HILL_MAP,
    _diagonal_inset_pattern_key_for_geometry,
    _ne_inset_br_probe_one_row_above,
    _ne_inset_tl_probe_one_column_left,
    _sw_inset_br_probe_two_columns_left,
    _sw_inset_turn_east_from_grass_notch,
    _sw_inset_tl_probe_two_rows_below,
    _se_inset_bl_probe_one_column_left,
    _se_inset_tr_probe_one_row_below,
    _nw_inset_bl_probe_two_rows_above,
    _nw_inset_tr_probe_two_columns_left,
    parse_hill_diagonal_inset_2x2_patterns,
    apply_hill_mask11_tee_neighbor_gate,
    apply_hill_peninsula_protrusion_adjacent_pass,
    apply_hill_peninsula_vertical_spine_pass,
    resolve_hill_peninsula_n_junction_tile_id,
    apply_hill_vertical_spine_tile_fix,
    apply_hill_diagonal_inset_neighbor_rules,
    apply_hill_peninsula_post_inset_tile_restore_pass,
    collect_hill_raw_peninsula_tip_tile_snapshot,
    resolve_hill_horizontal_ridge_tile_id,
    resolve_hill_mask11_corner_extension_connect_tile_id,
    resolve_hill_mask14_n_peninsula_connector_tile_id,
    resolve_hill_vertical_ridge_tile_id,
    LAKE_WATER_CHARS,
    _lake_mask_with_diagonal_inference,
    _ocean_connected_water_cells,
    close_lake_shoreline_gaps,
    close_ocean_shoreline_gaps,
    filter_isolated_lake_shoreline,
    count_adjacent_shoreline_cells,
    compute_hill_autotile_mask,
    get_hill_adjacency_bitmask,
    get_water_adjacency_bitmask,
    get_water_adjacency_with_type,
    match_lake_shoreline_special_tile,
    match_ocean_inset_special_tile,
    match_ocean_shoreline_special_tile,
    propagate_shore_masks,
    resolve_center_ocean_inset_tile,
    resolve_bottom_ocean_inset_tile,
    resolve_hill_autotile_tile_id,
    hill_mask5_vertical_spine_open_diagonals_for_tile24,
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

    def test_does_not_promote_interior_lake_center(self) -> None:
        """Center of 3x3 lake (water with L on all 4 sides) must stay water, not become L."""
        ascii_lines = [
            "LLL",
            "L~L",
            "LLL",
        ]

        closed = close_lake_shoreline_gaps(ascii_lines)

        self.assertEqual(closed[1][1], "~", "Center must remain water, not be promoted to L")


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


class HillAutotileInteriorExclusionTests(unittest.TestCase):
    """Rim tiles should not see fully surrounded I as cliff neighbors (fill_hill_interior case)."""

    def test_mask5_all_diagonals_grass_uses_tile24(self) -> None:
        # N+S ridge; E/W grass; all four diagonals in-bounds and grass-like -> 24 not 9
        lines = ["GIG", "GIG", "GIG"]
        self.assertTrue(hill_mask5_vertical_spine_open_diagonals_for_tile24(lines, 1, 1, hill_char="I"))
        self.assertEqual(resolve_hill_autotile_tile_id(lines, 1, 1, HILL_MAP), 24)

    def test_mask5_diagonal_hill_stays_tile9(self) -> None:
        lines = ["GIG", "GIG", "IIG"]
        self.assertFalse(hill_mask5_vertical_spine_open_diagonals_for_tile24(lines, 1, 1, hill_char="I"))
        self.assertEqual(resolve_hill_autotile_tile_id(lines, 1, 1, HILL_MAP), HILL_MAP[5])

    def test_outer_corner_es_when_both_neighbors_interior_uses_mask6_tile(self) -> None:
        """NW grass notch: N+W open, E+S are I (both mesa interior). Must stay mask 6 / hill_map[6].

        Interior exclusion used to drop both cardinals → wrong peninsula or isolated tile instead of
        E+S outer corner (user sheet may map mask 6 → tile 5; default HILL_MAP[6] is 2).
        """
        lines = [
            "GGGGG",
            "GGGII",
            "GGIII",
            "GIIII",
            "GIIII",
        ]
        self.assertEqual(compute_hill_autotile_mask(lines, 2, 2, hill_char="I"), 6)
        self.assertEqual(resolve_hill_autotile_tile_id(lines, 2, 2, HILL_MAP), HILL_MAP[6])

    def test_two_wide_vertical_strip_middle_uses_spine_9_and_7(self) -> None:
        # 2×5 II pill: outer faces are mask 7 / 13 — spine cliffs 9 / 7, not tee 28/30
        lines = [
            "GIIG",
            "GIIG",
            "GIIG",
            "GIIG",
            "GIIG",
        ]
        self.assertEqual(resolve_hill_autotile_tile_id(lines, 1, 2, HILL_MAP), HILL_MAP[5])
        self.assertEqual(resolve_hill_autotile_tile_id(lines, 2, 2, HILL_MAP), 7)

    def test_three_wide_left_column_is_mask5_not_two_wide_strip_pair(self) -> None:
        # 3 columns: east neighbor is interior I (excluded) → autotile mask 5, not 7+13 pair
        lines = [
            "GIIIIG",
            "GIIIIG",
            "GIIIIG",
        ]
        from tilemap_generator.paint_map_png import compute_hill_autotile_mask, hill_two_wide_vertical_strip_spine_tile_id

        h = compute_hill_autotile_mask(lines, 1, 1, hill_char="I")
        self.assertEqual(h, 5)
        self.assertIsNone(hill_two_wide_vertical_strip_spine_tile_id(lines, 1, 1, h, HILL_MAP))

    def test_three_wide_plateau_rim_mask5_cliff_faces_from_raw_cardinals(self) -> None:
        # Interior-excluded mask 5 on both vertical rims; raw W vs E still picks stable 9 / 7.
        lines = [
            "GIIIIG",
            "GIIIIG",
            "GIIIIG",
        ]
        self.assertEqual(resolve_hill_autotile_tile_id(lines, 1, 1, HILL_MAP), 9)
        self.assertEqual(resolve_hill_autotile_tile_id(lines, 4, 1, HILL_MAP), 7)

    def test_two_row_horizontal_strip_middle_uses_spine_6_and_8(self) -> None:
        # n×2 II pill (2 rows): top/bottom faces are mask 14 / 11 — ridge 6 / 8, not tee 26/32
        lines = [
            "GGIIIII",
            "GGIIIII",
        ]
        self.assertEqual(resolve_hill_autotile_tile_id(lines, 3, 0, HILL_MAP), 6)
        self.assertEqual(resolve_hill_autotile_tile_id(lines, 3, 1, HILL_MAP), 8)

    def test_three_tall_top_row_not_two_row_strip_spine(self) -> None:
        # 3 rows: S neighbor is interior (excluded) → autotile mask 10, not 14+11 pair
        lines = [
            "GIIIIIG",
            "GIIIIIG",
            "GIIIIIG",
        ]
        from tilemap_generator.paint_map_png import compute_hill_autotile_mask, hill_two_wide_horizontal_strip_spine_tile_id

        h = compute_hill_autotile_mask(lines, 3, 0, hill_char="I")
        self.assertEqual(h, 10)
        self.assertIsNone(hill_two_wide_horizontal_strip_spine_tile_id(lines, 3, 0, h, HILL_MAP))

    def test_rim_top_mid_raw_tee_excl_ridge(self) -> None:
        lines = ["III", "III", "III"]
        raw = get_hill_adjacency_bitmask(lines, 1, 0)
        excl = get_hill_adjacency_bitmask(lines, 1, 0, exclude_interior_hill_neighbors=True)
        self.assertEqual(raw, 14, "raw: S is interior I -> tee mask (N open)")
        self.assertEqual(excl, 10, "excl: ignore interior -> E+W ridge")
        ridge = resolve_hill_autotile_tile_id(lines, 1, 0, HILL_MAP)
        self.assertEqual(ridge, HILL_MAP[10])

    def test_plateau_center_not_articulation_resolve_still_mask15(self) -> None:
        from tilemap_generator.paint_map_png import is_hill_deep_interior_cell, is_hill_mask15_articulation_point

        lines = ["III", "III", "III"]
        self.assertTrue(is_hill_deep_interior_cell(lines, 1, 1))
        self.assertFalse(is_hill_mask15_articulation_point(lines, 1, 1))
        # Autotile still maps raw 15 → hill_map[15]; painter skips hill layer for deep interior
        self.assertEqual(resolve_hill_autotile_tile_id(lines, 1, 1, HILL_MAP), HILL_MAP[15])

    def test_plus_center_is_articulation_not_deep_interior(self) -> None:
        from tilemap_generator.paint_map_png import is_hill_deep_interior_cell, is_hill_mask15_articulation_point

        lines = ["..I..", ".III.", "..I.."]
        self.assertTrue(is_hill_mask15_articulation_point(lines, 2, 1))
        self.assertFalse(is_hill_deep_interior_cell(lines, 2, 1))


class HillVerticalSpineTileFixTests(unittest.TestCase):
    def test_replaces_e_peninsula_when_n_and_s_are_hill(self) -> None:
        # Single column of I: middle cell has raw mask 5 but wrong tile 11 (E peninsula).
        lines = ["I", "I", "I"]
        w, h = 1, 3
        base = [[9], [11], [9]]
        apply_hill_vertical_spine_tile_fix(lines, base, w, h, HILL_MAP, hill_char="I")
        self.assertEqual(base[1][0], 9)

    def test_skip_coords_preserves_tile(self) -> None:
        """Mask-5 vertical spine overwrites ridge_default (9); skip_coords keeps prior id."""
        lines = [
            "IIIII",
            "GIGGG",
            "IIIII",
        ]
        w, h = 5, 3
        base = [[1] * w for _ in range(h)]
        base[1][1] = 2
        apply_hill_vertical_spine_tile_fix(lines, base, w, h, HILL_MAP, hill_char="I")
        self.assertEqual(base[1][1], 9)
        base2 = [[1] * w for _ in range(h)]
        base2[1][1] = 2
        apply_hill_vertical_spine_tile_fix(
            lines, base2, w, h, HILL_MAP, hill_char="I", skip_coords=frozenset({(1, 1)})
        )
        self.assertEqual(base2[1][1], 2)


class HillVerticalRidgeSecondPassTests(unittest.TestCase):
    def test_spine_middle_24_24_becomes_9(self) -> None:
        self.assertEqual(resolve_hill_vertical_ridge_tile_id(24, 24, 24), 9)

    def test_explicit_pairs(self) -> None:
        self.assertEqual(resolve_hill_vertical_ridge_tile_id(2, 4, 99), 9)
        self.assertEqual(resolve_hill_vertical_ridge_tile_id(4, 2, 99), 9)
        self.assertEqual(resolve_hill_vertical_ridge_tile_id(9, 9, 99), 9)
        self.assertEqual(resolve_hill_vertical_ridge_tile_id(3, 5, 99), 7)
        self.assertEqual(resolve_hill_vertical_ridge_tile_id(5, 3, 99), 7)
        self.assertEqual(resolve_hill_vertical_ridge_tile_id(7, 7, 99), 7)
        self.assertEqual(resolve_hill_vertical_ridge_tile_id(3, 9, 99), 7)
        self.assertEqual(resolve_hill_vertical_ridge_tile_id(9, 5, 99), 7)

    def test_fallback(self) -> None:
        self.assertEqual(resolve_hill_vertical_ridge_tile_id(1, 1, 24), 24)


class HillHorizontalRidgeSecondPassTests(unittest.TestCase):
    def test_corners_without_mask10_neighbor(self) -> None:
        d = HILL_MAP[10]
        self.assertEqual(resolve_hill_horizontal_ridge_tile_id(2, 3, False, False, d), 6)
        self.assertEqual(resolve_hill_horizontal_ridge_tile_id(4, 5, False, False, d), 8)

    def test_ambiguous_both_mask10_stays_default(self) -> None:
        d = HILL_MAP[10]
        self.assertEqual(resolve_hill_horizontal_ridge_tile_id(d, d, True, True, d), d)

    def test_propagation_6_along_spine(self) -> None:
        d = HILL_MAP[10]
        self.assertEqual(resolve_hill_horizontal_ridge_tile_id(2, d, False, True, d), 6)
        self.assertEqual(resolve_hill_horizontal_ridge_tile_id(6, d, True, True, d), 6)

    def test_propagation_8_along_spine(self) -> None:
        d = HILL_MAP[10]
        self.assertEqual(resolve_hill_horizontal_ridge_tile_id(d, 5, True, False, d), 8)
        self.assertEqual(resolve_hill_horizontal_ridge_tile_id(d, 8, True, True, d), 8)

    def test_spine_middle_6_6(self) -> None:
        self.assertEqual(resolve_hill_horizontal_ridge_tile_id(6, 6, True, True, HILL_MAP[10]), 6)

    def test_spine_middle_8_8(self) -> None:
        self.assertEqual(resolve_hill_horizontal_ridge_tile_id(8, 8, True, True, HILL_MAP[10]), 8)


class HillPeninsulaVerticalSpineTests(unittest.TestCase):
    def test_junction_both_side_caps_tile_6(self) -> None:
        t = resolve_hill_peninsula_n_junction_tile_id(
            True,
            True,
            6,
            6,
            bulk_e=True,
            bulk_w=True,
        )
        self.assertEqual(t, 16)

    def test_junction_e_cap_only(self) -> None:
        self.assertEqual(
            resolve_hill_peninsula_n_junction_tile_id(
                True,
                False,
                6,
                None,
                bulk_e=True,
                bulk_w=False,
            ),
            15,
        )

    def test_junction_bulk_e_only_no_cap(self) -> None:
        self.assertEqual(
            resolve_hill_peninsula_n_junction_tile_id(
                True,
                False,
                8,
                None,
                bulk_e=True,
                bulk_w=False,
            ),
            15,
        )

    @patch(
        "tilemap_generator.paint_map_png.hill_mask5_vertical_spine_open_diagonals_for_tile24",
        return_value=False,
    )
    def test_extension_along_mask5_from_n_tip(self, _mock_tile24: object) -> None:
        # y=1 mask4 top, y=2–3 mask5 spine, y=4 mask1 bottom tip (column x=2).
        lines = [
            "GGGGGG",
            "GGIGGG",
            "GGIGGG",
            "GGIGGG",
            "GGIGGG",
            "GGGGGG",
        ]
        w, h = 6, 6
        base: list[list[int | None]] = [[None] * w for _ in range(h)]
        for y in range(h):
            for x in range(w):
                if lines[y][x] == "I":
                    base[y][x] = 9
        base[4][2] = HILL_MAP[1]
        base[1][2] = HILL_MAP[4]
        apply_hill_peninsula_vertical_spine_pass(lines, base, w, h, HILL_MAP, hill_char="I")
        self.assertEqual(base[2][2], 24)
        self.assertEqual(base[3][2], 24)

    @patch(
        "tilemap_generator.paint_map_png.hill_mask5_vertical_spine_open_diagonals_for_tile24",
        return_value=False,
    )
    def test_mask7_junction_overwrites_with_tee_e(self, _mock_tile24: object) -> None:
        import tilemap_generator.paint_map_png as pmp

        lines = [
            "GGGGGG",
            "GGIGGG",
            "GGIIGG",
            "GGIGGG",
            "GGGGGG",
        ]
        w, h = 6, 5
        _real_mask = pmp.compute_hill_autotile_mask

        def _mask(lines_in: list[str], x: int, y: int, hill_char: str = "I") -> int:
            if (x, y) == (2, 2):
                return 7
            if (x, y) == (2, 3):
                return 1
            return _real_mask(lines_in, x, y, hill_char=hill_char)

        base: list[list[int | None]] = [[None] * w for _ in range(h)]
        for y in range(h):
            for x in range(w):
                if lines[y][x] == "I":
                    base[y][x] = 9
        base[2][2] = HILL_MAP[7]
        base[2][3] = 8
        base[3][2] = HILL_MAP[1]
        with patch.object(pmp, "compute_hill_autotile_mask", side_effect=_mask):
            pmp.apply_hill_peninsula_vertical_spine_pass(
                lines, base, w, h, HILL_MAP, hill_char="I"
            )
        self.assertEqual(base[2][2], 15)


class HillMask14PeninsulaConnectorTests(unittest.TestCase):
    """Mask 14 + N open + E/W ridge 8 + S in {10,24} → peninsula N connector (21)."""

    def test_combo_returns_21(self) -> None:
        self.assertEqual(
            resolve_hill_mask14_n_peninsula_connector_tile_id(True, 8, 8, 10),
            21,
        )
        self.assertEqual(
            resolve_hill_mask14_n_peninsula_connector_tile_id(True, 8, 8, 24),
            21,
        )

    def test_mismatch_returns_none(self) -> None:
        self.assertIsNone(
            resolve_hill_mask14_n_peninsula_connector_tile_id(True, 8, 8, 9),
        )
        self.assertIsNone(
            resolve_hill_mask14_n_peninsula_connector_tile_id(False, 8, 8, 10),
        )
        self.assertIsNone(
            resolve_hill_mask14_n_peninsula_connector_tile_id(True, 7, 8, 10),
        )

    def test_south_tile_wrong_after_inset_raw_tip_still_21(self) -> None:
        """Inset can overwrite south to vertical 7; raw mask 1 (hill N only) still qualifies."""
        self.assertEqual(
            resolve_hill_mask14_n_peninsula_connector_tile_id(
                True, 8, 8, 7, south_raw_cardinal_mask=1
            ),
            21,
        )

    def test_geo_not_tip_with_bad_ts_still_none(self) -> None:
        self.assertIsNone(
            resolve_hill_mask14_n_peninsula_connector_tile_id(
                True, 8, 8, 7, south_raw_cardinal_mask=6
            ),
        )


class HillPeninsulaPostInsetTileRestoreTests(unittest.TestCase):
    """Snapshot raw tip (1/2/4/8) tiles before inset; restore after inset + spine fix."""

    def test_collect_snapshot_only_includes_tip_masks(self) -> None:
        ascii_lines = [
            "GIGG",
            "GIGG",
            "GGII",
        ]
        w, h = 4, 3
        base: list[list[int | None]] = [[7] * w for _ in range(h)]
        base[1][1] = 99  # raw mask 1 at (1,1)
        snap = collect_hill_raw_peninsula_tip_tile_snapshot(
            ascii_lines, base, w, h, hill_char="I"
        )
        self.assertEqual(snap.get((1, 1)), 99)
        self.assertIn((1, 1), snap)

    def test_restore_overwrites_inset_damage(self) -> None:
        ascii_lines = [
            "GIGG",
            "GIGG",
            "GGII",
        ]
        w, h = 4, 3
        base: list[list[int | None]] = [[7] * w for _ in range(h)]
        base[1][1] = 99
        snap = collect_hill_raw_peninsula_tip_tile_snapshot(
            ascii_lines, base, w, h, hill_char="I"
        )
        out, _, rims = apply_hill_diagonal_inset_neighbor_rules(
            ascii_lines, [row[:] for row in base], w, h, skip_rim_on_raw_peninsula_tips=False
        )
        self.assertNotEqual(out[1][1], 99)
        apply_hill_peninsula_post_inset_tile_restore_pass(out, w, h, snap)
        self.assertEqual(out[1][1], 99)

    def test_corridor_cells_merged_into_snapshot(self) -> None:
        """Spine / protrusion targets (not raw tips) must be restorable after inset."""
        ascii_lines = [
            "GIGG",
            "GIGG",
            "GGII",
        ]
        w, h = 4, 3
        base: list[list[int | None]] = [[7] * w for _ in range(h)]
        base[1][1] = 12  # raw tip (1) at (1,1)
        base[2][2] = 21  # protrusion-style tee — not a raw 1/2/4/8 tip
        corridor = frozenset({(2, 2)})
        snap = collect_hill_raw_peninsula_tip_tile_snapshot(
            ascii_lines, base, w, h, hill_char="I", corridor_cells=corridor
        )
        self.assertEqual(snap.get((1, 1)), 12)
        self.assertEqual(snap.get((2, 2)), 21)
        out, _, _ = apply_hill_diagonal_inset_neighbor_rules(
            ascii_lines, [row[:] for row in base], w, h, skip_rim_on_raw_peninsula_tips=False
        )
        self.assertNotEqual(out[2][2], 21)
        apply_hill_peninsula_post_inset_tile_restore_pass(out, w, h, snap)
        self.assertEqual(out[2][2], 21)

    def test_restore_skips_coords_that_overlap_inset_rims(self) -> None:
        """Rim cells (e.g. SW south cap 4) must not be clobbered by corridor snapshot (e.g. 9)."""
        out: list[list[int | None]] = [[10, 10], [4, 10]]
        snap = {(0, 1): 9}
        apply_hill_peninsula_post_inset_tile_restore_pass(
            out, 2, 2, snap, skip_coords=frozenset({(0, 1)})
        )
        self.assertEqual(out[1][0], 4)
        apply_hill_peninsula_post_inset_tile_restore_pass(out, 2, 2, snap)
        self.assertEqual(out[1][0], 9)


class HillPeninsulaProtrusionAdjacentTests(unittest.TestCase):
    """First spine cell from cardinal tips: 21/24 (S tip + T), 21/24 (N tip), 18/8, 19/8."""

    @patch(
        "tilemap_generator.paint_map_png.hill_mask5_vertical_spine_open_diagonals_for_tile24",
        return_value=False,
    )
    def test_south_tip_interior_ew_grass_is_24(self, _m: object) -> None:
        lines = [
            "GGGGGG",
            "GGIGGG",
            "GGIGGG",
            "GGIGGG",
            "GGIGGG",
            "GGGGGG",
        ]
        w, h = 6, 6
        base: list[list[int | None]] = [[None] * w for _ in range(h)]
        for y in range(h):
            for x in range(w):
                if lines[y][x] == "I":
                    base[y][x] = 9
        base[4][2] = HILL_MAP[1]
        base[1][2] = HILL_MAP[4]
        apply_hill_peninsula_vertical_spine_pass(lines, base, w, h, HILL_MAP, hill_char="I")
        apply_hill_peninsula_protrusion_adjacent_pass(lines, base, w, h, HILL_MAP, hill_char="I")
        self.assertEqual(base[3][2], 24)

    @patch(
        "tilemap_generator.paint_map_png.hill_mask5_vertical_spine_open_diagonals_for_tile24",
        return_value=False,
    )
    def test_south_tip_interior_ew_hill_is_south_tee_21(self, _m: object) -> None:
        # Row y=3: spine x=3 with W and E hills → interior mask 15; south tee connector tile 21.
        lines = [
            "GGGGGGG",
            "GGGIGGG",
            "GGGIGGG",
            "GGIIIGG",
            "GGGIGGG",
            "GGGGGGG",
        ]
        w, h = 7, 6
        cx = 3
        base: list[list[int | None]] = [[None] * w for _ in range(h)]
        for y in range(h):
            for x in range(w):
                if lines[y][x] == "I":
                    base[y][x] = 9
        base[4][cx] = HILL_MAP[1]
        base[1][cx] = HILL_MAP[4]
        apply_hill_peninsula_vertical_spine_pass(lines, base, w, h, HILL_MAP, hill_char="I")
        apply_hill_peninsula_protrusion_adjacent_pass(lines, base, w, h, HILL_MAP, hill_char="I")
        self.assertEqual(base[3][cx], 21)

    def test_horizontal_west_tip_interior_ns_grass_is_ridge_8(self) -> None:
        lines = ["GGGGG", "GIIIG", "GGGGG"]
        w, h = 5, 3
        base: list[list[int | None]] = [[None] * w for _ in range(h)]
        for y in range(h):
            for x in range(w):
                if lines[y][x] == "I":
                    base[y][x] = 8
        apply_hill_peninsula_protrusion_adjacent_pass(lines, base, w, h, HILL_MAP, hill_char="I")
        self.assertEqual(base[1][2], HILL_MAP[10])


class HillMask11TeeNeighborGateTests(unittest.TestCase):
    """hill_map[11] tee only when a cardinal hill neighbor tile is in 10–13 ∪ 23–33 (painter gate)."""

    def _mask11_center_fixture(self) -> tuple[list[str], int, int, int, int]:
        """5×3 map; center (2,1) is I with mask 11 (N,E,W hill; S grass)."""
        lines = [
            "GIIIG",
            "GIIIG",
            "GGGGG",
        ]
        return lines, 5, 3, 2, 1

    def test_no_allowed_neighbor_replaces_tee_with_ridge(self) -> None:
        lines, w, h, cx, cy = self._mask11_center_fixture()
        base: list[list[int | None]] = [[None] * w for _ in range(h)]
        for y in range(h):
            for x in range(w):
                if lines[y][x] == "I":
                    base[y][x] = 1
        base[cy][cx] = HILL_MAP[11]
        base[cy - 1][cx] = 5
        base[cy][cx - 1] = 4
        base[cy][cx + 1] = 8
        self.assertEqual(compute_hill_autotile_mask(lines, cx, cy, hill_char="I"), 11)
        apply_hill_mask11_tee_neighbor_gate(lines, base, w, h, HILL_MAP, hill_char="I")
        self.assertEqual(base[cy][cx], HILL_MAP[10])

    def test_allowed_neighbor_keeps_tee(self) -> None:
        lines, w, h, cx, cy = self._mask11_center_fixture()
        base: list[list[int | None]] = [[None] * w for _ in range(h)]
        for y in range(h):
            for x in range(w):
                if lines[y][x] == "I":
                    base[y][x] = 1
        base[cy][cx] = HILL_MAP[11]
        base[cy - 1][cx] = 12
        base[cy][cx - 1] = 4
        base[cy][cx + 1] = 8
        apply_hill_mask11_tee_neighbor_gate(lines, base, w, h, HILL_MAP, hill_char="I")
        self.assertEqual(base[cy][cx], HILL_MAP[11])

    def test_tile_23_neighbor_keeps_tee(self) -> None:
        lines, w, h, cx, cy = self._mask11_center_fixture()
        base = [[None] * w for _ in range(h)]
        for y in range(h):
            for x in range(w):
                if lines[y][x] == "I":
                    base[y][x] = 1
        base[cy][cx] = HILL_MAP[11]
        base[cy - 1][cx] = 23
        base[cy][cx - 1] = 4
        base[cy][cx + 1] = 8
        apply_hill_mask11_tee_neighbor_gate(lines, base, w, h, HILL_MAP, hill_char="I")
        self.assertEqual(base[cy][cx], HILL_MAP[11])


class HillMask11ExtensionConnectTests(unittest.TestCase):
    """Mask 11 (N+E+W, S open): W=corner 4 + E=extension 8 → center tile 8 (ridge second pass)."""

    def test_w4_e8_returns_connect_tile(self) -> None:
        self.assertEqual(
            resolve_hill_mask11_corner_extension_connect_tile_id(4, 8),
            8,
        )

    def test_mismatch_returns_none(self) -> None:
        self.assertIsNone(resolve_hill_mask11_corner_extension_connect_tile_id(3, 8))
        self.assertIsNone(resolve_hill_mask11_corner_extension_connect_tile_id(4, 7))

    def test_custom_overrides(self) -> None:
        self.assertEqual(
            resolve_hill_mask11_corner_extension_connect_tile_id(
                10, 20, w_corner_tile=10, e_extension_tile=20, connect_tile=99
            ),
            99,
        )


class HillDiagonalInsetNeighborRulesTests(unittest.TestCase):
    def _grid(self, w: int, h: int, fill: int) -> list[list[int | None]]:
        return [[fill] * w for _ in range(h)]

    def test_sw_w_rim_skips_raw_peninsula_tip_west_of_checkerboard_inset(self) -> None:
        """SW inset W rim must not overwrite a mask-1 tip (N-only hill) with continuation art."""
        ascii_lines = [
            "GIGG",
            "GIGG",
            "GGII",
        ]
        snap = self._grid(4, 3, 7)
        snap[1][1] = 99
        out, grass_inset, _ = apply_hill_diagonal_inset_neighbor_rules(
            ascii_lines, snap, 4, 3, skip_rim_on_raw_peninsula_tips=True
        )
        self.assertEqual(grass_inset[1][2], 36)  # SW concave at (2,1)
        self.assertEqual(out[1][1], 99)
        out_legacy, _, _ = apply_hill_diagonal_inset_neighbor_rules(
            ascii_lines, snap, 4, 3, skip_rim_on_raw_peninsula_tips=False
        )
        self.assertNotEqual(out_legacy[1][1], 99)

    def test_sw_geometry_inset_and_south_to_9(self) -> None:
        # Grass (2,0): W+S hill; second pass: S from succeeding S (OOB→hill→9), W from preceding W (I→8)
        ascii_lines = ["IIG", "III"]
        snap = self._grid(3, 2, 1)
        out, grass_inset, _ = apply_hill_diagonal_inset_neighbor_rules(ascii_lines, snap, 3, 2)
        self.assertEqual(grass_inset[0][2], 36)
        self.assertEqual(out[1][2], 9)

    def test_sw_checkerboard_inset_tr_grass(self) -> None:
        """TL/BR hill, TR/BL grass; inset tags TR grass (tile 36 anchor)."""
        ascii_lines = ["IG", "GI"]
        snap = self._grid(2, 2, 1)
        _, grass_inset, _ = apply_hill_diagonal_inset_neighbor_rules(ascii_lines, snap, 2, 2)
        self.assertEqual(grass_inset[0][1], 36)

    def test_se_geometry_inset_and_south_to_9(self) -> None:
        ascii_lines = ["GII", "III"]
        snap = self._grid(3, 2, 1)
        out, grass_inset, _ = apply_hill_diagonal_inset_neighbor_rules(ascii_lines, snap, 3, 2)
        self.assertEqual(grass_inset[0][0], 37)
        self.assertEqual(out[1][0], 7)

    def test_se_checkerboard_inset_bl_grass(self) -> None:
        """TL/BR hill, TR/BL grass; inset tags BL grass (tile 37). Mirrors SW checkerboard."""
        ascii_lines = ["GI", "IG"]
        snap = self._grid(2, 2, 1)
        _, grass_inset, _ = apply_hill_diagonal_inset_neighbor_rules(ascii_lines, snap, 2, 2)
        self.assertEqual(grass_inset[0][0], 37)

    def test_nw_checkerboard_inset_tr_grass(self) -> None:
        """Same 2×2 checkerboard; NW concave at (1,1) with NW diagonal grass → tile 34."""
        ascii_lines = ["GI", "IG"]
        snap = self._grid(2, 2, 1)
        _, grass_inset, _ = apply_hill_diagonal_inset_neighbor_rules(ascii_lines, snap, 2, 2)
        self.assertEqual(grass_inset[1][1], 34)

    def test_ne_geometry_inset_and_south_to_6(self) -> None:
        # NE concave: N+E hill; W and S grass — south override applies only if (1,2) is hill
        ascii_lines = ["III", "GGI", "GGG"]
        snap = self._grid(3, 3, 1)
        out, grass_inset, _ = apply_hill_diagonal_inset_neighbor_rules(ascii_lines, snap, 3, 3)
        self.assertEqual(grass_inset[1][1], 35)
        self.assertEqual(out[2][1], 1)  # south is grass; no hill tile to override

    def test_ne_checkerboard_inset_tr_grass(self) -> None:
        """TL/BR hill, TR/BL grass; inset tags BL (tile 35). Mirrors SW checkerboard."""
        ascii_lines = ["IG.", "GI.", "..."]
        snap = self._grid(3, 3, 1)
        _, grass_inset, _ = apply_hill_diagonal_inset_neighbor_rules(ascii_lines, snap, 3, 3)
        self.assertEqual(grass_inset[1][0], 35)

    def test_nw_geometry_inset_only(self) -> None:
        ascii_lines = ["III", "IGG", "GGG"]
        snap = self._grid(3, 3, 1)
        out, grass_inset, _ = apply_hill_diagonal_inset_neighbor_rules(ascii_lines, snap, 3, 3)
        self.assertEqual(grass_inset[1][1], 34)
        self.assertEqual(out[1][1], 1)

    def test_tile_id_refinement_optional(self) -> None:
        """With use_tile_id_rules, NW requires N=2 and W=2 on ridge snapshot."""
        ascii_lines = ["III", "IGG", "GGG"]
        snap_ok = self._grid(3, 3, 1)
        snap_ok[0][1] = 2
        snap_ok[1][0] = 2
        out_ok, gi_ok, _ = apply_hill_diagonal_inset_neighbor_rules(
            ascii_lines, snap_ok, 3, 3, use_tile_id_rules=True
        )
        self.assertEqual(gi_ok[1][1], 34)
        self.assertEqual(out_ok[0][1], 9)
        self.assertEqual(out_ok[1][0], 6)
        snap_bad = self._grid(3, 3, 1)
        snap_bad[0][1] = 99
        snap_bad[1][0] = 99
        _, gi_bad, _ = apply_hill_diagonal_inset_neighbor_rules(
            ascii_lines, snap_bad, 3, 3, use_tile_id_rules=True
        )
        self.assertIsNone(gi_bad[1][1])

    def test_sw_adjacent_west_outer_corner_to_w_edge(self) -> None:
        ascii_lines = ["IIG", "III"]
        snap = self._grid(3, 2, 1)
        snap[0][1] = 4
        out, _, _ = apply_hill_diagonal_inset_neighbor_rules(ascii_lines, snap, 3, 2)
        # Preceding W from W rim (1,0) is I → SW W hill tile 8
        self.assertEqual(out[0][1], 8)
        self.assertEqual(out[1][2], 9)

    def test_se_adjacent_east_outer_corner_to_e_edge(self) -> None:
        ascii_lines = ["GII", "III"]
        snap = self._grid(3, 2, 1)
        snap[0][1] = 5
        out, _, _ = apply_hill_diagonal_inset_neighbor_rules(ascii_lines, snap, 3, 2)
        self.assertEqual(out[0][1], 8)
        self.assertEqual(out[1][0], 7)

    def test_ne_adjacent_n_e_outer_corners_to_edges(self) -> None:
        # NE concave at (1,1): N and E rim; W/S grass; NE diagonal hill
        ascii_lines = ["III", "GGI", "GGG"]
        snap = self._grid(3, 3, 1)
        snap[0][1] = 3
        snap[1][2] = 3
        out, gi, _ = apply_hill_diagonal_inset_neighbor_rules(ascii_lines, snap, 3, 3)
        self.assertEqual(gi[1][1], 35)
        self.assertEqual(out[0][1], 9)
        self.assertEqual(out[1][2], 6)

    def test_nw_rim_full_symmetric_defaults(self) -> None:
        """NW inset: second pass from preceding N/W (OOB → hill → 9/6)."""
        ascii_lines = ["III", "IGG", "GGG"]
        snap = self._grid(3, 3, 1)
        out, _, _ = apply_hill_diagonal_inset_neighbor_rules(ascii_lines, snap, 3, 3)
        self.assertEqual(out[0][1], 9)
        self.assertEqual(out[1][0], 6)

    def test_sw_s_does_not_overwrite_nw_n_rim_with_tile_4_when_open_north(self) -> None:
        """SW inset above NW inset shares the middle hill; SW S second pass must not paste **4**
        over NW N cap **2** when column north of the rim has no ``I`` (open grass at ``(2,0)``)."""
        ascii_lines = [
            ".IG.",
            ".II.",
            ".IGG",
            "....",
        ]
        w, h = 4, 4
        snap = self._grid(w, h, 1)
        for y in range(h):
            for x in range(w):
                if x < len(ascii_lines[y]) and ascii_lines[y][x] == "I":
                    snap[y][x] = resolve_hill_autotile_tile_id(ascii_lines, x, y, HILL_MAP)
        out, gi, _ = apply_hill_diagonal_inset_neighbor_rules(
            ascii_lines, snap, w, h, corner_tiles={"nw": 34, "ne": 35, "sw": 36, "se": 37}
        )
        self.assertEqual(gi[2][2], 34)  # NW notch (2,2)
        self.assertEqual(gi[0][2], 36)  # SW notch (2,0)
        self.assertNotEqual(out[1][2], 4, "SW S must not stomp NW N rim with south grass-4")
        self.assertEqual(out[1][2], 2)

    def test_nw_overlay_north_of_tr_matches_rim_second_pass_semantics(self) -> None:
        """OOB north of NW TR counts as hill so 2×2 overlay can pick vertical cliff tile 9."""
        import tilemap_generator.paint_map_png as pmp

        self.assertEqual(
            pmp._rim_refine_br_for_diagonal_overlay(["GI", "GG"], 0, -1, 2, 2, hill_char="I"),
            "hill",
        )
        self.assertEqual(
            pmp._rim_refine_br_for_diagonal_overlay(["GI", "GG"], 0, 0, 2, 2, hill_char="I"),
            "grass",
        )
        self.assertEqual(
            pmp._rim_refine_br_for_diagonal_overlay(["II", "GG"], 0, 0, 2, 2, hill_char="I"),
            "hill",
        )

    def test_nw_checkerboard_treats_tree_on_nw_diagonal_as_grass_gap(self) -> None:
        """NW checkerboard: ``T`` on the NW diagonal still forms the concave notch (forest gap)."""
        ascii_lines = ["TII", "IGG", "GGG"]
        snap = self._grid(3, 3, 1)
        _, gi, _ = apply_hill_diagonal_inset_neighbor_rules(ascii_lines, snap, 3, 3)
        self.assertEqual(gi[1][1], 34)

    def test_rim_overrides_explicit(self) -> None:
        ascii_lines = ["III", "IGG", "GGG"]
        snap = self._grid(3, 3, 1)
        out, _, _ = apply_hill_diagonal_inset_neighbor_rules(
            ascii_lines, snap, 3, 3, rim_overrides={"nw": {"n": 77, "w": 88}}
        )
        self.assertEqual(out[0][1], 77)
        self.assertEqual(out[1][0], 88)

    def test_sw_west_rim_cap_when_continuation_is_grass_ascii(self) -> None:
        """Second pass: preceding W from (0,0) is G → SW W uses TL outer corner (default 2)."""
        ascii_lines = [
            "GIG",
            "III",
        ]
        snap = self._grid(3, 2, 1)
        out, gi, _ = apply_hill_diagonal_inset_neighbor_rules(ascii_lines, snap, 3, 2)
        self.assertEqual(gi[0][2], 36)
        self.assertEqual(out[0][1], 2)

    def test_sw_preceding_w_tree_counts_as_grass_for_tile_2(self) -> None:
        """Trees (T) west of W rim are open ground — same W rim cap as G (default 2), not cliff (8)."""
        ascii_lines = [
            "TIG",
            "III",
            "GGG",
        ]
        snap = self._grid(3, 3, 1)
        out, gi, _ = apply_hill_diagonal_inset_neighbor_rules(ascii_lines, snap, 3, 3)
        self.assertEqual(gi[0][2], 36)
        self.assertEqual(out[0][1], 2)

    def test_sw_s_rim_second_pass_after_ne_n_on_shared_rim_cell(self) -> None:
        """(4,1) is both SW S rim (inset SW at 4,0) and NE N rim (inset NE at 4,2); SW S must win."""
        ascii_lines = [
            "IIIIGG",
            "IIIIII",
            "GGGGGI",
            "GGGGGG",
        ]
        snap = self._grid(6, 4, 1)
        out, gi, _ = apply_hill_diagonal_inset_neighbor_rules(ascii_lines, snap, 6, 4)
        self.assertEqual(gi[0][4], 36)
        self.assertEqual(gi[2][4], 35)
        # Succeeding S from (4,1) is grass → SW s grass = 4; must not stay NE n grass = 2
        self.assertEqual(out[1][4], 4)

    def test_nw_n_rim_on_sw_s_shared_cell_keeps_9_when_plateau_north_past_tree(self) -> None:
        """SW at (3,2) and NW at (3,4) share S/N rim (3,3). Column has ``I`` above ``T`` above SW
        grass — :func:`_inset_n_rim_column_has_hill_north` is true; SW S must not overwrite NW N **9**."""
        ascii_lines = [
            "GGIIIGG",
            "GGITTGG",
            "GIIGGGG",
            "GIGIIII",
            "GIIGGGG",
            "GGGGGGG",
        ]
        w, h = 7, 6
        snap = self._grid(w, h, 1)
        out, gi, _ = apply_hill_diagonal_inset_neighbor_rules(ascii_lines, snap, w, h)
        self.assertEqual(gi[2][3], 36)
        self.assertEqual(gi[4][3], 34)
        self.assertEqual(out[3][3], 9)

    def test_sw_w_grass_rim_survives_vertical_spine_tile_fix(self) -> None:
        """W rim (1,1) is mask 5 + diagonal-inset cap tile 2; spine fix must not replace it with 9."""
        ascii_lines = [
            "IIGII",
            "GIGGG",
            "IIIII",
        ]
        w, h = 5, 3
        snap = [[1] * w for _ in range(h)]
        out, _, rims = apply_hill_diagonal_inset_neighbor_rules(ascii_lines, snap, w, h)
        self.assertEqual(out[1][1], 2)
        self.assertIn((1, 1), rims)
        without_skip = [row[:] for row in out]
        apply_hill_vertical_spine_tile_fix(ascii_lines, without_skip, w, h, HILL_MAP, hill_char="I")
        self.assertEqual(without_skip[1][1], 9)
        with_skip = [row[:] for row in out]
        apply_hill_vertical_spine_tile_fix(
            ascii_lines, with_skip, w, h, HILL_MAP, hill_char="I", skip_coords=rims
        )
        self.assertEqual(with_skip[1][1], 2)

    def test_sw_s_rim_turn_east_uses_south_to_6_not_vertical_9(self) -> None:
        """When (gx,gy-2) is open and (gx+2,gy-1) is hill, SW south rim uses corner 6 not 9."""
        ascii_lines = [
            "GGGGGG",
            "GGGGIG",
            "GIGGGG",
            "GIIGGG",
            "GGIGGG",
        ]
        w, h = 6, 5
        snap = self._grid(w, h, 1)
        out, gi, _ = apply_hill_diagonal_inset_neighbor_rules(ascii_lines, snap, w, h)
        self.assertEqual(gi[2][2], 36)
        self.assertEqual(out[3][2], 6)

class HillDiagonalInsetPatternKeySwapTests(unittest.TestCase):
    def test_swap_sw_ne_maps_geometry_to_pattern_key(self) -> None:
        self.assertEqual(
            _diagonal_inset_pattern_key_for_geometry("sw", swap_sw_ne=True, swap_nw_se=False), "ne"
        )
        self.assertEqual(
            _diagonal_inset_pattern_key_for_geometry("ne", swap_sw_ne=True, swap_nw_se=False), "sw"
        )
        self.assertEqual(
            _diagonal_inset_pattern_key_for_geometry("nw", swap_sw_ne=True, swap_nw_se=False), "nw"
        )
        self.assertEqual(
            _diagonal_inset_pattern_key_for_geometry("se", swap_sw_ne=True, swap_nw_se=False), "se"
        )

    def test_swap_nw_se_maps_geometry_to_pattern_key(self) -> None:
        self.assertEqual(
            _diagonal_inset_pattern_key_for_geometry("nw", swap_sw_ne=False, swap_nw_se=True), "se"
        )
        self.assertEqual(
            _diagonal_inset_pattern_key_for_geometry("se", swap_sw_ne=False, swap_nw_se=True), "nw"
        )
        self.assertEqual(
            _diagonal_inset_pattern_key_for_geometry("ne", swap_sw_ne=False, swap_nw_se=True), "ne"
        )

    def test_both_swaps_combined(self) -> None:
        self.assertEqual(
            _diagonal_inset_pattern_key_for_geometry("sw", swap_sw_ne=True, swap_nw_se=True), "ne"
        )
        self.assertEqual(
            _diagonal_inset_pattern_key_for_geometry("nw", swap_sw_ne=True, swap_nw_se=True), "se"
        )

    def test_swap_disabled_is_identity(self) -> None:
        for o in ("nw", "ne", "sw", "se"):
            self.assertEqual(_diagonal_inset_pattern_key_for_geometry(o, swap_sw_ne=False, swap_nw_se=False), o)


class SwInsetTlBrProbeTests(unittest.TestCase):
    def test_tl_two_rows_below_grass(self) -> None:
        # SW origin (1,0): TL (1,0); two rows below (1,2) = G
        ascii_lines = [
            "III",
            "IGG",
            "GGG",
        ]
        self.assertEqual(
            _sw_inset_tl_probe_two_rows_below(ascii_lines, 1, 0, 3, 3, hill_char="I"),
            "grass",
        )

    def test_tl_two_rows_below_hill(self) -> None:
        ascii_lines = [
            "III",
            "IGG",
            "GII",
        ]
        self.assertEqual(
            _sw_inset_tl_probe_two_rows_below(ascii_lines, 1, 0, 3, 3, hill_char="I"),
            "hill",
        )

    def test_br_two_columns_left_grass(self) -> None:
        # SW origin (2,0): BR (3,1); two columns left (1,1) = G
        ascii_lines = [
            "IIII",
            "IGGI",
            "IIII",
        ]
        self.assertEqual(
            _sw_inset_br_probe_two_columns_left(ascii_lines, 2, 0, 4, 2, hill_char="I"),
            "grass",
        )

    def test_br_two_columns_left_hill(self) -> None:
        ascii_lines = [
            "IIII",
            "IIGI",
            "IIII",
        ]
        self.assertEqual(
            _sw_inset_br_probe_two_columns_left(ascii_lines, 2, 0, 4, 2, hill_char="I"),
            "hill",
        )

    def test_turn_east_geometry_forces_br_probe_hill(self) -> None:
        # Two columns left of BR is grass, but (gx+2, gy-1) is hill and (gx, gy-2) open → "hill".
        ascii_lines = [
            "GGGGGG",
            "GGGGIG",
            "GIGGGG",
            "GIIGGG",
            "GGIGGG",
        ]
        w, h = 6, 5
        self.assertTrue(_sw_inset_turn_east_from_grass_notch(ascii_lines, 2, 2, w, h, hill_char="I"))
        # Grass SW at (2,2) → 2×2 origin (1,2); BR (2,3); two columns left of BR is (0,3)=G.
        self.assertEqual(
            _sw_inset_br_probe_two_columns_left(ascii_lines, 1, 2, w, h, hill_char="I"),
            "hill",
        )

    def test_turn_east_false_when_n_plus_2_not_open(self) -> None:
        ascii_lines = [
            "IIIIII",
            "GGGGIG",
            "GIGGGG",
            "GIIGGG",
            "GGIGGG",
        ]
        w, h = 6, 5
        self.assertFalse(_sw_inset_turn_east_from_grass_notch(ascii_lines, 2, 2, w, h, hill_char="I"))

    def test_turn_east_true_when_north_oob(self) -> None:
        """Top-row SW notch: (gx, gy-2) is above map → still treat north as open."""
        ascii_lines = [
            "GGGGI",
            "GIGGG",
            "GIIGG",
        ]
        w, h = 5, 3
        self.assertTrue(_sw_inset_turn_east_from_grass_notch(ascii_lines, 2, 1, w, h, hill_char="I"))

    def test_turn_east_true_when_north_is_shoreline_b(self) -> None:
        ascii_lines = [
            "GGBGGG",
            "GGGGIG",
            "GIGGGG",
            "GIIGGG",
            "GGIGGG",
        ]
        w, h = 6, 5
        self.assertTrue(_sw_inset_turn_east_from_grass_notch(ascii_lines, 2, 2, w, h, hill_char="I"))


class SeInsetTrBlProbeTests(unittest.TestCase):
    def test_tr_one_row_below_grass(self) -> None:
        # SE origin (1,0): TR (2,0); one row below (2,1) = G
        ascii_lines = [
            "III",
            "IGG",
        ]
        self.assertEqual(
            _se_inset_tr_probe_one_row_below(ascii_lines, 1, 0, 3, 2, hill_char="I"),
            "grass",
        )

    def test_tr_one_row_below_hill(self) -> None:
        ascii_lines = [
            "III",
            "IGI",
        ]
        self.assertEqual(
            _se_inset_tr_probe_one_row_below(ascii_lines, 1, 0, 3, 2, hill_char="I"),
            "hill",
        )

    def test_bl_one_column_left_grass(self) -> None:
        # SE origin (2,0): BL (2,1); one column left (1,1) = G
        ascii_lines = [
            "III",
            "IGI",
        ]
        self.assertEqual(
            _se_inset_bl_probe_one_column_left(ascii_lines, 2, 0, 3, 2, hill_char="I"),
            "grass",
        )

    def test_bl_one_column_left_hill(self) -> None:
        ascii_lines = [
            "III",
            "III",
        ]
        self.assertEqual(
            _se_inset_bl_probe_one_column_left(ascii_lines, 2, 0, 3, 2, hill_char="I"),
            "hill",
        )


class NwInsetTrBlProbeTests(unittest.TestCase):
    def test_tr_two_columns_left_hill(self) -> None:
        # NW origin (2,1): TR (3,1); two columns left (1,1) = I
        ascii_lines = [
            "III",
            "III",
        ]
        self.assertEqual(
            _nw_inset_tr_probe_two_columns_left(ascii_lines, 2, 1, 3, 2, hill_char="I"),
            "hill",
        )

    def test_tr_two_columns_left_grass(self) -> None:
        ascii_lines = [
            "III",
            "IGI",
        ]
        self.assertEqual(
            _nw_inset_tr_probe_two_columns_left(ascii_lines, 2, 1, 3, 2, hill_char="I"),
            "grass",
        )

    def test_bl_two_rows_above_hill(self) -> None:
        # NW origin (2,2): BL (2,3); two rows above (2,1) = I
        ascii_lines = [
            "III",
            "III",
            "III",
            "III",
        ]
        self.assertEqual(
            _nw_inset_bl_probe_two_rows_above(ascii_lines, 2, 2, 3, 4, hill_char="I"),
            "hill",
        )

    def test_bl_two_rows_above_grass(self) -> None:
        ascii_lines = [
            "III",
            "IIG",
            "III",
            "III",
        ]
        self.assertEqual(
            _nw_inset_bl_probe_two_rows_above(ascii_lines, 2, 2, 3, 4, hill_char="I"),
            "grass",
        )


class NeInsetTlBrProbeTests(unittest.TestCase):
    def test_br_one_row_above_grass(self) -> None:
        # NE origin (1,0): BR (2,1); one row above (2,0) = TR row — grass
        ascii_lines = [
            "IGG",
            "IGG",
        ]
        self.assertEqual(
            _ne_inset_br_probe_one_row_above(ascii_lines, 1, 0, 3, 2, hill_char="I"),
            "grass",
        )

    def test_br_one_row_above_hill(self) -> None:
        ascii_lines = [
            "III",
            "IGG",
        ]
        self.assertEqual(
            _ne_inset_br_probe_one_row_above(ascii_lines, 1, 0, 3, 2, hill_char="I"),
            "hill",
        )

    def test_tl_one_column_left_hill(self) -> None:
        # NE origin (1,1): TL (1,1); one column left (0,1) = I
        ascii_lines = [
            "III",
            "III",
        ]
        self.assertEqual(
            _ne_inset_tl_probe_one_column_left(ascii_lines, 1, 1, 3, 2, hill_char="I"),
            "hill",
        )

    def test_tl_one_column_left_grass(self) -> None:
        ascii_lines = [
            "III",
            "GII",
        ]
        self.assertEqual(
            _ne_inset_tl_probe_one_column_left(ascii_lines, 1, 1, 3, 2, hill_char="I"),
            "grass",
        )


class HillDiagonalInset2x2PatternParseTests(unittest.TestCase):
    def test_parses_terrain_bitmask_defaults(self) -> None:
        hill = {
            "diagonal_inset_2x2": {
                "nw": {"tl": None, "tr": 2, "bl": 2, "br": 34},
                "ne": {"tl": 3, "tr": None, "bl": 35, "br": 3},
                "sw": {"tl": 4, "tr": 36, "bl": None, "br": 4},
                "se": {"tl": 37, "tr": 5, "bl": 5, "br": None},
            }
        }
        p = parse_hill_diagonal_inset_2x2_patterns(hill)
        assert p is not None
        self.assertIsNone(p["nw"]["tl"])
        self.assertEqual(p["se"]["tr"], 5)

    def test_grass_aliases(self) -> None:
        p = parse_hill_diagonal_inset_2x2_patterns(
            {"diagonal_inset_2x2": {"nw": {"tl": "grass", "tr": 2, "bl": 2, "br": 34}}}
        )
        assert p is not None
        self.assertIsNone(p["nw"]["tl"])


if __name__ == "__main__":
    unittest.main()
