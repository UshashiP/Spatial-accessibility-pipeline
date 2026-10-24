"""Block-level facility proximity details for the dashboard."""

from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import CRS
from scipy.spatial import cKDTree


@dataclass(frozen=True)
class MapColorScale:
    values: np.ndarray
    upper: float
    ticks: list[float]
    labels: list[str]
    capped: bool


def build_color_scale(scores: np.ndarray, logarithmic: bool = False) -> MapColorScale:
    """Prepare display-only colors and raw-score legend labels, preserving zeros."""
    values = np.asarray(scores, dtype=float)
    if values.size == 0 or not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("Map scores must be non-empty, finite, and non-negative.")
    maximum = float(values.max())
    if maximum == 0:
        return MapColorScale(values.copy(), 1.0, [0.0], ["0"], False)

    if logarithmic:
        # log1p includes zero without replacing it with an arbitrary positive score.
        minimum_positive = float(values[values > 0].min())
        raw_ticks = np.unique(np.concatenate([
            [0.0], np.clip(
                np.geomspace(minimum_positive, maximum, 5), minimum_positive, maximum
            )
        ]))
        return MapColorScale(
            np.log1p(values), float(np.log1p(maximum)),
            np.log1p(raw_ticks).tolist(),
            [f"{value:,.5g}" for value in raw_ticks], False,
        )

    upper = float(np.percentile(values, 95))
    # When at least 95% of blocks have zero access, use the full range.
    if upper == 0:
        upper = maximum
    raw_ticks = np.linspace(0, upper, 5)
    labels = [f"{value:,.5g}" for value in raw_ticks]
    capped = maximum > upper
    if capped:
        labels[-1] += "+"
    return MapColorScale(values.copy(), upper, raw_ticks.tolist(), labels, capped)


def build_block_details(
    blocks: gpd.GeoDataFrame,
    facilities: gpd.GeoDataFrame,
    metric_crs: str,
    catchment_m: float,
) -> gpd.GeoDataFrame:
    """Add centroid-based proximity measures without changing source scores."""
    if not np.isfinite(catchment_m) or catchment_m <= 0:
        raise ValueError("Catchment radius must be a positive, finite number of metres.")
    crs = CRS.from_user_input(metric_crs)
    if not crs.is_projected or any(axis.unit_name != "metre" for axis in crs.axis_info):
        raise ValueError("Facility distances require a projected CRS in metres.")
    if "GEOID" not in blocks or blocks["GEOID"].isna().any():
        raise ValueError("Census Block GEOID is required for every block.")
    if not blocks["GEOID"].is_unique:
        raise ValueError("Census Block GEOIDs must be unique.")
    if blocks.crs is None or (blocks.geometry.isna() | blocks.geometry.is_empty).any():
        raise ValueError("Blocks require a CRS and non-empty geometries.")

    result = blocks.copy()
    result["GEOID"] = result["GEOID"].astype(str)
    result["nearby_facilities"] = pd.array([pd.NA] * len(result), dtype="Int64")
    result["nearest_facility_m"] = np.nan
    if facilities.empty or blocks.empty:
        return result
    if facilities.crs is None or (facilities.geometry.isna() | facilities.geometry.is_empty).any():
        raise ValueError("Facilities require a CRS and non-empty geometries.")

    block_centroids = blocks.to_crs(crs).geometry.centroid
    facility_centroids = facilities.to_crs(crs).geometry.centroid
    block_coords = np.column_stack([block_centroids.x, block_centroids.y])
    facility_coords = np.column_stack([facility_centroids.x, facility_centroids.y])
    if not np.isfinite(block_coords).all() or not np.isfinite(facility_coords).all():
        raise ValueError("Block and facility centroid coordinates must be finite.")

    tree = cKDTree(facility_coords)
    result["nearby_facilities"] = tree.query_ball_point(
        block_coords, r=catchment_m, return_length=True
    )
    result["nearest_facility_m"] = tree.query(block_coords, k=1)[0]
    return result
