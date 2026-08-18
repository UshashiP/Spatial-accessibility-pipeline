"""
pipeline.ingest.cms_api
------------------------
Fetches facility data from the CMS Provider of Services public dataset
via the data.cms.gov Socrata API.

Facility type, state, CMS dataset ID, and supply column are all read
from config.yaml — no values are hardcoded.

Snapshot mode
-------------
Set data.snapshot.use_snapshot: true in config.yaml to skip the API
and load directly from a local shapefile. Recommended for reproducibility
and offline runs. Users supply their own facility shapefile and update
data.local_shapefiles.facilities in config.yaml.

The raw CMS supply column (e.g. CRTFD_BED_CNT) is normalised to 'supply'
on output so downstream modules remain facility-agnostic.

Returns a GeoDataFrame with columns:
    FAC_NAME, supply, geometry  (+ raw CMS columns retained)
"""

from __future__ import annotations

import io
import logging
import time
from pathlib import Path
from typing import Optional

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import Point

from pipeline.config import load_config
from pipeline.ingest.http_utils import get_with_retry

log = logging.getLogger(__name__)

_CMS_BASE = "https://data.cms.gov/provider-data/api/1/datastore/query"
_CMS_META = "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items"
_GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"


def _clip_to_study_area(gdf: gpd.GeoDataFrame, config: dict) -> gpd.GeoDataFrame:
    """Clip facility points to configured study-area bbox when available."""
    bbox = config.get("study_area", {}).get("bbox")
    if not bbox or len(bbox) != 4:
        return gdf

    minx, miny, maxx, maxy = bbox
    gdf_4326 = gdf.to_crs("EPSG:4326") if str(gdf.crs) != "EPSG:4326" else gdf.copy()
    clipped = gdf_4326.cx[minx:maxx, miny:maxy].copy()

    if len(clipped) == 0:
        log.warning("Study-area bbox clip produced 0 facilities; returning un-clipped facilities")
        return gdf

    if str(gdf.crs) != "EPSG:4326":
        clipped = clipped.to_crs(gdf.crs)
    log.info("Facility clip to study-area bbox: %d -> %d", len(gdf), len(clipped))
    return clipped


# ── CMS data ──────────────────────────────────────────────────────────────────

def _fetch_cms_facilities(
    dataset_id: str,
    category_code: str,
    state_abbrev: str,
    api_key: Optional[str] = None,
) -> pd.DataFrame:
    all_results: list[dict] = []
    offset, limit = 0, 500
    headers = {"X-App-Token": api_key} if api_key else {}

    log.info(
        "Fetching CMS facilities — dataset=%s category=%s state=%s",
        dataset_id, category_code, state_abbrev,
    )

    while True:
        params = {
            "id": dataset_id,
            "filters[STATE_CD]": state_abbrev,
            "offset": offset,
            "limit": limit,
        }
        if category_code:
            params["filters[PRVDR_CTGRY_CD]"] = category_code
        resp = get_with_retry(_CMS_BASE, params)
        payload = resp.json()
        results = payload.get("results", [])
        all_results.extend(results)

        total = payload.get("count", len(all_results))
        log.debug("  offset=%d fetched=%d total=%d", offset, len(results), total)

        if offset + limit >= total or not results:
            break
        offset += limit
        time.sleep(0.2)

    if not all_results:
        # Some datasets (notably dialysis listing 23ew-n7w9) are published as CSV
        # distribution links while datastore query can return 0 rows.
        csv_df = _fetch_cms_dataset_csv(dataset_id, state_abbrev)
        if csv_df is not None and len(csv_df) > 0:
            log.info("CMS CSV fallback: %d facilities retrieved", len(csv_df))
            return csv_df
        raise ValueError(
            f"CMS API returned 0 facilities for dataset={dataset_id}, "
            f"category={category_code}, state={state_abbrev}. "
            "The dataset ID may have changed. Set data.snapshot.use_snapshot: true "
            "in config.yaml to use local data instead."
        )

    df = pd.DataFrame(all_results)
    log.info("CMS ingest: %d facilities retrieved", len(df))
    return df


def _fetch_cms_dataset_csv(dataset_id: str, state_abbrev: str) -> pd.DataFrame | None:
    """Fallback: load provider-data CSV distribution URL from metastore."""
    try:
        meta = requests.get(_CMS_META, timeout=120)
        meta.raise_for_status()
        items = meta.json()
        item = next((i for i in items if i.get("identifier") == dataset_id), None)
        if not item:
            return None
        distributions = item.get("distribution", [])
        if not distributions:
            return None
        csv_url = next((d.get("downloadURL") for d in distributions if "csv" in str(d.get("mediaType", "")).lower()), None)
        if not csv_url:
            return None

        log.info("Loading CMS CSV fallback from %s", csv_url)
        raw = pd.read_csv(csv_url)

        # Map known dialysis-listing columns to ingest-normalized names.
        rename_map = {
            "Facility Name": "FAC_NAME",
            "Address Line 1": "STR_ADDR_LN_1",
            "City/Town": "CITY_NAME",
            "State": "STATE_CD",
            "ZIP Code": "ZIP_CD",
            "# of Dialysis Stations": "TOTAL_DIALYSIS_STATIONS",
        }
        for old, new in rename_map.items():
            if old in raw.columns:
                raw = raw.rename(columns={old: new})

        if "STATE_CD" in raw.columns:
            raw = raw[raw["STATE_CD"].astype(str).str.upper() == state_abbrev.upper()].copy()
        return raw.reset_index(drop=True)
    except Exception as exc:
        log.warning("CMS CSV fallback failed: %s", exc)
        return None


# ── Address geocoding ─────────────────────────────────────────────────────────

def _geocode_batch(df: pd.DataFrame) -> gpd.GeoDataFrame:
    addr_df = pd.DataFrame({
        "id":     df.index.astype(str),
        "street": df.get("STR_ADDR_LN_1", df.get("FAC_ADDR", "")),
        "city":   df.get("CITY_NAME",     df.get("FAC_CITY", "")),
        "state":  df.get("STATE_CD",      df.get("FAC_STATE", "")),
        "zip":    df.get("ZIP_CD",        df.get("FAC_ZIP", "")),
    })
    csv_buf = io.StringIO()
    addr_df.to_csv(csv_buf, header=False, index=False)

    log.info("Geocoding %d facility addresses via Census Geocoder", len(addr_df))
    files = {
        "addressFile": ("addresses.csv", csv_buf.getvalue().encode(), "text/csv"),
        "benchmark":   (None, "Public_AR_Current"),
        "returntype":  (None, "locations"),
        "format":      (None, "csv"),
    }
    resp = requests.post(_GEOCODER_URL, files=files, timeout=120)
    resp.raise_for_status()

    result_df = pd.read_csv(
        io.StringIO(resp.text),
        header=None,
        names=["id", "input_addr", "match", "match_type",
               "matched_addr", "coordinates", "tigerlineid", "side"],
        dtype=str,
    )

    def _parse_coord(row: pd.Series):
        if row["match"] == "Match" and pd.notna(row["coordinates"]):
            lon_s, lat_s = row["coordinates"].split(",")
            return float(lon_s), float(lat_s)
        return None, None

    coords = result_df.apply(_parse_coord, axis=1, result_type="expand")
    coords.columns = ["lon", "lat"]
    coords.index = result_df["id"].astype(int)

    df = df.copy()
    df["lon"] = coords["lon"]
    df["lat"] = coords["lat"]

    unmatched = df["lon"].isna().sum()
    if unmatched:
        log.warning("%d facilities could not be geocoded and will be dropped", unmatched)

    df = df.dropna(subset=["lon", "lat"]).copy()
    geometry = [Point(x, y) for x, y in zip(df["lon"], df["lat"])]
    return gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")


# ── Local fallback ────────────────────────────────────────────────────────────

def _local_facilities_path(config: dict) -> Path:
    """
    Resolve local shapefile path.
    Uses explicit override from config if provided, otherwise derives
    from facility type and study area name. Users should set
    data.local_shapefiles.facilities in config.yaml to point to their data.
    """
    override = config.get("data", {}).get("local_shapefiles", {}).get("facilities")
    if override:
        return Path(override)
    ftype = config["facility"]["type"]
    area = config["study_area"]["name"].replace(" ", "_")
    return Path(config["data"]["intermediate"]["path"]) / f"{ftype}_{area}.shp"


def _load_local_facilities(config: dict) -> gpd.GeoDataFrame:
    path = _local_facilities_path(config)
    if not path.exists():
        raise FileNotFoundError(f"Local facilities file not found: {path}")
    log.info("Loading local facilities from %s", path)
    gdf = gpd.read_file(path)

    raw_supply_col = config["facility"]["supply_column"]
    for candidate in (raw_supply_col, "BEDS", "BED_COUNT", "beds", "supply"):
        if candidate in gdf.columns:
            gdf = gdf.rename(columns={candidate: "supply"})
            break

    gdf["supply"] = pd.to_numeric(gdf["supply"], errors="coerce").fillna(0)

    for candidate in ("NAME", "FAC_NAME", "name"):
        if candidate in gdf.columns:
            gdf = gdf.rename(columns={candidate: "FAC_NAME"})
            break

    crs = config["study_area"]["coordinate_system"]
    if str(gdf.crs) != crs:
        gdf = gdf.to_crs(crs)

    gdf = _clip_to_study_area(gdf, config)

    cols = [c for c in gdf.columns if c != "geometry"] + ["geometry"]
    return gdf[cols].dropna(subset=["geometry"]).reset_index(drop=True)


# ── Public entry point ────────────────────────────────────────────────────────

def ingest_facilities(config: dict | None = None) -> gpd.GeoDataFrame:
    """
    Load facilities for the configured study area and facility type.

    Behaviour
    ---------
    - If data.snapshot.use_snapshot is true in config: loads from local
      shapefile directly (recommended for reproducibility).
    - Otherwise: attempts CMS REST API + geocoding, falls back to local
      shapefile on failure.

    Users should place their facility shapefile in data/intermediate_files/
    and set data.local_shapefiles.facilities in config.yaml.

    The raw supply column is normalised to 'supply' on output so all
    downstream modules remain facility-type agnostic.

    Returns
    -------
    GeoDataFrame
        Columns: FAC_NAME, supply, geometry (+ raw CMS columns if API used)
        CRS: as specified in config study_area.coordinate_system
    """
    if config is None:
        config = load_config()

    # Snapshot mode — prefer local, but auto-fallback to live API if missing.
    if config.get("data", {}).get("snapshot", {}).get("use_snapshot", False):
        log.info("Snapshot mode — loading validated local facilities")
        try:
            gdf = _load_local_facilities(config)
            log.info("Facility ingest (snapshot) complete: %d facilities [%s, %s]",
                     len(gdf), config["facility"]["type"], config["study_area"]["name"])
            return gdf
        except FileNotFoundError as exc:
            log.warning("Snapshot facilities file missing (%s) — falling back to CMS API", exc)

    # Live API mode with local fallback
    cfg_fac = config["facility"]
    cfg_study = config["study_area"]
    crs = cfg_study["coordinate_system"]
    api_key = config.get("cms", {}).get("api_key")

    try:
        raw_df = _fetch_cms_facilities(
            dataset_id=cfg_fac["cms_dataset_id"],
            category_code=cfg_fac["cms_category_code"],
            state_abbrev=cfg_study["state_abbrev"],
            api_key=api_key,
        )

        raw_supply_col = cfg_fac["supply_column"]
        if raw_supply_col in raw_df.columns:
            raw_df["supply"] = pd.to_numeric(raw_df[raw_supply_col], errors="coerce").fillna(0)
        else:
            log.warning("Supply column '%s' not found in CMS data; defaulting to 0", raw_supply_col)
            raw_df["supply"] = 0

        gdf = _geocode_batch(raw_df)
        gdf = gdf.to_crs(crs)
        gdf = _clip_to_study_area(gdf, config)
        log.info("Facility ingest (API) complete: %d facilities [%s, %s]",
                 len(gdf), cfg_fac["type"], cfg_study["name"])
        return gdf

    except Exception as exc:
        log.warning("CMS API ingest failed (%s) — falling back to local shapefile", exc)
        return _load_local_facilities(config)
