"""
tests/test_transform.py
------------------------
Unit tests for pipeline.transform.sfca_2.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import Point, Polygon

from pipeline.transform.sfca_2 import compute_2sfca, run_transform


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def population_gdf() -> gpd.GeoDataFrame:
    """3×3 grid of census blocks, 200 m cells, EPSG:26985."""
    records = []
    origin_x, origin_y, cell = 390_000.0, 4_300_000.0, 200.0
    for idx in range(9):
        row, col = divmod(idx, 3)
        x0 = origin_x + col * cell
        y0 = origin_y + row * cell
        records.append({
            "GEOID": f"110010001{idx:04d}",
            "population": (idx + 1) * 50,
            "geometry": Polygon([
                (x0, y0), (x0 + cell, y0),
                (x0 + cell, y0 + cell), (x0, y0 + cell),
            ]),
        })
    return gpd.GeoDataFrame(records, crs="EPSG:26985")


@pytest.fixture()
def facility_gdf() -> gpd.GeoDataFrame:
    """2 facilities near the centre of the grid. Uses normalised 'supply' column."""
    records = [
        {"FAC_NAME": "Fac A", "supply": 50, "geometry": Point(390_300.0, 4_300_300.0)},
        {"FAC_NAME": "Fac B", "supply": 30, "geometry": Point(390_500.0, 4_300_500.0)},
    ]
    return gpd.GeoDataFrame(records, crs="EPSG:26985")


d0 = 500.0  # 500 m catchment radius


# ── compute_2sfca ─────────────────────────────────────────────────────────────

class TestCompute2SFCA:

    def test_returns_geodataframe(self, population_gdf, facility_gdf):
        result = compute_2sfca(population_gdf, facility_gdf, d0)
        assert isinstance(result, gpd.GeoDataFrame)

    def test_output_row_count_unchanged(self, population_gdf, facility_gdf):
        result = compute_2sfca(population_gdf, facility_gdf, d0)
        assert len(result) == len(population_gdf)

    def test_accessibility_score_column_exists(self, population_gdf, facility_gdf):
        result = compute_2sfca(population_gdf, facility_gdf, d0)
        assert "accessibility_score" in result.columns
        assert "accessibility_norm" in result.columns

    def test_accessibility_score_nonnegative(self, population_gdf, facility_gdf):
        result = compute_2sfca(population_gdf, facility_gdf, d0)
        assert (result["accessibility_score"] >= 0).all()

    def test_accessibility_norm_in_unit_interval(self, population_gdf, facility_gdf):
        result = compute_2sfca(population_gdf, facility_gdf, d0)
        assert result["accessibility_norm"].between(0, 1).all()

    def test_scores_are_finite(self, population_gdf, facility_gdf):
        result = compute_2sfca(population_gdf, facility_gdf, d0)
        assert np.isfinite(result["accessibility_score"]).all()

    def test_binary_decay_also_works(self, population_gdf, facility_gdf):
        result = compute_2sfca(population_gdf, facility_gdf, d0, decay="binary")
        assert "accessibility_score" in result.columns
        assert (result["accessibility_score"] >= 0).all()

    def test_unknown_decay_raises(self, population_gdf, facility_gdf):
        with pytest.raises(ValueError, match="Unknown decay"):
            compute_2sfca(population_gdf, facility_gdf, d0=500.0, decay="unknown")

    def test_facility_inside_catchment_positive_score(self, population_gdf, facility_gdf):
        """Blocks within catchment of a facility should have score > 0."""
        result = compute_2sfca(population_gdf, facility_gdf, d0=1000.0)
        assert (result["accessibility_score"] > 0).any()

    def test_facility_outside_catchment_zero_score(self, population_gdf):
        """A facility far away should yield zero scores for all blocks."""
        far_fac = gpd.GeoDataFrame(
            [{"supply": 50, "geometry": Point(999_000.0, 9_999_000.0)}],
            crs="EPSG:26985",
        )
        result = compute_2sfca(population_gdf, far_fac, d0=100.0)
        assert (result["accessibility_score"] == 0).all()

    def test_zero_population_block_yields_valid_score(self, population_gdf, facility_gdf):
        gdf = population_gdf.copy()
        gdf.loc[0, "population"] = 0
        result = compute_2sfca(gdf, facility_gdf, d0)
        assert np.isfinite(result["accessibility_score"]).all()


# ── run_transform ─────────────────────────────────────────────────────────────

class TestRunTransform:

    def test_run_transform_uses_config(self, population_gdf, facility_gdf, pipeline_config):
        result = run_transform(population_gdf, facility_gdf, pipeline_config)
        assert "accessibility_score" in result.columns
        assert len(result) == len(population_gdf)

    def test_run_transform_preserves_geometry(self, population_gdf, facility_gdf, pipeline_config):
        result = run_transform(population_gdf, facility_gdf, pipeline_config)
        assert result.geometry.is_valid.all()
        assert str(result.crs) == str(population_gdf.crs)
