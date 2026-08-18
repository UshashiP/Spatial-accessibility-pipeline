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
