"""
scripts/acquire_la_data.py
---------------------------
Downloads LA County FQHC data from HRSA and census blocks.

Run once:
    python scripts/acquire_la_data.py

Outputs:
    data/intermediate_files/FQHC_LA.shp
    data/intermediate_files/blocks_Los_Angeles.shp
"""

from __future__ import annotations

import io
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

LA_CRS = "EPSG:32611"  # UTM Zone 11N — LA

# LA County city names
LA_CITIES = {
    'LOS ANGELES', 'EAST LOS ANGELES', 'COMPTON', 'INGLEWOOD',
    'LONG BEACH', 'CARSON', 'GARDENA', 'HAWTHORNE', 'LYNWOOD',
    'TORRANCE', 'PASADENA', 'ALHAMBRA', 'POMONA', 'EL MONTE',
    'DOWNEY', 'NORWALK', 'WEST COVINA', 'WHITTIER', 'MONTEREY PARK',
    'SANTA MONICA', 'BURBANK', 'GLENDALE', 'Lancaster', 'PALMDALE',
    'BELLFLOWER', 'LAKEWOOD', 'SOUTH GATE', 'PICO RIVERA',
    'MONTEBELLO', 'TORRANCE', 'HAWTHORNE', 'WATTS', 'BOYLE HEIGHTS',
    'EAST HOLLYWOOD', 'KOREATOWN', 'WESTLAKE', 'ECHO PARK',
    'VAN NUYS', 'CANOGA PARK', 'RESEDA', 'SAN PEDRO', 'WILMINGTON',
    'HARBOR CITY', 'SYLMAR', 'PACOIMA', 'SUNLAND', 'TUJUNGA',
    'ARLETA', 'PANORAMA CITY', 'NORTH HILLS', 'GRANADA HILLS',
    'CHATSWORTH', 'NORTHRIDGE', 'ENCINO', 'SHERMAN OAKS',
    'STUDIO CITY', 'NORTH HOLLYWOOD', 'SUN VALLEY', 'SUNLAND',
    'LAKEVIEW TERRACE', 'MISSION HILLS', 'SEPULVEDA', 'WEST HILLS',
    'WINNETKA', 'WOODLAND HILLS', 'TARZANA', 'VENICE', 'CULVER CITY',
    'INGLEWOOD', 'HAWTHORNE', 'LAWNDALE', 'REDONDO BEACH',
    'MANHATTAN BEACH', 'HERMOSA BEACH', 'EL SEGUNDO', 'INGLEWOOD',
    'BALDWIN PARK', 'AZUSA', 'COVINA', 'GLENDORA', 'SAN DIMAS',
    'ARCADIA', 'MONROVIA', 'DUARTE', 'AZUSA', 'IRWINDALE',
    'INDUSTRY', 'LA PUENTE', 'HACIENDA HEIGHTS', 'ROWLAND HEIGHTS',
    'DIAMOND BAR', 'WALNUT', 'CITY OF INDUSTRY',
}

# LA County FIPS
LA_COUNTY_FIPS = "037"
LA_STATE_FIPS  = "06"

HRSA_URL   = "https://data.hrsa.gov/DataDownload/DD_Files/Health_Center_Service_Delivery_and_LookAlike_Sites.csv"
TIGER_URL  = f"https://www2.census.gov/geo/tiger/TIGER2020/TABBLOCK20/tl_2020_{LA_STATE_FIPS}_tabblock20.zip"
CENSUS_API = "https://api.census.gov/data/2020/dec/pl"


# ── 1. FQHC Facilities ────────────────────────────────────────────────────────

def fetch_fqhc_la() -> gpd.GeoDataFrame:
    """Download HRSA FQHC CSV and filter to LA County."""
    log.info("Downloading HRSA Health Center data...")
    r = requests.get(HRSA_URL, timeout=120)
    r.raise_for_status()

    df = pd.read_csv(io.StringIO(r.text), dtype=str)
    log.info("Total HRSA records: %d", len(df))

    # Filter to CA
    df = df[df["Site State Abbreviation"] == "CA"].copy()
    log.info("CA records: %d", len(df))

    # Filter to LA County using FIPS or city name
    fips_col = "State and County Federal Information Processing Standard Code"
    if fips_col in df.columns:
        la_fips = f"{LA_STATE_FIPS}{LA_COUNTY_FIPS}"
        df = df[df[fips_col].str.startswith(la_fips, na=False)].copy()
        log.info("LA County records (by FIPS): %d", len(df))
    else:
        df = df[df["Site City"].str.upper().isin(LA_CITIES)].copy()
        log.info("LA area records (by city): %d", len(df))

    # Parse coordinates
    x_col = "Geocoding Artifact Address Primary X Coordinate"
    y_col = "Geocoding Artifact Address Primary Y Coordinate"

    df[x_col] = pd.to_numeric(df[x_col], errors="coerce")
    df[y_col] = pd.to_numeric(df[y_col], errors="coerce")
    df = df.dropna(subset=[x_col, y_col]).copy()
    log.info("Records with coordinates: %d", len(df))

    # Build geometry — HRSA coordinates are in WGS84 (EPSG:4326)
    geometry = [Point(x, y) for x, y in zip(df[x_col], df[y_col])]
    gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")

    # Normalise columns
    gdf = gdf.rename(columns={"Site Name": "FAC_NAME"})

    # Supply = 1 per facility (HRSA doesn't include patient capacity per site)
    # This models facility-count accessibility — valid for primary care access
    gdf["supply"] = 1
    log.info(
        "Note: supply=1 per FQHC site. HRSA does not publish per-site capacity. "
        "This models geographic access to primary care facilities."
    )

    # Project to LA CRS
    gdf = gdf.to_crs(LA_CRS)

    keep = [c for c in ["FAC_NAME", "supply", "Site Address",
                         "Site City", "Site Postal Code",
                         "Health Center Type", "geometry"] if c in gdf.columns]
    return gdf[keep].reset_index(drop=True)


# ── 2. LA Census Blocks ───────────────────────────────────────────────────────

def fetch_la_blocks() -> gpd.GeoDataFrame:
    """Download CA TIGER blocks, filter to LA County, join population."""
    zip_path = REF_DIR / "tl_2020_06_tabblock20.zip"

    if not zip_path.exists():
        log.info("Downloading CA TIGER blocks (~300MB)...")
        r = requests.get(TIGER_URL, stream=True, timeout=600)
        r.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
        log.info("Download complete")
    else:
        log.info("Using cached TIGER file: %s", zip_path)

    log.info("Reading shapefile (may take ~2 mins for CA)...")
    gdf = gpd.read_file(f"zip://{zip_path}")
    log.info("Total CA blocks: %d", len(gdf))

    # Filter to LA County
    gdf = gdf[gdf["COUNTYFP20"] == LA_COUNTY_FIPS].copy()
    log.info("LA County blocks: %d", len(gdf))

    # Build GEOID
    gdf["GEOID"] = (
        gdf["STATEFP20"]
        + gdf["COUNTYFP20"]
        + gdf["TRACTCE20"]
        + gdf["BLOCKCE20"]
    )

    # Use POP20 from TIGER — no Census API needed
    if "POP20" in gdf.columns:
        gdf["population"] = pd.to_numeric(
            gdf["POP20"], errors="coerce"
        ).fillna(0).astype(int)
        log.info(
            "Using TIGER POP20 | Total pop: %s",
            f"{gdf['population'].sum():,}"
        )
    else:
        log.warning("POP20 not found — fetching from Census API...")
        gdf = _fetch_population_api(gdf)

    # Project to LA CRS
    gdf = gdf.to_crs(LA_CRS)

    return (
        gdf[["GEOID", "population", "geometry"]]
        .dropna(subset=["geometry"])
        .reset_index(drop=True)
    )


def _fetch_population_api(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Fallback: fetch population from Census API."""
    log.info("Fetching population from Census API...")
    params = {
        "get": "P1_001N",
        "for": "block:*",
        "in": f"state:{LA_STATE_FIPS} county:{LA_COUNTY_FIPS} tract:*",
    }
    resp = requests.get(CENSUS_API, params=params, timeout=120)
    resp.raise_for_status()
    header, *rows = resp.json()
    pop_df = pd.DataFrame(rows, columns=header)
    pop_df["population"] = pd.to_numeric(
        pop_df["P1_001N"], errors="coerce"
    ).fillna(0).astype(int)
    pop_df["GEOID"] = (
        pop_df["state"].str.zfill(2)
        + pop_df["county"].str.zfill(3)
        + pop_df["tract"].str.zfill(6)
        + pop_df["block"].str.zfill(4)
    )
    gdf = gdf.merge(pop_df[["GEOID", "population"]], on="GEOID", how="left")
    gdf["population"] = gdf["population"].fillna(0).astype(int)
    log.info("Total pop: %s", f"{gdf['population'].sum():,}")
    return gdf


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # FQHCs
    fac_path = OUT_DIR / "FQHC_LA.shp"
    if fac_path.exists():
        existing = gpd.read_file(fac_path)
        log.info("FQHC shapefile exists: %d facilities", len(existing))
    else:
        gdf = fetch_fqhc_la()
        gdf.to_file(fac_path)
        log.info(
            "Saved %d LA FQHCs → %s", len(gdf), fac_path
        )
        log.info(
            "Sample:\n%s",
            gdf[["FAC_NAME", "supply", "Site City"]].head(5).to_string()
        )

    # Census blocks
    blocks_path = OUT_DIR / "blocks_Los_Angeles.shp"
    if blocks_path.exists():
        existing = gpd.read_file(blocks_path)
        log.info(
            "Blocks shapefile exists: %d blocks | pop: %s",
            len(existing), f"{existing['population'].sum():,}"
        )
    else:
        gdf = fetch_la_blocks()
        gdf.to_file(blocks_path)
        log.info(
            "Saved %d LA blocks | pop: %s → %s",
            len(gdf), f"{gdf['population'].sum():,}", blocks_path
        )

    log.info("=== LA data acquisition complete ===")
    log.info("Next: python run_pipeline.py --config case_studies/la_fqhc.yaml")


if __name__ == "__main__":
    main()
