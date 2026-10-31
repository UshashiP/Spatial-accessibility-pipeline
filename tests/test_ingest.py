"""
tests/test_ingest.py
---------------------
Unit tests for the ingest stage (Census API + CMS API).

All external HTTP calls are mocked so tests run fully offline.
"""

from __future__ import annotations

import json
import textwrap
from unittest.mock import MagicMock, patch

import geopandas as gpd
import pytest
from shapely.geometry import Point


# ── Census ingest ─────────────────────────────────────────────────────────────

class TestCensusIngest:
    """Tests for pipeline.ingest.census_api.ingest_census_blocks"""

    def _mock_pop_response(self) -> MagicMock:
        data = [
            ["NAME", "P1_001N", "state", "county", "tract", "block"],
            ["Block 1, DC", "150", "11", "001", "000100", "1000"],
            ["Block 2, DC", "0",   "11", "001", "000100", "1001"],
            ["Block 3, DC", "320", "11", "001", "000100", "1002"],
        ]
        resp = MagicMock()
        resp.json.return_value = data
        resp.raise_for_status = MagicMock()
        return resp

    def _mock_tiger_geojson(self) -> MagicMock:
        features = []
        for i, geoid in enumerate(["110010001001000", "110010001001001", "110010001001002"]):
            features.append({
                "type": "Feature",
                "properties": {"GEOID20": geoid},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [-77.0 - i * 0.01, 38.9],
                        [-77.0 - i * 0.01 + 0.001, 38.9],
                        [-77.0 - i * 0.01 + 0.001, 38.901],
                        [-77.0 - i * 0.01, 38.901],
                        [-77.0 - i * 0.01, 38.9],
                    ]],
                },
            })
        geojson = json.dumps({"type": "FeatureCollection", "features": features})
        resp = MagicMock()
        resp.text = geojson
        resp.raise_for_status = MagicMock()
        return resp

    @patch("pipeline.ingest.census_api.get_with_retry")
    def test_returns_geodataframe(self, mock_get, pipeline_config):
        mock_get.side_effect = [self._mock_pop_response(), self._mock_tiger_geojson()]
        from pipeline.ingest.census_api import ingest_census_blocks
        gdf = ingest_census_blocks(pipeline_config)
        assert isinstance(gdf, gpd.GeoDataFrame)
        assert len(gdf) > 0

    @patch("pipeline.ingest.census_api.get_with_retry")
    def test_population_column_numeric(self, mock_get, pipeline_config):
        mock_get.side_effect = [self._mock_pop_response(), self._mock_tiger_geojson()]
        from pipeline.ingest.census_api import ingest_census_blocks
        gdf = ingest_census_blocks(pipeline_config)
        assert (gdf["population"] >= 0).all()
        assert gdf["population"].dtype in (int, "int64", "int32")

    @patch("pipeline.ingest.census_api.get_with_retry")
    def test_geoid_unique(self, mock_get, pipeline_config):
        mock_get.side_effect = [self._mock_pop_response(), self._mock_tiger_geojson()]
        from pipeline.ingest.census_api import ingest_census_blocks
        gdf = ingest_census_blocks(pipeline_config)
        assert gdf["GEOID"].is_unique


# ── CMS ingest ────────────────────────────────────────────────────────────────

class TestCMSIngest:
    """Tests for pipeline.ingest.cms_api.ingest_facilities"""

    def _mock_cms_response(self) -> MagicMock:
        results = [
            {
                "FAC_NAME": "ICF Alpha",
                "STATE_CD": "DC",
                "CRTFD_BED_CNT": "30",
                "STR_ADDR_LN_1": "100 Main St",
                "CITY_NAME": "Washington",
                "ZIP_CD": "20001",
            },
            {
                "FAC_NAME": "ICF Beta",
                "STATE_CD": "DC",
                "CRTFD_BED_CNT": "45",
                "STR_ADDR_LN_1": "200 Oak Ave",
                "CITY_NAME": "Washington",
                "ZIP_CD": "20002",
            },
        ]
        resp = MagicMock()
        resp.json.return_value = {"results": results, "count": 2}
        resp.raise_for_status = MagicMock()
        return resp

    def _mock_geocoder_response(self) -> MagicMock:
        csv_text = textwrap.dedent("""\
            0,100 Main St Washington DC 20001,Match,Exact,100 Main St,"-77.0366,38.9072",123456,L
            1,200 Oak Ave Washington DC 20002,Match,Exact,200 Oak Ave,"-77.0300,38.9100",123457,L
        """)
        resp = MagicMock()
        resp.text = csv_text
        resp.raise_for_status = MagicMock()
        return resp

    @patch("pipeline.ingest.cms_api.requests.post")
    @patch("pipeline.ingest.cms_api.get_with_retry")
    def test_returns_geodataframe(self, mock_get, mock_post, pipeline_config):
        mock_get.return_value = self._mock_cms_response()
        mock_post.return_value = self._mock_geocoder_response()
        from pipeline.ingest.cms_api import ingest_facilities
        gdf = ingest_facilities(pipeline_config)
        assert isinstance(gdf, gpd.GeoDataFrame)
        assert len(gdf) == 2

    @patch("pipeline.ingest.cms_api.requests.post")
    @patch("pipeline.ingest.cms_api.get_with_retry")
    def test_bed_count_positive(self, mock_get, mock_post, pipeline_config):
        mock_get.return_value = self._mock_cms_response()
        mock_post.return_value = self._mock_geocoder_response()
        from pipeline.ingest.cms_api import ingest_facilities
        gdf = ingest_facilities(pipeline_config)
        assert (gdf["supply"] > 0).all()

    @patch("pipeline.ingest.cms_api.requests.post")
    @patch("pipeline.ingest.cms_api.get_with_retry")
    def test_crs_projected(self, mock_get, mock_post, pipeline_config):
        mock_get.return_value = self._mock_cms_response()
        mock_post.return_value = self._mock_geocoder_response()
        from pipeline.ingest.cms_api import ingest_facilities
        gdf = ingest_facilities(pipeline_config)
        assert gdf.crs is not None
        assert gdf.crs.is_projected


# ── Population settings ───────────────────────────────────────────────────────

class TestPopulationSettings:
    """Tests for pipeline.ingest.census_api._apply_population_settings"""

    @pytest.fixture
    def blocks(self):
        return gpd.GeoDataFrame(
            {"GEOID": ["1", "2", "3", "4"], "population": [0, 10, 30, 0]},
            geometry=[Point(0, 0)] * 4, crs="EPSG:26985",
        )

    def test_exclude_keeps_empty_blocks_at_zero(self, blocks):
        from pipeline.ingest.census_api import _apply_population_settings
        result = _apply_population_settings(blocks, {"data": {}})
        assert result["population"].tolist() == [0, 10, 30, 0]

    def test_median_fills_empty_blocks(self, blocks):
        from pipeline.ingest.census_api import _apply_population_settings
        result = _apply_population_settings(blocks, {"data": {"empty_blocks": "median"}})
        assert result["population"].tolist() == [5, 10, 30, 5]

    def test_reference_replaces_population(self, blocks, tmp_path):
        from pipeline.ingest.census_api import _apply_population_settings
        path = tmp_path / "ref.csv"
        path.write_text("GEOID,population_2020\n1,7\n2,0\n3,30\n4,0\n")
        result = _apply_population_settings(blocks, {"data": {"population_reference": str(path)}})
        assert result["population"].tolist() == [7, 0, 30, 0]

    def test_reference_must_cover_every_block(self, blocks, tmp_path):
        from pipeline.ingest.census_api import _apply_population_settings
        path = tmp_path / "ref.csv"
        path.write_text("GEOID,population_2020\n1,7\n")
        with pytest.raises(ValueError, match="3 missing"):
            _apply_population_settings(blocks, {"data": {"population_reference": str(path)}})

    def test_unknown_mode_rejected(self, blocks):
        from pipeline.ingest.census_api import _apply_population_settings
        with pytest.raises(ValueError, match="empty_blocks"):
            _apply_population_settings(blocks, {"data": {"empty_blocks": "drop"}})


class TestReportArea:
    """Tests for pipeline.ingest.census_api.report_area_mask"""

    def test_no_report_area_keeps_everything(self):
        from pipeline.ingest.census_api import report_area_mask
        points = gpd.GeoSeries([Point(0, 0), Point(10, 10)], crs="EPSG:32611")
        assert report_area_mask(points, {"study_area": {}}).tolist() == [True, True]

    def test_flags_geometries_inside_the_boundary(self, tmp_path):
        from shapely.geometry import box
        from pipeline.ingest.census_api import report_area_mask
        boundary = tmp_path / "places.geojson"
        gpd.GeoDataFrame({"GEOID": ["0644000", "0600001"]},
                         geometry=[box(0, 0, 100, 100), box(200, 0, 300, 100)],
                         crs="EPSG:32611").to_file(boundary)
        points = gpd.GeoSeries([Point(50, 50), Point(250, 50), Point(500, 500)], crs="EPSG:32611")
        config = {"study_area": {"report_area": {"boundary": str(boundary), "id": "0644000"}}}
        assert report_area_mask(points, config).tolist() == [True, False, False]

    def test_unknown_id_is_an_error(self, tmp_path):
        from shapely.geometry import box
        from pipeline.ingest.census_api import report_area_mask
        boundary = tmp_path / "places.geojson"
        gpd.GeoDataFrame({"GEOID": ["0644000"]}, geometry=[box(0, 0, 1, 1)], crs="EPSG:32611").to_file(boundary)
        config = {"study_area": {"report_area": {"boundary": str(boundary), "id": "9999999"}}}
        with pytest.raises(ValueError, match="found 0"):
            report_area_mask(gpd.GeoSeries([Point(0, 0)], crs="EPSG:32611"), config)
