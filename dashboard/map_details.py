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


def populated_mask(blocks: pd.DataFrame) -> pd.Series:
    """Blocks with residents inside the reporting area.

    SDW-2SFCA scores every block, including ones nobody lives in (parks, rail
    yards, airports), so study statistics count populated blocks only. Blocks
    flagged outside the study's reporting area are modelled but not reported.
    """
    populated = pd.to_numeric(blocks["population"], errors="coerce").fillna(0) > 0
    if "in_report_area" in blocks:
        populated &= blocks["in_report_area"].fillna(False).astype(bool)
    return populated


def search_blocks(geoids: pd.Series, query: str, limit: int = 50) -> list[str]:
    """Return the block GEOID matching ``query`` exactly, else GEOIDs that start with it.

    Non-digits are ignored so pasted IDs like "11001 003000 1001" still match.
    A tract (11 digits) or block group (12 digits) prefix lists its blocks.
    """
    digits = "".join(ch for ch in str(query) if ch.isdigit())
    if not digits:
        return []
    ids = geoids.astype(str)
    if (ids == digits).any():
        return [digits]
    return sorted(ids[ids.str.startswith(digits)])[:limit]


def block_zoom(
    bounds: tuple[float, float, float, float],
    target_px: float = 160.0,
    min_zoom: float = 12.0,
    max_zoom: float = 16.5,
) -> float:
    """Web-map zoom at which a lon/lat bounding box spans about ``target_px`` pixels."""
    minx, miny, maxx, maxy = bounds
    # Mercator stretches latitude by 1/cos(lat); compare both sides in equatorial degrees.
    lat = np.radians((miny + maxy) / 2)
    span = max(maxx - minx, (maxy - miny) / np.cos(lat), 1e-9)
    # MapLibre's world is 512 px wide at zoom 0.
    return float(np.clip(np.log2(target_px * 360 / (512 * span)), min_zoom, max_zoom))


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


# ── Bivariate classes (population density × accessibility) ───────────────────
# Same palette and population-weighted tertiles as the pipeline's bivariate map.
# Keys are f"{density_tier}_{access_tier}".
BIVARIATE_COLORS = {
    "low_low": "#e8e8e8", "medium_low": "#e4acac", "high_low": "#c85a5a",
    "low_medium": "#b0d5df", "medium_medium": "#ad9ea5", "high_medium": "#985356",
    "low_high": "#64acbe", "medium_high": "#627f8c", "high_high": "#574249",
}
# Named cells of the 3x3 grid: class -> (name, description). The dense column's two
# lower cells are the two ways people are left behind: isolated (no facility in
# reach, the same under any catchment method) and diluted (a facility nearby but
# its supply stretched by demand, which only a competition-aware method can see).
BIVARIATE_NAMED = {
    "high_high": ("Demand met", "Dense · high access"),
    "high_medium": ("Left behind: diluted", "Dense · facility nearby, supply stretched"),
    "high_low": ("Left behind: isolated", "Dense · no facility in reach"),
    "low_high": ("Surplus access", "Low density · high access"),
    "low_low": ("Sparse", "Low density · no access"),
}
ISOLATED, DILUTED = "high_low", "high_medium"
LEFT_BEHIND = (ISOLATED, DILUTED)


def _weighted_quantiles(values: np.ndarray, weights: np.ndarray, quantiles: list[float]) -> np.ndarray:
    """Population-weighted quantiles."""
    order = np.argsort(values)
    values, weights = values[order], weights[order]
    cumulative = (np.cumsum(weights) - 0.5 * weights) / weights.sum()
    return np.interp(quantiles, cumulative, values)


def classify_bivariate(blocks: gpd.GeoDataFrame, metric_crs: str) -> pd.DataFrame:
    """Density and access tiers for blocks with residents.

    Density is split at population-weighted tertiles, so each density tier holds
    about a third of residents. Access is "low" exactly when the score is zero
    (no facility within the catchment); blocks with some access are split at
    their population-weighted median into "medium" and "high". So the dense
    "isolated" cell always means no facility in reach, in every study.
    Returns ``density`` (residents per km²), ``density_tier``, ``access_tier``
    and ``bivariate_class``, indexed like the populated rows of ``blocks``.
    """
    populated = blocks[populated_mask(blocks)]
    if populated.empty:
        raise ValueError("No census blocks with residents to classify.")
    area_km2 = populated.to_crs(metric_crs).geometry.area.to_numpy() / 1e6
    population = populated["population"].to_numpy(float)
    density = np.divide(population, area_km2, out=np.zeros_like(population), where=area_km2 > 0)
    score = populated["accessibility_score"].to_numpy(float)

    q33, q66 = _weighted_quantiles(density, population, [1 / 3, 2 / 3])
    density_tier = np.select([density <= q33, density <= q66], ["low", "medium"], "high")

    has_access = score > 0
    median = (_weighted_quantiles(score[has_access], population[has_access], [0.5])[0]
              if has_access.any() else 0.0)
    access_tier = np.select([~has_access, score <= median], ["low", "medium"], "high")

    result = pd.DataFrame(
        {"density": density, "density_tier": density_tier, "access_tier": access_tier},
        index=populated.index,
    )
    result["bivariate_class"] = result["density_tier"] + "_" + result["access_tier"]
    return result
