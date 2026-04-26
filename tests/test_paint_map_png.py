import unittest
from unittest.mock import patch

from tilemap_generator.paint_map_png import (
    HILL_MAP,
    apply_hill_mask11_tee_neighbor_gate,
    apply_hill_peninsula_protrusion_adjacent_pass,
    apply_hill_peninsula_vertical_spine_pass,
    resolve_hill_peninsula_n_junction_tile_id,
    apply_hill_vertical_spine_tile_fix,
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
    resolve_hill_basic_mask_paint_tile_id,
    resolve_hill_paint_layer_tile_id,
    resolve_hill_autotile_tile_id,
    resolve_hill_split_mask_tile_id,
    resolve_hill_peninsula_connector_tile_id,
    apply_hill_peninsula_connector_pass,
    apply_hill_inset_2x2_pass,
    parse_hill_inset_2x2_rules,
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
        # 2×5 II pill: outer faces are mask 7 / 13 — spine cliffs 9 / 7.
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
        # n×2 II pill (2 rows): top/bottom faces are mask 14 / 11 — ridge 6 / 8.
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


class HillSplitMaskJsonTests(unittest.TestCase):
    def test_split_resolver_uses_shape_map_for_enabled_mask(self) -> None:
        tid = resolve_hill_split_mask_tile_id(
            mask_for_lookup=10,
            raw_mask=10,
            autotile_mask=10,
            maps_by_shape={
                "default": {10: 8},
                "ridge_horizontal": {10: 77},
            },
            enabled_masks=frozenset({10}),
            default_shape="default",
        )
        self.assertEqual(tid, 77)

    def test_split_resolver_falls_back_to_default_shape(self) -> None:
        tid = resolve_hill_split_mask_tile_id(
            mask_for_lookup=11,
            raw_mask=11,
            autotile_mask=11,
            maps_by_shape={"default": {11: 66}},
            enabled_masks=frozenset({11}),
            default_shape="default",
        )
        self.assertEqual(tid, 66)

    def test_basic_resolver_respects_enabled_mask_allowlist(self) -> None:
        lines = ["III"]
        self.assertEqual(
            resolve_hill_basic_mask_paint_tile_id(
                lines,
                1,
                0,
                raw_cardinal_mask=10,
                hill_map=HILL_MAP,
                split_maps_by_shape={"default": {10: 55}},
                split_enabled_masks=frozenset({10}),
            ),
            55,
        )
        self.assertEqual(
            resolve_hill_basic_mask_paint_tile_id(
                lines,
                1,
                0,
                raw_cardinal_mask=10,
                hill_map=HILL_MAP,
                split_maps_by_shape={"default": {10: 55}},
                split_enabled_masks=frozenset({11}),
            ),
            HILL_MAP[10],
        )

    def test_basic_resolver_three_side_masks_use_cliff_faces(self) -> None:
        lines = ["I"]
        self.assertEqual(
            resolve_hill_basic_mask_paint_tile_id(
                lines, 0, 0, raw_cardinal_mask=7, hill_map=HILL_MAP
            ),
            9,
        )
        self.assertEqual(
            resolve_hill_basic_mask_paint_tile_id(
                lines, 0, 0, raw_cardinal_mask=13, hill_map=HILL_MAP
            ),
            7,
        )
        self.assertEqual(
            resolve_hill_basic_mask_paint_tile_id(
                lines, 0, 0, raw_cardinal_mask=14, hill_map=HILL_MAP
            ),
            6,
        )
        self.assertEqual(
            resolve_hill_basic_mask_paint_tile_id(
                lines, 0, 0, raw_cardinal_mask=11, hill_map=HILL_MAP
            ),
            8,
        )

    def test_autotile_resolver_uses_split_for_enabled_mask(self) -> None:
        lines = ["GIIIIIG", "GIIIIIG", "GIIIIIG"]
        self.assertEqual(
            resolve_hill_autotile_tile_id(
                lines,
                3,
                0,
                HILL_MAP,
                split_maps_by_shape={"ridge_horizontal": {10: 88}, "default": {10: 8}},
                split_enabled_masks=frozenset({10}),
            ),
            88,
        )
        self.assertEqual(
            resolve_hill_autotile_tile_id(
                lines,
                3,
                0,
                HILL_MAP,
                split_maps_by_shape={"ridge_horizontal": {10: 88}, "default": {10: 8}},
                split_enabled_masks=frozenset({11}),
            ),
            HILL_MAP[10],
        )


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


class HillPeninsulaConnectorPassTests(unittest.TestCase):
    def _base(self, lines: list[str], fill: int = 9) -> list[list[int | None]]:
        width = max((len(row) for row in lines), default=0)
        out: list[list[int | None]] = [[None] * width for _ in lines]
        for y, row in enumerate(lines):
            for x, ch in enumerate(row):
                if ch == "I":
                    out[y][x] = fill
        return out

    def test_north_anchor_rewrites_inward_adjacent_but_keeps_endpoint(self) -> None:
        lines = ["GGG", "GIG", "GII"]
        base = self._base(lines)
        base[1][1] = 10
        apply_hill_peninsula_connector_pass(lines, base, 3, 3)
        self.assertEqual(base[1][1], 10)
        self.assertEqual(base[2][1], 39)

    def test_south_anchor_rewrites_inward_adjacent_but_keeps_endpoint(self) -> None:
        lines = ["IIG", "GIG", "GGG"]
        base = self._base(lines)
        base[1][1] = 12
        apply_hill_peninsula_connector_pass(lines, base, 3, 3)
        self.assertEqual(base[1][1], 12)
        self.assertEqual(base[0][1], 45)

    def test_east_anchor_rewrites_inward_adjacent_but_keeps_endpoint(self) -> None:
        lines = ["GGG", "IIG", "IGG"]
        base = self._base(lines)
        base[1][1] = 11
        apply_hill_peninsula_connector_pass(lines, base, 3, 3)
        self.assertEqual(base[1][1], 11)
        self.assertEqual(base[1][0], 40)

    def test_east_anchor_with_both_side_hills_rewrites_inward_adjacent_to_18(self) -> None:
        lines = ["IGG", "IIG", "IGG"]
        base = self._base(lines)
        base[1][1] = 11
        apply_hill_peninsula_connector_pass(lines, base, 3, 3)
        self.assertEqual(base[1][1], 11)
        self.assertEqual(base[1][0], 18)

    def test_raw_w_endpoint_keeps_original_cap_and_rewrites_adjacent_to_18(self) -> None:
        lines = ["IGG", "IIG", "IGG"]
        base = self._base(lines)
        base[1][1] = resolve_hill_basic_mask_paint_tile_id(
            lines, 1, 1, raw_cardinal_mask=8, hill_map=HILL_MAP
        )
        self.assertEqual(base[1][1], 13)
        apply_hill_peninsula_connector_pass(lines, base, 3, 3)
        self.assertEqual(base[1][1], 13)
        self.assertEqual(base[1][0], 18)

    def test_connector_classifier_does_not_rewrite_cardinal_endpoint(self) -> None:
        lines = ["GIG", "IIH", "GGG"]
        base = self._base(lines)
        base[1][1] = 11
        base[0][1] = 24
        base[1][0] = 24
        apply_hill_peninsula_connector_pass(lines, base, 3, 3)
        self.assertEqual(base[1][1], 11)

    def test_west_anchor_rewrites_inward_adjacent_but_keeps_endpoint(self) -> None:
        lines = ["GGG", "GII", "GGI"]
        base = self._base(lines)
        base[1][1] = 13
        apply_hill_peninsula_connector_pass(lines, base, 3, 3)
        self.assertEqual(base[1][1], 13)
        self.assertEqual(base[1][2], 38)

    def test_anchor_extension_outputs(self) -> None:
        lines_v = ["GGG", "GIG", "GIG"]
        base_v = self._base(lines_v)
        base_v[1][1] = 10
        apply_hill_peninsula_connector_pass(lines_v, base_v, 3, 3)
        self.assertEqual(base_v[2][1], 24)

        lines_h = ["GGG", "IIG", "GGG"]
        base_h = self._base(lines_h)
        base_h[1][1] = 11
        apply_hill_peninsula_connector_pass(lines_h, base_h, 3, 3)
        self.assertEqual(base_h[1][0], 23)

    def test_vertical_extension_walks_until_side_hills(self) -> None:
        lines = [
            "GGG",
            "GIG",
            "GIG",
            "III",
        ]
        base = self._base(lines)
        base[1][1] = 10
        apply_hill_peninsula_connector_pass(lines, base, 3, 4)
        self.assertEqual(base[1][1], 10)
        self.assertEqual(base[2][1], 24)
        self.assertEqual(base[3][1], 16)

    def test_horizontal_extension_walks_until_side_hills(self) -> None:
        lines = [
            "GIGG",
            "IIII",
            "GIGG",
        ]
        base = self._base(lines)
        base[1][3] = resolve_hill_basic_mask_paint_tile_id(
            lines, 3, 1, raw_cardinal_mask=8, hill_map=HILL_MAP
        )
        apply_hill_peninsula_connector_pass(lines, base, 4, 3)
        self.assertEqual(base[1][3], 13)
        self.assertEqual(base[1][2], 23)
        self.assertEqual(base[1][1], 18)

    def test_touched_extender_promotes_to_90_degree_connector(self) -> None:
        lines = [
            "GGG",
            "GIG",
            "GII",
        ]
        base = self._base(lines)
        base[1][1] = 10
        base[2][2] = 24
        apply_hill_peninsula_connector_pass(lines, base, 3, 3)
        self.assertEqual(base[2][1], 31)

    def test_touched_extender_promotes_to_tee_connector(self) -> None:
        lines = [
            "GGG",
            "GIG",
            "III",
        ]
        base = self._base(lines)
        base[1][1] = 10
        base[2][0] = 24
        base[2][2] = 24
        apply_hill_peninsula_connector_pass(lines, base, 3, 3)
        self.assertEqual(base[2][1], 32)

    def test_touched_extender_promotes_to_4way_connector(self) -> None:
        lines = [
            "GIG",
            "GIG",
            "III",
            "GIG",
        ]
        base = self._base(lines)
        base[0][1] = 24
        base[1][1] = 10
        base[2][0] = 24
        base[2][2] = 24
        base[3][1] = 24
        apply_hill_peninsula_connector_pass(lines, base, 3, 4)
        self.assertEqual(base[2][1], 29)

    def test_connector_classifier_outputs_elbows_tees_and_4way(self) -> None:
        expected = {
            6: 25,
            12: 27,
            3: 31,
            9: 33,
            11: 32,
            14: 26,
            7: 28,
            13: 30,
            15: 29,
        }
        for mask, tile_id in expected.items():
            with self.subTest(mask=mask):
                self.assertEqual(resolve_hill_peninsula_connector_tile_id(mask), tile_id)

    def test_paint_layer_uses_resolved_grid_tile(self) -> None:
        lines = ["GGG", "GIG", "GIG"]
        base = self._base(lines)
        base[1][1] = 10
        apply_hill_peninsula_connector_pass(lines, base, 3, 3)
        raw = get_hill_adjacency_bitmask(lines, 1, 2, hill_char="I")
        autotile = compute_hill_autotile_mask(lines, 1, 2, hill_char="I")
        self.assertEqual(
            resolve_hill_paint_layer_tile_id(
                lines,
                1,
                2,
                raw_cardinal_mask=raw,
                autotile_mask=autotile,
                base_hill_tile_ids=base,
                hill_map=HILL_MAP,
                post_first_pass=False,
                width=3,
                height=3,
            ),
            24,
        )


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



class HillInset2x2PassTests(unittest.TestCase):
    def _grid(self, rows: list[list[int | None]]) -> list[list[int | None]]:
        return [row[:] for row in rows]

    def test_nw_inset_sets_br_34(self) -> None:
        lines = ["GI", "II"]
        base = self._grid([[None, 39], [38, 9]])
        touched = apply_hill_inset_2x2_pass(lines, base, 2, 2)
        self.assertEqual(base[1][1], 34)
        self.assertIn((1, 1), touched)

    def test_nw_inset_can_write_inner_plateau_cell(self) -> None:
        lines = ["GI", "II"]
        base = self._grid([[None, 39], [38, None]])
        touched = apply_hill_inset_2x2_pass(lines, base, 2, 2)
        self.assertEqual(base[1][1], 34)
        self.assertIn((1, 1), touched)

    def test_ne_inset_sets_bl_35(self) -> None:
        lines = ["IG", "II"]
        base = self._grid([[41, None], [9, 40]])
        touched = apply_hill_inset_2x2_pass(lines, base, 2, 2)
        self.assertEqual(base[1][0], 35)
        self.assertIn((0, 1), touched)

    def test_se_inset_sets_tl_37(self) -> None:
        lines = ["II", "IG"]
        base = self._grid([[9, 44], [45, None]])
        touched = apply_hill_inset_2x2_pass(lines, base, 2, 2)
        self.assertEqual(base[0][0], 37)
        self.assertIn((0, 0), touched)

    def test_sw_inset_sets_tr_36(self) -> None:
        lines = ["II", "GI"]
        base = self._grid([[42, 9], [None, 43]])
        touched = apply_hill_inset_2x2_pass(lines, base, 2, 2)
        self.assertEqual(base[0][1], 36)
        self.assertIn((1, 0), touched)

    def test_no_inset_when_edge_tile_not_allowed(self) -> None:
        lines = ["GI", "II"]
        base = self._grid([[None, 99], [38, 9]])
        touched = apply_hill_inset_2x2_pass(lines, base, 2, 2)
        self.assertEqual(base[1][1], 9)
        self.assertNotIn((1, 1), touched)

    def test_parse_inset_2x2_rule_override(self) -> None:
        rules = parse_hill_inset_2x2_rules(
            {"inset_2x2_rules": {"nw": {"edge_a": [1], "edge_b": [2], "out_tile": 99}}}
        )
        self.assertEqual(rules.nw.edge_a, frozenset({1}))
        self.assertEqual(rules.nw.edge_b, frozenset({2}))
        self.assertEqual(rules.nw.out_tile, 99)

    def test_paint_layer_uses_inset_grid_tile(self) -> None:
        lines = ["GI", "II"]
        base = self._grid([[None, 39], [38, 9]])
        apply_hill_inset_2x2_pass(lines, base, 2, 2)
        raw = get_hill_adjacency_bitmask(lines, 1, 1, hill_char="I")
        autotile = compute_hill_autotile_mask(lines, 1, 1, hill_char="I")
        self.assertEqual(
            resolve_hill_paint_layer_tile_id(
                lines,
                1,
                1,
                raw_cardinal_mask=raw,
                autotile_mask=autotile,
                base_hill_tile_ids=base,
                hill_map=HILL_MAP,
                post_first_pass=False,
                width=2,
                height=2,
            ),
            34,
        )

    def test_paint_layer_uses_inset_grid_tile_on_deep_interior(self) -> None:
        lines = ["GII", "III", "III"]
        base = self._grid(
            [
                [None, 39, 9],
                [38, None, 7],
                [9, 6, 7],
            ]
        )
        apply_hill_inset_2x2_pass(lines, base, 3, 3)
        raw = get_hill_adjacency_bitmask(lines, 1, 1, hill_char="I")
        autotile = compute_hill_autotile_mask(lines, 1, 1, hill_char="I")
        self.assertEqual(raw, 15)
        self.assertEqual(
            resolve_hill_paint_layer_tile_id(
                lines,
                1,
                1,
                raw_cardinal_mask=raw,
                autotile_mask=autotile,
                base_hill_tile_ids=base,
                hill_map=HILL_MAP,
                post_first_pass=False,
                width=3,
                height=3,
            ),
            34,
        )
