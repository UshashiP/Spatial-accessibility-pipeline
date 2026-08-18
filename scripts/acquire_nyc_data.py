"""
scripts/acquire_nyc_data.py
----------------------------
One-time script to prepare NYC dialysis + census block data.
Run locally ONCE, then set use_snapshot: true in configs/nyc_dialysis.yaml.

Data sources:
    Facilities : HIFLD Dialysis Centers shapefile (pre-geocoded, no API needed)
                 Download from: https://hifld-geoplatform.opendata.arcgis.com/datasets/dialysis-centers
                 Place at: data/reference/Dialysis_Centers.shp (all component files)

    Blocks     : 2020 TIGER/Line census blocks for New York State
                 Auto-downloaded (~200MB, cached after first run)
                 Population joined from Census API (2020 Decennial)

Usage:
    python scripts/acquire_nyc_data.py

Outputs:
    data/intermediate_files/Dialysis_NYC.shp
    data/intermediate_files/blocks_New_York_City.shp
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import Point

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s"
)
log = logging.getLogger(__name__)

OUT_DIR = Path("data/intermediate_files")
REF_DIR = Path("data/reference")
OUT_DIR.mkdir(parents=True, exist_ok=True)
REF_DIR.mkdir(parents=True, exist_ok=True)

NYC_CRS = "EPSG:32618"   # NYC UTM Zone 18N (metres)

# NYC city names in HIFLD dataset
NYC_CITIES = {
    'BROOKLYN', 'BRONX', 'NEW YORK', 'STATEN ISLAND',
    'FLUSHING', 'JAMAICA', 'ASTORIA', 'BAYSIDE', 'ELMHURST',
    'CORONA', 'JACKSON HEIGHTS', 'LONG ISLAND CITY', 'RIDGEWOOD',
    'WOODSIDE', 'FAR ROCKAWAY', 'HOWARD BEACH', 'OZONE PARK',
    'RICHMOND HILL', 'SOUTH OZONE PARK', 'FOREST HILLS',
    'KEW GARDENS', 'REGO PARK', 'MASPETH', 'MIDDLE VILLAGE',
    'GLENDALE', 'EAST ELMHURST', 'COLLEGE POINT', 'WHITESTONE',
    'FRESH MEADOWS', 'HOLLIS', 'CAMBRIA HEIGHTS', 'ROSEDALE',
    'SPRINGFIELD GARDENS', 'EAST NEW YORK', 'BUSHWICK',
    'BEDFORD STUYVESANT', 'CROWN HEIGHTS', 'FLATBUSH',
    'EAST FLATBUSH', 'BROWNSVILLE', 'CANARSIE', 'CONEY ISLAND',
    'BENSONHURST', 'BAY RIDGE', 'SUNSET PARK', 'PARK SLOPE',
    'RED HOOK', 'GREENPOINT', 'WILLIAMSBURG', 'EAST VILLAGE',
    'HARLEM', 'WASHINGTON HEIGHTS', 'INWOOD',
}


# ── 1. Dialysis Facilities ────────────────────────────────────────────────────

def prepare_dialysis_facilities() -> gpd.GeoDataFrame:
    """
    Load HIFLD dialysis centers shapefile, filter to NYC, normalise columns.
    Expects shapefile at data/reference/Dialysis_Centers.shp
    """
    shp_path = REF_DIR / "Dialysis_Centers.shp"
    if not shp_path.exists():
        raise FileNotFoundError(
            f"Dialysis shapefile not found at {shp_path}\n"
            "Download from: https://hifld-geoplatform.opendata.arcgis.com/datasets/dialysis-centers\n"
            "Place all shapefile components (.shp .dbf .prj .shx) in data/reference/"
        )

    log.info("Loading HIFLD dialysis centers from %s", shp_path)
    gdf = gpd.read_file(shp_path)
    log.info("Total US dialysis centers: %d", len(gdf))

    # Filter to NY state
    ny = gdf[gdf["State"] == "NY"].copy()
    log.info("NY dialysis centers: %d", len(ny))

    # Filter to NYC by city name
    nyc = ny[ny["City"].str.upper().isin(NYC_CITIES)].copy()
    log.info("NYC dialysis centers: %d", len(nyc))

    # Keep only open facilities
    if "Status" in nyc.columns:
        nyc = nyc[nyc["Status"].str.lower() == "open"].copy()
        log.info("Open NYC dialysis centers: %d", len(nyc))

    # Build geometry from X/Y columns (lon/lat)
    nyc["geometry"] = [Point(x, y) for x, y in zip(nyc["X"], nyc["Y"])]
    nyc = gpd.GeoDataFrame(nyc, geometry="geometry", crs="EPSG:4326")

    # Normalise columns
    nyc = nyc.rename(columns={"Name": "FAC_NAME"})

    # Supply = 1 per facility (HIFLD does not include station counts)
    # This models facility-count accessibility, valid for location analysis
    nyc["supply"] = 1

    # Project to NYC CRS
    nyc = nyc.to_crs(NYC_CRS)

    keep = [c for c in ["FAC_NAME", "supply", "Address", "City",
                         "Zip", "geometry"] if c in nyc.columns]
    return nyc[keep].reset_index(drop=True)


# ── 2. NYC Census Blocks ──────────────────────────────────────────────────────
TIGER_URL  = "https://www2.census.gov/geo/tiger/TIGER2020/TABBLOCK20/tl_2020_36_tabblock20.zip"
CENSUS_API = "https://api.census.gov/data/2020/dec/pl"

NYC_COUNTIES = {
    "061": "Manhattan",
    "047": "Brooklyn",
    "081": "Queens",
    "005": "Bronx",
    "085": "Staten Island",
}


def fetch_nyc_blocks() -> gpd.GeoDataFrame:
    """
    Download NYC 2020 census blocks + population.
    TIGER file (~200MB) is cached after first download.
    Population from 2020 Decennial Census API.
    Note: 2020 is the most granular block-level population data available.
          ACS estimates are only available at tract level.
    """
    zip_path = REF_DIR / "tl_2020_36_tabblock20.zip"

    if not zip_path.exists():
        log.info("Downloading NY TIGER blocks (~200MB)...")
        r = requests.get(TIGER_URL, stream=True, timeout=600)
        r.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
        log.info("Download complete")
    else:
        log.info("Using cached TIGER file")

    log.info("Reading shapefile (may take ~1 min)...")
    gdf = gpd.read_file(f"zip://{zip_path}")
    log.info("Total NY blocks: %d", len(gdf))

    # Filter to NYC counties
    gdf = gdf[gdf["COUNTYFP20"].isin(NYC_COUNTIES.keys())].copy()
    log.info("NYC blocks: %d", len(gdf))

    # Build 15-char GEOID
    gdf["GEOID"] = (
        gdf["STATEFP20"]
        + gdf["COUNTYFP20"]
        + gdf["TRACTCE20"]
        + gdf["BLOCKCE20"]
    )

    # Fetch population per borough
    # Use POP20 column built into TIGER 2020 blocks — no API needed
    if "POP20" in gdf.columns:
        gdf["population"] = pd.to_numeric(gdf["POP20"], errors="coerce").fillna(0).astype(int)
        log.info("Using TIGER POP20 | Total pop: %s", f"{gdf['population'].sum():,}")
    else:
        log.warning("POP20 not found. Columns: %s", gdf.columns.tolist())
        gdf["population"] = 0
        gdf = gdf.to_crs(NYC_CRS)

    return (
        gdf[["GEOID", "population", "geometry"]]
        .dropna(subset=["geometry"])
        .reset_index(drop=True)
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Step 1: Dialysis facilities
    fac_path = OUT_DIR / "Dialysis_NYC.shp"
    if fac_path.exists():
        existing = gpd.read_file(fac_path)
        log.info("Dialysis shapefile exists: %d facilities", len(existing))
    else:
        gdf = prepare_dialysis_facilities()
        gdf.to_file(fac_path)
        log.info("Saved %d NYC dialysis centers → %s", len(gdf), fac_path)

    # Step 2: Census blocks
    blocks_path = OUT_DIR / "blocks_New_York_City.shp"
    if blocks_path.exists():
        existing = gpd.read_file(blocks_path)
        log.info("Blocks shapefile exists: %d blocks | pop: %s",
                 len(existing), f"{existing['population'].sum():,}")
    else:
        gdf = fetch_nyc_blocks()
        gdf.to_file(blocks_path)
        log.info("Saved %d NYC blocks | pop: %s → %s",
                 len(gdf), f"{gdf['population'].sum():,}", blocks_path)

    log.info("=== Done ===")
    log.info("Next: python run_pipeline.py --config configs/nyc_dialysis.yaml")


if __name__ == "__main__":
    main()
