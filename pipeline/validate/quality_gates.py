"""
pipeline.validate.quality_gates
---------------------------------
Data quality checks that promote raw (Bronze) data to validated (Silver).

Design principle: all facility-specific column names are normalised to
'supply' by the ingest stage, so these gates are facility-type agnostic.
No CMS column names appear here.

Each gate raises ``DataQualityError`` on hard failure, or logs a warning
for soft issues that are auto-corrected.

Gates applied
-------------
Population blocks (census):
    1. Required columns present
    2. Population bounds (0 ≤ pop ≤ max)
    3. Null-pct check on key fields
    4. No duplicate GEOIDs
    5. CRS correctly set
    6. All geometries valid (auto-fixed via buffer(0) if fixable)

Facilities (any CMS type):
    1. Required columns present  (expects normalised 'supply' column)
    2. Supply > 0 (records with supply=0 dropped with warning)
    3. Null-pct check
    4. CRS correctly set
    5. All geometries valid
"""

from __future__ import annotations

import logging
from typing import Sequence

import geopandas as gpd
import pandas as pd

from pipeline.config import load_config

log = logging.getLogger(__name__)


class DataQualityError(RuntimeError):
    """Raised when a hard data-quality gate fails."""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _check_required_columns(gdf: gpd.GeoDataFrame, required: Sequence[str], label: str) -> None:
    missing = [c for c in required if c not in gdf.columns]
    if missing:
        raise DataQualityError(f"[{label}] Missing required columns: {missing}")


def _check_null_pct(gdf: gpd.GeoDataFrame, columns: Sequence[str], max_pct: float, label: str) -> None:
    for col in columns:
        if col not in gdf.columns:
            continue
        null_pct = gdf[col].isna().mean()
        if null_pct > max_pct:
            raise DataQualityError(
                f"[{label}] Column '{col}' has {null_pct:.1%} nulls (threshold={max_pct:.1%})"
            )
        if null_pct > 0:
            log.warning("[%s] Column '%s' has %.1f%% nulls", label, col, null_pct * 100)


def _fix_geometries(gdf: gpd.GeoDataFrame, label: str) -> gpd.GeoDataFrame:
    invalid_mask = ~gdf.geometry.is_valid
    n_invalid = invalid_mask.sum()
    if n_invalid > 0:
        log.warning("[%s] Fixing %d invalid geometries via buffer(0)", label, n_invalid)
        gdf = gdf.copy()
        gdf.loc[invalid_mask, "geometry"] = gdf.loc[invalid_mask, "geometry"].buffer(0)
        still_invalid = ~gdf.geometry.is_valid
        if still_invalid.any():
            raise DataQualityError(
                f"[{label}] {still_invalid.sum()} geometries remain invalid after fix"
            )
    return gdf


def _ensure_crs(gdf: gpd.GeoDataFrame, expected_crs: str, label: str) -> gpd.GeoDataFrame:
    if str(gdf.crs) != expected_crs:
        log.warning("[%s] Re-projecting from %s to %s", label, gdf.crs, expected_crs)
        gdf = gdf.to_crs(expected_crs)
    return gdf


# ── Population blocks gate ────────────────────────────────────────────────────

def validate_population(
    gdf: gpd.GeoDataFrame,
    config: dict | None = None,
) -> gpd.GeoDataFrame:
    """
    Validate census-block population GeoDataFrame.
    Returns a cleaned copy ready for the Silver layer.
    """
    if config is None:
        config = load_config()

    cfg_v = config["validation"]
    label = "population"

    log.info("[%s] Validating %d rows", label, len(gdf))

    _check_required_columns(gdf, cfg_v["required_population_columns"], label)
    _check_null_pct(gdf, ["population", "GEOID"], cfg_v["max_null_pct"], label)

    out_of_range = gdf["population"].lt(cfg_v["min_population"]) | gdf["population"].gt(cfg_v["max_population"])
    if out_of_range.any():
        log.warning("[%s] Clamping %d blocks with population outside [%d, %d]",
                    label, out_of_range.sum(), cfg_v["min_population"], cfg_v["max_population"])
        gdf = gdf.copy()
        gdf["population"] = gdf["population"].clip(cfg_v["min_population"], cfg_v["max_population"])

    dupes = gdf["GEOID"].duplicated()
    if dupes.any():
        log.warning("[%s] Dropping %d duplicate GEOIDs", label, dupes.sum())
        gdf = gdf.loc[~dupes].copy()

    gdf = _ensure_crs(gdf, config["study_area"]["coordinate_system"], label)
    gdf = _fix_geometries(gdf, label)

    log.info("[%s] Validation passed: %d clean blocks", label, len(gdf))
    return gdf.reset_index(drop=True)


# ── Facility gate ─────────────────────────────────────────────────────────────

def validate_facilities(
    gdf: gpd.GeoDataFrame,
    config: dict | None = None,
) -> gpd.GeoDataFrame:
    """
    Validate facility GeoDataFrame.

    Expects the ingest stage to have normalised the raw supply column
    to 'supply'. This gate is therefore facility-type agnostic —
    no CMS column names appear here.

    Returns a cleaned copy ready for the Silver layer.
    """
    if config is None:
        config = load_config()

    cfg_v = config["validation"]
    fac_label = config["facility"]["label"]
    label = f"facilities [{fac_label}]"

    log.info("[%s] Validating %d rows", label, len(gdf))

    # Required columns use normalised names ('supply', not e.g. 'CRTFD_BED_CNT')
    _check_required_columns(gdf, cfg_v["required_facility_columns"], label)
    _check_null_pct(gdf, ["supply"], cfg_v["max_null_pct"], label)

    no_supply = gdf["supply"].le(0)
    if no_supply.any():
        log.warning("[%s] Dropping %d facilities with supply ≤ 0", label, no_supply.sum())
        gdf = gdf.loc[~no_supply].copy()

    out_of_range = gdf["supply"].lt(cfg_v["min_supply"]) | gdf["supply"].gt(cfg_v["max_supply"])
    if out_of_range.any():
        log.warning("[%s] Clamping %d facilities with supply outside [%d, %d]",
                    label, out_of_range.sum(), cfg_v["min_supply"], cfg_v["max_supply"])
        gdf = gdf.copy()
        gdf["supply"] = gdf["supply"].clip(cfg_v["min_supply"], cfg_v["max_supply"])

    gdf = _ensure_crs(gdf, config["study_area"]["coordinate_system"], label)
    gdf = _fix_geometries(gdf, label)

    log.info("[%s] Validation passed: %d facilities", label, len(gdf))
    return gdf.reset_index(drop=True)


# ── Combined runner ────────────────────────────────────────────────────────────

def run_quality_gates(
    pop_gdf: gpd.GeoDataFrame,
    fac_gdf: gpd.GeoDataFrame,
    config: dict | None = None,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Run all quality gates. Returns (validated_pop, validated_fac)."""
    return validate_population(pop_gdf, config), validate_facilities(fac_gdf, config)
