"""
scripts/acquire_acs.py
-----------------------
Add the SDW-2SFCA socio-economic columns to a study's census blocks, built the
same way as the Washington DC case study (the paper's data):

    block value = tract value x (block population / tract population)

from ACS 5-year (2020) tract estimates:

    PerCapitaI  — per capita income (B19301_001)
    HI_block    — residents with health-insurance coverage, civilian
                  non-institutionalized (B27001_001 minus the uninsured cells)
    age_18to65  — residents aged 18–64 (B01001, male and female 18–64 cells)

Values are left unnormalized; the transform min-max normalizes them. Every block
is kept, including blocks with no residents (their population 0 gives them no
demand). Blocks whose centroid lies outside study_area.bbox are removed — for LA
that leaves out Catalina and San Clemente Islands.

The script stops if ACS values fail to join, so a failed download can never
leave the socio-economic columns silently at zero.

Usage:
    python scripts/acquire_acs.py --config case_studies/la_fqhc.yaml \\
        --blocks data/intermediate_files/blocks_Los_Angeles.shp \\
        --out data/intermediate_files/blocks_Los_Angeles_county_enhanced.shp

Needs CENSUS_API_KEY (free: https://api.census.gov/data/key_signup.html).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from acquire_nyc_acs import FEMALE_18_64, FEMALE_UNINSURED, MALE_18_64, MALE_UNINSURED  # noqa: E402
from pipeline.config import load_config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
log = logging.getLogger(__name__)

ACS_URL = "https://api.census.gov/data/2020/acs/acs5"
INCOME, INSURANCE_UNIVERSE, TRACT_POPULATION = "B19301_001E", "B27001_001E", "B01001_001E"
UNINSURED = MALE_UNINSURED + FEMALE_UNINSURED
WORKING_AGE = MALE_18_64 + FEMALE_18_64
SOCIO_COLUMNS = ["PerCapitaI", "HI_block", "age_18to65"]


def fetch_tracts(state_fips: str, county_fips: str, api_key: str | None) -> pd.DataFrame:
    """Tract-level per capita income, insured count, working-age count and population."""
    variables = [INCOME, INSURANCE_UNIVERSE, TRACT_POPULATION] + UNINSURED + WORKING_AGE
    params = {"get": ",".join(variables), "for": "tract:*", "in": f"state:{state_fips} county:{county_fips}"}
    if api_key:
        params["key"] = api_key
    resp = requests.get(ACS_URL, params=params, timeout=120)
    resp.raise_for_status()
    if "missing_key" in resp.url:
        raise RuntimeError("Census API key required: set CENSUS_API_KEY.")
    header, *rows = resp.json()
    df = pd.DataFrame(rows, columns=header)
    for column in variables:
        # ACS marks unavailable estimates with large negative codes.
        df[column] = pd.to_numeric(df[column], errors="coerce").where(lambda v: v >= 0).fillna(0)
    return pd.DataFrame({
        "TRACTID": df["state"].str.zfill(2) + df["county"].str.zfill(3) + df["tract"].str.zfill(6),
        "income": df[INCOME],
        "insured": (df[INSURANCE_UNIVERSE] - df[UNINSURED].sum(axis=1)).clip(lower=0),
        "working_age": df[WORKING_AGE].sum(axis=1),
        "tract_population": df[TRACT_POPULATION],
    })


def clip_to_bbox(blocks: gpd.GeoDataFrame, bbox: list[float]) -> gpd.GeoDataFrame:
    """Keep blocks whose centroid lies inside [min_lon, min_lat, max_lon, max_lat]."""
    min_lon, min_lat, max_lon, max_lat = bbox
    points = blocks.geometry.representative_point().to_crs("EPSG:4326")
    inside = points.x.between(min_lon, max_lon) & points.y.between(min_lat, max_lat)
    dropped = blocks[~inside]
    log.info("Outside study bbox: %d blocks, %s residents removed",
             len(dropped), f"{int(dropped['population'].sum()):,}")
    return blocks[inside].reset_index(drop=True)


def apportion(blocks: gpd.GeoDataFrame, tracts: pd.DataFrame) -> gpd.GeoDataFrame:
    """Give each block its tract's values scaled by its share of the tract population."""
    blocks = blocks.copy()
    blocks["TRACTID"] = blocks["GEOID"].str[:11]
    merged = blocks.merge(tracts, on="TRACTID", how="left")
    share = (merged["population"] / merged["tract_population"]).where(merged["tract_population"] > 0, 0)
    merged["PerCapitaI"] = merged["income"] * share
    merged["HI_block"] = merged["insured"] * share
    merged["age_18to65"] = merged["working_age"] * share
    merged[SOCIO_COLUMNS] = merged[SOCIO_COLUMNS].fillna(0)
    return merged.drop(columns=["TRACTID", "income", "insured", "working_age", "tract_population"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", required=True)
    parser.add_argument("--blocks", required=True, help="census blocks with GEOID and population")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    config = load_config(args.config)
    study = config["study_area"]
    api_key = os.environ.get("CENSUS_API_KEY")

    blocks = gpd.read_file(args.blocks).to_crs(study["coordinate_system"])
    blocks = blocks[["GEOID", "population", "geometry"]].copy()
    blocks["GEOID"] = blocks["GEOID"].astype(str)
    log.info("Loaded %d blocks (%s residents, %d with none)", len(blocks),
             f"{int(blocks['population'].sum()):,}", int((blocks["population"] == 0).sum()))
    if study.get("bbox"):
        blocks = clip_to_bbox(blocks, study["bbox"])

    tracts = []
    for county in study["county_fips"]:
        tracts.append(fetch_tracts(study["state_fips"], str(county).zfill(3), api_key))
        time.sleep(0.5)
    tracts = pd.concat(tracts, ignore_index=True)
    log.info("ACS: %d tracts", len(tracts))

    enhanced = apportion(blocks, tracts)
    populated = enhanced["population"] > 0
    matched = enhanced.loc[populated, "GEOID"].str[:11].isin(tracts["TRACTID"]).mean()
    if matched < 0.99 or (enhanced.loc[populated, SOCIO_COLUMNS] == 0).all().any():
        raise RuntimeError(
            f"ACS join failed: {matched:.1%} of populated blocks matched a tract, or a "
            "socio-economic column is all zero. Not writing a file with empty weights."
        )

    enhanced.to_file(args.out)
    log.info("Saved %d blocks (%s residents, %d with none) → %s", len(enhanced),
             f"{int(enhanced['population'].sum()):,}", int((~populated).sum()), args.out)


if __name__ == "__main__":
    main()
