"""
tests/conftest.py
------------------
Shared pytest fixtures for the Spatial Accessibility Pipeline.
"""

from __future__ import annotations

import numpy as np
import pytest
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon


# ── Synthetic population GeoDataFrame ─────────────────────────────────────────

@pytest.fixture()
def population_gdf() -> gpd.GeoDataFrame:
    """
    10×10 grid of census blocks in EPSG:26985 (metres).
    Origin at (390_000, 4_300_000), 100 m × 100 m cells.
    """
    rng = np.random.default_rng(42)
    size = 100
    origin_x, origin_y = 390_000.0, 4_300_000.0
    cell = 100.0

    records = []
    for idx in range(size):
        row, col = divmod(idx, 10)
        x0 = origin_x + col * cell
        y0 = origin_y + row * cell
        geoid = f"1100100{idx:04d}"
        pop = int(rng.integers(10, 500))
        geom = Polygon([
            (x0, y0), (x0 + cell, y0),
            (x0 + cell, y0 + cell), (x0, y0 + cell),
        ])
        records.append({
            "GEOID": geoid, "population": pop, "geometry": geom,
            "state": "11", "county": "001",
            "tract": "000100", "block": f"{idx:04d}",
        })

    return gpd.GeoDataFrame(records, crs="EPSG:26985")


# ── Synthetic facility GeoDataFrame ──────────────────────────────────────────

@pytest.fixture()
def facility_gdf() -> gpd.GeoDataFrame:
    """
    5 facilities in the centre of the synthetic study area.
    Uses normalised 'supply' column (as produced by ingest stage).
    """
    rng = np.random.default_rng(0)
    origins = [
        (390_450.0, 4_300_450.0),
        (390_550.0, 4_300_550.0),
        (390_300.0, 4_300_700.0),
        (390_700.0, 4_300_300.0),
        (390_500.0, 4_300_250.0),
    ]
    records = [
        {
            "FAC_NAME": f"Facility {i + 1}",
            "supply": int(rng.integers(10, 100)),   # normalised column name
            "geometry": Point(x, y),
        }
        for i, (x, y) in enumerate(origins)
    ]
    return gpd.GeoDataFrame(records, crs="EPSG:26985")


# ── Pipeline config fixture ───────────────────────────────────────────────────

@pytest.fixture()
def pipeline_config() -> dict:
    """Minimal config dict for unit tests (no S3, no API keys)."""
    return {
        "study_area": {
            "name": "Washington DC",
            "state_fips": "11",
            "state_abbrev": "DC",
            "coordinate_system": "EPSG:26985",
            "distance_unit": "meters",
        },
        "facility": {
            "type": "ICF",
            "label": "Intermediate Care Facilities",
            "cms_dataset_id": "78j2-v3zx",
            "cms_category_code": "13",
            "supply_column": "CRTFD_BED_CNT",
            "supply_label": "Certified beds",
        },
        "census": {
            "base_url": "https://api.census.gov/data",
            "year": 2020,
            "dataset": "dec/pl",
            "variables": {"total_population": "P1_001N"},
            "geography": "block",
        },
        "cms": {
            "base_url": "https://data.cms.gov/provider-data/api/1/datastore/query",
        },
        "analysis": {
            "distance_threshold_m": 500.0,
            "decay_function": "gaussian",
            "population_column": "population",
        },
        "validation": {
            "min_population": 0,
            "max_population": 50_000,
            "min_supply": 1,
            "max_supply": 1_000,
            "required_facility_columns": ["geometry", "supply"],
            "required_population_columns": ["geometry", "population"],
            "max_null_pct": 0.05,
        },
        "s3": {
            "prefix": "spatial-accessibility",
            "bronze": "bronze",
            "silver": "silver",
            "gold": "gold",
            "region": "us-east-1",
            "geoparquet_compression": "snappy",
        },
        "duckdb": {
            "db_path": "/tmp/test_accessibility.duckdb",
            "gold_table": "accessibility_scores",
        },
        "data": {
            "intermediate": {"path": "data/intermediate_files/"},
            "output": {"results": "outputs/results/", "figures": "outputs/figures/"},
        },
    }
