PYTHON ?= python3

ASCII_MAP ?= maps/sample_room.txt
LEGEND ?= maps/sample_room.legend.json
MAP_GEN_OUT ?= maps/generated_map.txt
MAP_GEN_LEGEND ?= maps/generated_map.legend.json
CANVAS_WIDTH ?= 96
CANVAS_HEIGHT ?= 96
TREE_DENSITY ?= 0.20
FOREST_DENSITY ?= 0.60
WATER_DENSITY ?= 0.10
SPAWN_COUNT ?= 8
SPAWN_CLEARING_SIZE ?= 15
JOIN_POINT_COUNT ?= 0
PATH_WIDTH_THRESHOLD ?= 3
PATH_PERLIN_SCALE ?= 14.0
PATH_PERLIN_WEIGHT ?= 1.8
MINE_COUNT ?= 4
SHOP_COUNT ?= 3
CREEP_ZONE_COUNT ?= 6
CREEP_ZONE_RADIUS ?= 2
DEAD_END_COUNT ?= 8
REQUIRE_SECRET_NPC_PATH ?= 1
PREVIEW_IN_ASEPRITE ?= 0
PREVIEW_TILE_SIZE ?= 8
MAP_PREVIEW_OUT ?=
ASEPRITE_BIN ?=
SEED ?= 42
TILE_WIDTH ?= 32
TILE_HEIGHT ?= 32
COLS ?= 4
ROWS ?=
LAYER_NAME ?= Ground

TILESET_ASE ?= assets/tilesets/sample_room_tileset.aseprite
TILESET_BUILD_DIR ?= build/tilesets
TILESET_SOURCE ?=
MAP_OUT_PREFIX ?= build/sample_room

TILESET_NAME := $(basename $(notdir $(TILESET_ASE)))
ASEPRITE_DATA_DEFAULT := $(TILESET_BUILD_DIR)/$(TILESET_NAME).json
ASEPRITE_DATA ?=

MAP_BUILD_ARGS = \
	--ascii $(ASCII_MAP) \
	--legend $(LEGEND) \
	--tile-width $(TILE_WIDTH) \
	--tile-height $(TILE_HEIGHT) \
	--layer-name "$(LAYER_NAME)" \
	--out-prefix $(MAP_OUT_PREFIX)

ifneq ($(strip $(TILESET_SOURCE)),)
MAP_BUILD_ARGS += --tileset-source $(TILESET_SOURCE)
endif

MAP_PAINT_OUT ?= build/map.aseprite
TILE_SIZE ?= 16

.PHONY: help map-gen aseprite-check tileset-init tileset-terrain tileset-edit tileset-export map-paint map-build map-build-validated pipeline

help:
	@echo "Targets:"
	@echo "  make map-gen            # generate an ASCII map + legend JSON"
	@echo "  make aseprite-check     # verify Aseprite CLI is available"
	@echo "  make map-paint          # paint ASCII map as .aseprite (uses MAP_GEN_OUT)"
	@echo "  make tileset-init        # create blank .aseprite tileset canvas"
	@echo "  make tileset-terrain     # generate solid-color terrain tileset from legend"
	@echo "  make tileset-edit        # open .aseprite tileset in Aseprite"
	@echo "  make tileset-export      # export PNG + JSON from .aseprite"
	@echo "  make map-build           # build CSV + Tiled JSON from ASCII + legend"
	@echo "  make map-build-validated # same as map-build, plus --aseprite-data validation"
	@echo "  make pipeline            # check + init + export + map-build-validated"
	@echo ""
	@echo "Common overrides:"
	@echo "  make map-gen CANVAS_WIDTH=128 CANVAS_HEIGHT=128 DEAD_END_COUNT=10 MINE_COUNT=6 SHOP_COUNT=4 PREVIEW_IN_ASEPRITE=1"
	@echo "  make tileset-init TILE_WIDTH=16 TILE_HEIGHT=16 COLS=8"
	@echo "  make tileset-terrain LEGEND=maps/generated_map.legend.json TILESET_ASE=assets/tilesets/generated.aseprite"
	@echo "  make map-build MAP_OUT_PREFIX=build/room01 TILESET_SOURCE=tilesets/overworld.tsx"
	@echo "  make map-paint MAP_GEN_OUT=maps/generated_map.txt MAP_PAINT_OUT=build/map.aseprite TILE_SIZE=16"

map-gen:
	$(PYTHON) scripts/ascii_map_gen.py \
		--width $(CANVAS_WIDTH) \
		--height $(CANVAS_HEIGHT) \
		--tree-density $(TREE_DENSITY) \
		--forest-density $(FOREST_DENSITY) \
		--water-density $(WATER_DENSITY) \
		--spawn-count $(SPAWN_COUNT) \
		--spawn-clearing-size $(SPAWN_CLEARING_SIZE) \
		--join-point-count $(JOIN_POINT_COUNT) \
		--path-width-threshold $(PATH_WIDTH_THRESHOLD) \
		--path-perlin-scale $(PATH_PERLIN_SCALE) \
		--path-perlin-weight $(PATH_PERLIN_WEIGHT) \
		--mine-count $(MINE_COUNT) \
		--shop-count $(SHOP_COUNT) \
		--creep-zone-count $(CREEP_ZONE_COUNT) \
		--creep-zone-radius $(CREEP_ZONE_RADIUS) \
		--dead-end-count $(DEAD_END_COUNT) \
		--preview-tile-size $(PREVIEW_TILE_SIZE) \
		$(if $(strip $(MAP_PREVIEW_OUT)),--preview-out $(MAP_PREVIEW_OUT),) \
		$(if $(strip $(ASEPRITE_BIN)),--aseprite-bin $(ASEPRITE_BIN),) \
		$(if $(filter 1 true yes TRUE YES,$(PREVIEW_IN_ASEPRITE)),--preview-in-aseprite,) \
		$(if $(filter 1 true yes TRUE YES,$(REQUIRE_SECRET_NPC_PATH)),--require-secret-npc-path,) \
		--seed $(SEED) \
		--out $(MAP_GEN_OUT) \
		--legend-out $(MAP_GEN_LEGEND)

aseprite-check:
	$(PYTHON) scripts/aseprite_tileset.py check

map-paint:
	$(PYTHON) scripts/aseprite_tileset.py paint \
		--ascii $(MAP_GEN_OUT) \
		--out $(MAP_PAINT_OUT) \
		--tile-size $(TILE_SIZE)

tileset-init:
	$(PYTHON) scripts/aseprite_tileset.py init \
		--legend $(LEGEND) \
		--out $(TILESET_ASE) \
		--tile-width $(TILE_WIDTH) \
		--tile-height $(TILE_HEIGHT) \
		--cols $(COLS) \
		$(if $(strip $(ROWS)),--rows $(ROWS),)

tileset-terrain:
	$(PYTHON) scripts/aseprite_tileset.py terrain \
		--legend $(LEGEND) \
		--out $(TILESET_ASE) \
		--tile-width $(TILE_WIDTH) \
		--tile-height $(TILE_HEIGHT) \
		--cols $(COLS) \
		$(if $(strip $(ROWS)),--rows $(ROWS),) \
		--export-dir $(TILESET_BUILD_DIR)

tileset-edit:
	$(PYTHON) scripts/aseprite_tileset.py edit --source $(TILESET_ASE)

tileset-export:
	$(PYTHON) scripts/aseprite_tileset.py export \
		--source $(TILESET_ASE) \
		--out-dir $(TILESET_BUILD_DIR)

map-build:
	$(PYTHON) scripts/ascii_to_tilemap.py $(MAP_BUILD_ARGS)

map-build-validated:
	$(PYTHON) scripts/ascii_to_tilemap.py \
		$(MAP_BUILD_ARGS) \
		--aseprite-data $(if $(strip $(ASEPRITE_DATA)),$(ASEPRITE_DATA),$(ASEPRITE_DATA_DEFAULT))

pipeline: aseprite-check tileset-init tileset-export map-build-validated
