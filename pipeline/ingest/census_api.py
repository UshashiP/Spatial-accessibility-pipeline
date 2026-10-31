"""
pipeline.ingest.census_api
---------------------------
Fetches 2020 Decennial Census (PL 94-171) block-level total population
for any US state via the Census Bureau public REST API.

Study area is fully driven by config.yaml (study_area.state_fips).

Snapshot mode
-------------
Set data.snapshot.use_snapshot: true in config.yaml to skip the API
and load directly from a local shapefile. Recommended for reproducibility
and offline runs. Users supply their own census block shapefile for their
study area and update data.local_shapefiles.census_blocks in config.yaml.

Returns a GeoDataFrame with columns:
    GEOID, population, geometry
"""

from __future__ import annotations

import logging
import json
from pathlib import Path
from typing import Optional

import geopandas as gpd
import pandas as pd

from pipeline.config import load_config
from pipeline.ingest.http_utils import get_with_retry

log = logging.getLogger(__name__)

_TIGER_BASE = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services"
    "/TIGERweb/Tracts_Blocks/MapServer/12/query"
)
_CENSUS_API_BASE = "https://api.census.gov/data"


# ── Population table ──────────────────────────────────────────────────────────

def _fetch_population_table(
    state_fips: str,
    api_key: Optional[str],
    year: int,
    dataset: str,
    variable: str,
    county_fips: list[str] | None = None,
) -> pd.DataFrame:
    url = f"{_CENSUS_API_BASE}/{year}/{dataset}"
    frames: list[pd.DataFrame] = []

    def _request(in_clause: str) -> pd.DataFrame:
        params: dict = {
            "get": f"NAME,{variable}",
            "for": "block:*",
            "in": in_clause,
        }
        if api_key:
            params["key"] = api_key
        resp = get_with_retry(url, params)
        # Census now redirects unauthenticated requests to missing_key.html.
        if "missing_key" in resp.url or "A valid" in resp.text and "key" in resp.text:
            raise RuntimeError(
                "Census API key required. Set CENSUS_API_KEY or provide local snapshot shapefiles."
            )
        data = resp.json()
        header, *rows = data
        return pd.DataFrame(rows, columns=header)

    if county_fips:
        log.info(
            "Fetching Census population table — state_fips=%s counties=%s",
            state_fips,
            county_fips,
        )
        for county in county_fips:
            county3 = str(county).zfill(3)
            frames.append(_request(f"state:{state_fips} county:{county3} tract:*"))
        df = pd.concat(frames, ignore_index=True)
    else:
        log.info("Fetching Census population table — state_fips=%s (all counties)", state_fips)
        df = _request(f"state:{state_fips} county:* tract:*")

    df = df.rename(columns={variable: "population"})
    df["population"] = pd.to_numeric(df["population"], errors="coerce").fillna(0).astype(int)
    df["GEOID"] = (
        df["state"].str.zfill(2)
        + df["county"].str.zfill(3)
        + df["tract"].str.zfill(6)
        + df["block"].str.zfill(4)
    )
    log.info("Census API: %d blocks retrieved", len(df))
    return df


# ── TIGER block geometry ──────────────────────────────────────────────────────

def _fetch_block_geometries(state_fips: str, county_fips: str) -> gpd.GeoDataFrame:
    params = {
        "where": f"STATE='{state_fips}' AND COUNTY='{county_fips}'",
        "outFields": "GEOID,STATE,COUNTY,TRACT,BLOCK",
        "f": "geojson",
        "returnGeometry": "true",
        "outSR": "4326",
    }
    log.info("Fetching TIGER geometries — state=%s county=%s", state_fips, county_fips)
    resp = get_with_retry(_TIGER_BASE, params)
    payload = json.loads(resp.text)
    if payload.get("error"):
        raise RuntimeError(f"TIGER query failed: {payload['error']}")
    gdf = gpd.GeoDataFrame.from_features(payload["features"], crs="EPSG:4326")
    return gdf[["GEOID", "geometry"]]


# ── Local fallback ────────────────────────────────────────────────────────────

def _local_blocks_path(config: dict) -> Path:
    """
    Resolve local shapefile path.
    Uses explicit override from config if provided, otherwise derives
    from study area name. Users should set data.local_shapefiles.census_blocks
    in config.yaml to point to their own data.
    """
    override = config.get("data", {}).get("local_shapefiles", {}).get("census_blocks")
    if override:
        return Path(override)
    area = config["study_area"]["name"].replace(" ", "_")
    return Path(config["data"]["intermediate"]["path"]) / f"blocks_{area}.shp"


def _load_local_blocks(config: dict) -> gpd.GeoDataFrame:
    path = _local_blocks_path(config)
    if not path.exists():
        raise FileNotFoundError(f"Local census blocks file not found: {path}")
    log.info("Loading local census blocks from %s", path)
    gdf = gpd.read_file(path)

    # GEOID normalisation
    for candidate in ("GEOCODE", "GEOID_left", "GEOID", "GEOID20"):
        if candidate in gdf.columns:
            gdf = gdf.rename(columns={candidate: "GEOID"})
            break

    # Population column — use explicit override from config if provided
    pop_col_override = config.get("data", {}).get("population_column")
    if pop_col_override and pop_col_override in gdf.columns:
        gdf = gdf.rename(columns={pop_col_override: "population"})
        log.info("Using population column: %s", pop_col_override)
    else:
        # Auto-detect fallback
        for candidate in ("Bl_totalpo", "Total po_3", "Total Popu", "population", "P1_001N"):
            if candidate in gdf.columns:
                gdf = gdf.rename(columns={candidate: "population"})
                log.info("Auto-detected population column: %s", candidate)
                break

    gdf["population"] = pd.to_numeric(gdf["population"], errors="coerce").fillna(0).astype(int)
    crs = config["study_area"]["coordinate_system"]
    if str(gdf.crs) != crs:
        gdf = gdf.to_crs(crs)

    keep_cols = ["GEOID", "population", "geometry"] + [c for c in gdf.columns if c not in ["GEOID", "population", "geometry"]]
    return gdf[keep_cols].dropna(subset=["geometry"]).reset_index(drop=True)


# ── Population settings ───────────────────────────────────────────────────────

def _apply_population_settings(gdf: gpd.GeoDataFrame, config: dict) -> gpd.GeoDataFrame:
    """
    Apply the population options in config ``data``:

    population_reference
        CSV with GEOID and population_2020 columns that replaces the loaded
        population, e.g. official 2020 block counts where a snapshot was edited.
        It must cover every block.
    empty_blocks
        "exclude" (default): blocks with no residents keep a population of 0,
        so they add no demand and are left out of summary statistics.
        "median": they are set to the median block population (zeros included).
    """
    data_cfg = config.get("data", {})

    reference = data_cfg.get("population_reference")
    if reference:
        official = pd.read_csv(reference, dtype={"GEOID": str})
        merged = gdf[["GEOID"]].astype(str).merge(official, on="GEOID", how="left", validate="one_to_one")
        if merged["population_2020"].isna().any():
            raise ValueError(
                f"{reference} does not cover every census block "
                f"({int(merged['population_2020'].isna().sum())} missing)."
            )
        gdf = gdf.copy()
        gdf["population"] = merged["population_2020"].astype(int).to_numpy()
        log.info("Population from reference %s (total %s)", reference, f"{gdf['population'].sum():,}")

    mode = data_cfg.get("empty_blocks", "exclude")
    empty = gdf["population"] == 0
    if mode == "median":
        median = int(gdf["population"].median())
        gdf = gdf.copy()
        gdf.loc[empty, "population"] = median
        log.info("Empty blocks: %d set to the median block population (%d)", int(empty.sum()), median)
    elif mode == "exclude":
        log.info("Empty blocks: %d kept at 0 (no demand; excluded from statistics)", int(empty.sum()))
    else:
        raise ValueError(f"data.empty_blocks must be 'exclude' or 'median', got {mode!r}")
    return gdf


def report_area_mask(geometries: gpd.GeoSeries, config: dict) -> pd.Series:
    """
    True for geometries inside the study's reporting area.

    ``study_area.report_area`` lets a study model a wider region than it reports:
    LA models all of LA County — residents and clinics across the city line serve
    and compete with each other — but reports the City of Los Angeles. Its keys:
    ``boundary`` (a vector file, read with GeoPandas), ``url`` (downloaded to
    ``boundary`` when missing), ``id_column`` and ``id`` (the feature to use).
    A geometry counts as inside when its representative point is. Without a
    report_area every geometry is inside.
    """
    area = config.get("study_area", {}).get("report_area")
    if not area:
        return pd.Series(True, index=geometries.index)
    path = Path(area["boundary"])
    if not path.exists() and area.get("url"):
        path.parent.mkdir(parents=True, exist_ok=True)
        log.info("Downloading report-area boundary %s", area["url"])
        path.write_bytes(get_with_retry(area["url"], {}).content)
    boundary = gpd.read_file(f"zip://{path}" if path.suffix == ".zip" else path)
    boundary = boundary[boundary[area.get("id_column", "GEOID")].astype(str) == str(area["id"])]
    if len(boundary) != 1:
        raise ValueError(f"report_area: expected one feature with id {area['id']} in {path}, found {len(boundary)}")
    shape = boundary.to_crs(geometries.crs).geometry.iloc[0]
    return geometries.representative_point().within(shape)


def _apply_report_area(gdf: gpd.GeoDataFrame, config: dict) -> gpd.GeoDataFrame:
    """Flag blocks inside the reporting area (all blocks when none is configured)."""
    gdf = gdf.copy()
    gdf["in_report_area"] = report_area_mask(gdf.geometry, config).to_numpy()
    if not gdf["in_report_area"].all():
        inside = gdf["in_report_area"]
        log.info("Report area: %d of %d blocks (%s residents) — the rest are modelled, not reported",
                 int(inside.sum()), len(gdf), f"{int(gdf.loc[inside, 'population'].sum()):,}")
    return gdf


# ── Public entry point ────────────────────────────────────────────────────────

def ingest_census_blocks(config: dict | None = None) -> gpd.GeoDataFrame:
    """
    Load census block populations for the configured study area.

    Behaviour
    ---------
    - If data.snapshot.use_snapshot is true in config: loads from local
      shapefile directly (recommended for reproducibility).
    - Otherwise: attempts Census REST API, falls back to local on failure.

    Users should place their census block shapefile in data/intermediate_files/
    and set data.local_shapefiles.census_blocks in config.yaml.

    Returns
    -------
    GeoDataFrame
        Columns: GEOID, population, geometry
        CRS: as specified in config study_area.coordinate_system
    """
    if config is None:
        config = load_config()

    # Snapshot mode — prefer local, but auto-fallback to live API if missing.
    if config.get("data", {}).get("snapshot", {}).get("use_snapshot", False):
        log.info("Snapshot mode — loading validated local census blocks")
        try:
            gdf = _load_local_blocks(config)
            log.info("Census ingest (snapshot) complete: %d blocks", len(gdf))
            return _apply_report_area(_apply_population_settings(gdf, config), config)
        except FileNotFoundError as exc:
            log.warning("Snapshot census file missing (%s) — falling back to Census API", exc)

    # Live API mode with local fallback
    cfg_study = config["study_area"]
    cfg_census = config["census"]
    state_fips = cfg_study["state_fips"]
    crs = cfg_study["coordinate_system"]
    api_key = config.get("census", {}).get("api_key")

    try:
        pop_df = _fetch_population_table(
            state_fips=state_fips,
            api_key=api_key,
            year=cfg_census["year"],
            dataset=cfg_census["dataset"],
            variable=cfg_census["variables"]["total_population"],
            county_fips=cfg_study.get("county_fips"),
        )

        counties = pop_df["county"].unique().tolist()
        gdf_parts = [_fetch_block_geometries(state_fips, c) for c in counties]
        geom_all = pd.concat(gdf_parts, ignore_index=True)

        merged = pop_df.merge(geom_all, on="GEOID", how="left")
        gdf = gpd.GeoDataFrame(merged, geometry="geometry", crs="EPSG:4326").to_crs(crs)
        gdf = gdf.dropna(subset=["geometry"]).reset_index(drop=True)

        log.info("Census ingest (API) complete: %d blocks", len(gdf))
        return _apply_report_area(_apply_population_settings(gdf, config), config)

    except Exception as exc:
        log.warning("Census API failed (%s) — falling back to local shapefile", exc)
        try:
            gdf = _load_local_blocks(config)
            log.info("Census ingest (local fallback) complete: %d blocks", len(gdf))
            return _apply_report_area(_apply_population_settings(gdf, config), config)
        except FileNotFoundError as local_exc:
            raise RuntimeError(
                "Census ingest could not proceed: live API unavailable and local snapshot missing. "
                "Set CENSUS_API_KEY for live mode or provide the configured local snapshot shapefile."
            ) from local_exc
