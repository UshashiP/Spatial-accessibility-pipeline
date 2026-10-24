import logging

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point

from pipeline.transform.sfca_enhanced import _resolve_population_column
from pipeline.validate.quality_gates import _warn_if_population_repeats_within_block_groups


def _blocks(populations):
    # 15-digit GEOIDs: 12-digit block group + 3-digit block.
    geoids = [f"11001{bg:07d}{block:03d}" for bg, block in
              ((i // 4, i % 4) for i in range(len(populations)))]
    return gpd.GeoDataFrame(
        {"GEOID": geoids, "population": populations},
        geometry=[Point(0, 0)] * len(populations),
    )


def test_configured_population_column_beats_other_candidates():
    gdf = gpd.GeoDataFrame(
        {"population": [1], "Bl_totalpo": [2], "Total Popu": [3]},
        geometry=[Point(0, 0)],
    )
    assert _resolve_population_column(gdf) == "population"


def test_population_column_falls_back_to_known_aliases():
    gdf = gpd.GeoDataFrame({"Total Popu": [3]}, geometry=[Point(0, 0)])
    assert _resolve_population_column(gdf) == "Total Popu"
    assert _resolve_population_column(gpd.GeoDataFrame({"x": [1]}, geometry=[Point(0, 0)])) is None


def test_block_group_value_copied_to_blocks_is_flagged(caplog):
    # 40 block groups x 4 blocks, every block carrying its group's total.
    gdf = _blocks(np.repeat(np.arange(100, 140), 4))
    with caplog.at_level(logging.WARNING):
        _warn_if_population_repeats_within_block_groups(gdf, "population")
    assert "level value copied to blocks" in caplog.text


def test_real_block_counts_are_not_flagged(caplog):
    rng = np.random.default_rng(0)
    gdf = _blocks(rng.integers(0, 500, size=160))
    with caplog.at_level(logging.WARNING):
        _warn_if_population_repeats_within_block_groups(gdf, "population")
    assert caplog.text == ""


def test_check_skips_non_block_geoids(caplog):
    gdf = _blocks(np.repeat(np.arange(100, 140), 4))
    gdf["GEOID"] = [f"B{i}" for i in range(len(gdf))]
    with caplog.at_level(logging.WARNING):
        _warn_if_population_repeats_within_block_groups(gdf, "population")
    assert caplog.text == ""
