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


def test_enhanced_demand_weights_default_matches_equal_weighting():
    """Listing the four columns at 1 must reproduce the published equal weighting exactly."""
    import geopandas as gpd
    import numpy as np
    from shapely.geometry import Point
    import pytest
    pytest.importorskip("pipeline.transform.sfca_enhanced")
    from pipeline.transform.sfca_enhanced import compute_enhanced_2sfca

    blocks = gpd.GeoDataFrame(
        {"population": [100, 50, 0, 80], "PerCapitaI": [10.0, 30.0, 0.0, 20.0],
         "HI_block": [5.0, 1.0, 0.0, 3.0], "age_18to65": [60.0, 20.0, 0.0, 40.0]},
        geometry=[Point(0, 0), Point(300, 0), Point(600, 0), Point(5000, 0)], crs="EPSG:32618",
    )
    facilities = gpd.GeoDataFrame({"supply": [10.0]}, geometry=[Point(100, 0)], crs="EPSG:32618")
    default = compute_enhanced_2sfca(blocks, facilities, d0=900, pop_col="population")
    equal = {"population": 1, "PerCapitaI": 1, "HI_block": 1, "age_18to65": 1}
    explicit = compute_enhanced_2sfca(blocks, facilities, d0=900, pop_col="population", demand_weights=equal)
    no_income = compute_enhanced_2sfca(blocks, facilities, d0=900, pop_col="population",
                                       demand_weights={**equal, "PerCapitaI": 0})
    np.testing.assert_array_equal(default["accessibility_score"], explicit["accessibility_score"])
    assert not np.allclose(default["accessibility_score"], no_income["accessibility_score"])
    assert default["accessibility_score"].iloc[3] == 0  # beyond the catchment


def test_enhanced_transform_uses_configured_demand_columns():
    """A study can name its own demand columns; a missing one stops the run."""
    import geopandas as gpd
    import numpy as np
    import pytest
    from shapely.geometry import Point
    import pytest
    pytest.importorskip("pipeline.transform.sfca_enhanced")
    from pipeline.transform.sfca_enhanced import run_enhanced_transform

    blocks = gpd.GeoDataFrame(
        {"population": [100, 50, 80], "over_65": [40.0, 5.0, 20.0], "PerCapitaI": [1.0, 2.0, 3.0],
         "HI_block": [3.0, 2.0, 1.0], "age_18to65": [10.0, 30.0, 20.0]},
        geometry=[Point(0, 0), Point(300, 0), Point(600, 0)], crs="EPSG:32618",
    )
    facilities = gpd.GeoDataFrame({"supply": [10.0]}, geometry=[Point(100, 0)], crs="EPSG:32618")
    config = {"analysis": {"distance_threshold_m": 900}}
    published = run_enhanced_transform(blocks, facilities, config)
    custom_config = {"analysis": {"distance_threshold_m": 900,
                                  "demand_weights": {"population": 1, "over_65": 1}}}
    custom = run_enhanced_transform(blocks, facilities, custom_config)
    assert not np.allclose(published["accessibility_score"], custom["accessibility_score"])

    custom_config["analysis"]["demand_weights"]["no_vehicle"] = 1
    with pytest.raises(ValueError, match="no_vehicle"):
        run_enhanced_transform(blocks, facilities, custom_config)
