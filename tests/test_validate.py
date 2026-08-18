"""
tests/test_validate.py
-----------------------
Unit tests for pipeline.validate.quality_gates.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point, Polygon

from pipeline.validate.quality_gates import (
    DataQualityError,
    validate_facilities,
    validate_population,
)


# ── validate_population ───────────────────────────────────────────────────────

class TestValidatePopulation:

    def test_clean_input_passes(self, population_gdf, pipeline_config):
        result = validate_population(population_gdf, pipeline_config)
        assert isinstance(result, gpd.GeoDataFrame)
        assert len(result) == len(population_gdf)

    def test_missing_geometry_column_raises(self, population_gdf, pipeline_config):
        bad = population_gdf.drop(columns=["geometry"])
        # becomes a plain DataFrame; force it back to GeoDataFrame without geometry
        bad_gdf = gpd.GeoDataFrame(bad)
        with pytest.raises(DataQualityError, match="Missing required columns"):
            validate_population(bad_gdf, pipeline_config)

    def test_missing_population_column_raises(self, population_gdf, pipeline_config):
        bad = population_gdf.drop(columns=["population"])
        with pytest.raises(DataQualityError, match="Missing required columns"):
            validate_population(bad, pipeline_config)

    def test_population_clamped_at_bounds(self, population_gdf, pipeline_config):
        gdf = population_gdf.copy()
        gdf.loc[0, "population"] = 999_999  # way above max_population=50_000
        result = validate_population(gdf, pipeline_config)
        assert result["population"].max() <= pipeline_config["validation"]["max_population"]

    def test_duplicate_geoids_dropped(self, population_gdf, pipeline_config):
        gdf = pd.concat([population_gdf, population_gdf.iloc[:5]], ignore_index=True)
        gdf = gpd.GeoDataFrame(gdf, crs=population_gdf.crs)
        result = validate_population(gdf, pipeline_config)
        assert result["GEOID"].is_unique

    def test_excess_nulls_raise(self, population_gdf, pipeline_config):
        gdf = population_gdf.copy()
        # set >5% of population to NaN
        n_null = int(len(gdf) * 0.10) + 1
        gdf.loc[:n_null, "population"] = np.nan
        with pytest.raises(DataQualityError, match="nulls"):
            validate_population(gdf, pipeline_config)

    def test_reprojection_on_wrong_crs(self, population_gdf, pipeline_config):
        gdf_4326 = population_gdf.to_crs("EPSG:4326")
        result = validate_population(gdf_4326, pipeline_config)
        expected = pipeline_config["study_area"]["coordinate_system"]
        assert str(result.crs) == expected

    def test_output_row_count_nonnegative(self, population_gdf, pipeline_config):
        result = validate_population(population_gdf, pipeline_config)
        assert len(result) >= 0
        assert (result["population"] >= 0).all()


# ── validate_facilities ───────────────────────────────────────────────────────

class TestValidateFacilities:

    def test_clean_input_passes(self, facility_gdf, pipeline_config):
        result = validate_facilities(facility_gdf, pipeline_config)
        assert isinstance(result, gpd.GeoDataFrame)
        assert len(result) == len(facility_gdf)

    def test_missing_beds_column_raises(self, facility_gdf, pipeline_config):
        bad = facility_gdf.drop(columns=["supply"])
        with pytest.raises(DataQualityError, match="Missing required columns"):
            validate_facilities(bad, pipeline_config)

    def test_zero_bed_facilities_dropped(self, facility_gdf, pipeline_config):
        gdf = facility_gdf.copy()
        gdf.loc[0, "supply"] = 0
        result = validate_facilities(gdf, pipeline_config)
        assert (result["supply"] > 0).all()
        assert len(result) == len(facility_gdf) - 1

    def test_bed_count_clamped(self, facility_gdf, pipeline_config):
        gdf = facility_gdf.copy()
        gdf.loc[0, "supply"] = 99_999  # above max_supply=1000
        result = validate_facilities(gdf, pipeline_config)
        assert result["supply"].max() <= pipeline_config["validation"]["max_supply"]

    def test_reprojection_on_wrong_crs(self, facility_gdf, pipeline_config):
        gdf_4326 = facility_gdf.to_crs("EPSG:4326")
        result = validate_facilities(gdf_4326, pipeline_config)
        expected = pipeline_config["study_area"]["coordinate_system"]
        assert str(result.crs) == expected

    def test_invalid_geometry_auto_fixed(self, facility_gdf, pipeline_config):
        from shapely.geometry import LinearRing

        gdf = facility_gdf.copy()
        # A self-intersecting polygon (bowtie) is invalid
        bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1)])
        gdf.loc[0, "geometry"] = bowtie
        # buffer(0) should fix it; validate_facilities should not raise
        result = validate_facilities(gdf, pipeline_config)
        assert result.geometry.is_valid.all()
