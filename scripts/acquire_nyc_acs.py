"""
scripts/acquire_nyc_acs.py
---------------------------
Downloads ACS 5-year 2020 socioeconomic data for NYC census tracts
and spatially joins it to census blocks.

Variables fetched:
    B19301_001E  — Per capita income
    B27001_001E  — Total population (for insurance denominator)
    B27001_003E  — Male under 6, no insurance
    B27001_006E  — Male 6-18, no insurance  
    B27001_009E  — Male 19-25, no insurance
    B27001_012E  — Male 26-34, no insurance
    B27001_015E  — Male 35-44, no insurance
    B27001_018E  — Male 45-54, no insurance
    B27001_021E  — Male 55-64, no insurance
    B27001_024E  — Male 65-74, no insurance
    B27001_027E  — Male 75+, no insurance
    (same pattern for female: B27001_031E through B27001_057E)
    B01001_001E  — Total population
    B01001_007E through B01001_025E — Male age groups 18-64
    B01001_031E through B01001_049E — Female age groups 18-64

Output:
    data/intermediate_files/blocks_New_York_City_enhanced.shp
    — NYC blocks with population + PerCapitaI + HI_block + age_18to65

Usage:
    export CENSUS_API_KEY=your_key
    python scripts/acquire_nyc_acs.py
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s"
)
log = logging.getLogger(__name__)

OUT_DIR = Path("data/intermediate_files")
ACS_URL  = "https://api.census.gov/data/2020/acs/acs5"

NYC_COUNTIES = {
    "061": "Manhattan",
    "047": "Brooklyn",
    "081": "Queens",
    "005": "Bronx",
    "085": "Staten Island",
}

# ACS variables we need
# Per capita income
# Health insurance uninsured counts (male + female, all age groups)
# Age 18-64 counts (male + female)
ACS_VARS = [
    "B19301_001E",   # per capita income

    # Male uninsured by age group
    "B27001_005E", "B27001_008E", "B27001_011E", "B27001_014E",
    "B27001_017E", "B27001_020E", "B27001_023E", "B27001_026E",
    # Female uninsured by age group
    "B27001_033E", "B27001_036E", "B27001_039E", "B27001_042E",
    "B27001_045E", "B27001_048E", "B27001_051E", "B27001_054E",

    # Total with/without health insurance (for HI rate)
    "B27001_001E",   # total population in insurance universe

    # Age 18-64 male
    "B01001_007E", "B01001_008E", "B01001_009E", "B01001_010E",
    "B01001_011E", "B01001_012E", "B01001_013E", "B01001_014E",
    "B01001_015E", "B01001_016E", "B01001_017E", "B01001_018E",
    "B01001_019E",
    # Age 18-64 female
    "B01001_031E", "B01001_032E", "B01001_033E", "B01001_034E",
    "B01001_035E", "B01001_036E", "B01001_037E", "B01001_038E",
    "B01001_039E", "B01001_040E", "B01001_041E", "B01001_042E",
    "B01001_043E",
]

MALE_UNINSURED   = ["B27001_005E","B27001_008E","B27001_011E","B27001_014E",
                    "B27001_017E","B27001_020E","B27001_023E","B27001_026E"]
FEMALE_UNINSURED = ["B27001_033E","B27001_036E","B27001_039E","B27001_042E",
                    "B27001_045E","B27001_048E","B27001_051E","B27001_054E"]
MALE_18_64       = ["B01001_007E","B01001_008E","B01001_009E","B01001_010E",
                    "B01001_011E","B01001_012E","B01001_013E","B01001_014E",
                    "B01001_015E","B01001_016E","B01001_017E","B01001_018E",
                    "B01001_019E"]
FEMALE_18_64     = ["B01001_031E","B01001_032E","B01001_033E","B01001_034E",
                    "B01001_035E","B01001_036E","B01001_037E","B01001_038E",
                    "B01001_039E","B01001_040E","B01001_041E","B01001_042E",
                    "B01001_043E"]


def fetch_acs_county(county_fips: str, county_name: str, api_key: str) -> pd.DataFrame:
    """Fetch ACS tract-level data for one NYC county."""
    params = {
        "get":  ",".join(ACS_VARS),
        "for":  "tract:*",
        "in":   f"state:36 county:{county_fips}",
        "key":  api_key,
    }
    resp = requests.get(ACS_URL, params=params, timeout=90)
    resp.raise_for_status()

    header, *rows = resp.json()
    df = pd.DataFrame(rows, columns=header)

    # Build tract GEOID (11 chars: state+county+tract)
    df["TRACTID"] = (
        df["state"].str.zfill(2)
        + df["county"].str.zfill(3)
        + df["tract"].str.zfill(6)
    )

    # Convert to numeric
    for col in ACS_VARS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # ── Derived variables ─────────────────────────────────────────────────
    # Per capita income
    df["PerCapitaI"] = df["B19301_001E"].clip(lower=0)

    # Health insurance — uninsured count as proxy for lack of insurance
    df["uninsured"] = (
        df[MALE_UNINSURED].sum(axis=1)
        + df[FEMALE_UNINSURED].sum(axis=1)
    )
    # HI_block = uninsured rate (higher = worse access)
    total_insured_universe = df["B27001_001E"].clip(lower=1)
    df["HI_block"] = df["uninsured"] / total_insured_universe

    # Age 18-64 count
    df["age_18to65"] = (
        df[MALE_18_64].sum(axis=1)
        + df[FEMALE_18_64].sum(axis=1)
    )

    log.info("  %s: %d tracts", county_name, len(df))
    return df[["TRACTID", "PerCapitaI", "HI_block", "age_18to65"]]


def fetch_all_acs(api_key: str) -> pd.DataFrame:
    """Fetch ACS data for all NYC counties."""
    parts = []
    for fips, name in NYC_COUNTIES.items():
        try:
            df = fetch_acs_county(fips, name, api_key)
            parts.append(df)
            time.sleep(0.5)
        except Exception as exc:
            log.warning("  %s failed: %s", name, exc)
    return pd.concat(parts, ignore_index=True)


def spatial_join_to_blocks(
    blocks_gdf: gpd.GeoDataFrame,
    acs_df: pd.DataFrame,
) -> gpd.GeoDataFrame:
    """
    Join tract-level ACS data to blocks via GEOID prefix match.
    Each block inherits its parent tract's socioeconomic values.
    This is standard practice when block-level ACS data is unavailable.
    """
    # Extract tract ID from block GEOID (first 11 chars)
    blocks_gdf = blocks_gdf.copy()
    blocks_gdf["TRACTID"] = blocks_gdf["GEOID"].str[:11]

    # Merge
    merged = blocks_gdf.merge(acs_df, on="TRACTID", how="left")

    # Fill any unmatched blocks with 0
    for col in ["PerCapitaI", "HI_block", "age_18to65"]:
        merged[col] = merged[col].fillna(0)

    matched = merged["PerCapitaI"].gt(0).sum()
    log.info("Blocks matched to ACS tracts: %d / %d", matched, len(merged))

    return merged


def normalise(series: pd.Series) -> pd.Series:
    """Min-max normalise a series, matching DC preprocessing."""
    mn, mx = series.min(), series.max()
    if mx > mn:
        return (series - mn) / (mx - mn)
    return pd.Series(0.0, index=series.index)


def main():
    api_key = os.environ.get("CENSUS_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "CENSUS_API_KEY not set. Run: export CENSUS_API_KEY=your_key"
        )

    # Load existing blocks
    blocks_path = OUT_DIR / "blocks_New_York_City.shp"
    if not blocks_path.exists():
        raise FileNotFoundError(
            f"Blocks shapefile not found: {blocks_path}\n"
            "Run acquire_nyc_data.py first."
        )

    log.info("Loading NYC blocks...")
    blocks = gpd.read_file(blocks_path)
    log.info("Loaded %d blocks", len(blocks))

    # Fetch ACS data
    log.info("Fetching ACS 2020 tract-level data for NYC...")
    acs_df = fetch_all_acs(api_key)
    log.info("ACS data: %d tracts", len(acs_df))

    # Spatial join
    log.info("Joining ACS data to blocks...")
    enhanced = spatial_join_to_blocks(blocks, acs_df)

    # Normalise — matching DC preprocessing in enhanced method
    log.info("Normalising socioeconomic variables...")
    enhanced["Bl_totalpo"] = normalise(enhanced["population"].astype(float))
    enhanced["PerCapitaI"] = normalise(enhanced["PerCapitaI"])
    enhanced["HI_block"]   = normalise(enhanced["HI_block"])
    enhanced["age_18to65"] = normalise(enhanced["age_18to65"])

    # Also keep Total Popu column (used directly in enhanced method)
    enhanced["Total Popu"] = enhanced["population"]

    # Save
    out_path = OUT_DIR / "blocks_New_York_City_enhanced.shp"
    enhanced.to_file(out_path)
    log.info("Saved enhanced blocks → %s", out_path)
    log.info("Columns: %s", enhanced.columns.tolist())
    log.info(
        "Sample:\n%s",
        enhanced[["GEOID","population","PerCapitaI","HI_block","age_18to65"]].head(5).to_string()
    )

    log.info("=== ACS acquisition complete ===")
    log.info("Next: update nyc_dialysis.yaml to use blocks_New_York_City_enhanced.shp")


if __name__ == "__main__":
    main()
