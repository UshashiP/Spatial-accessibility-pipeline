"""
pipeline.transform.sfca_2
--------------------------
Standard Two-Step Floating Catchment Area (2SFCA) accessibility model.

Algorithm (Luo & Wang 2003, with optional Gaussian distance-decay)
------------------------------------------------------------------
Step 1 – Supply ratio at each facility j:

        R_j = S_j / Σ_{i : d_ij ≤ d₀} P_i · W(d_ij)

    where
        S_j   = supply at facility j  (normalised column: 'supply')
        P_i   = population at block i
        d_ij  = Euclidean distance from population centroid i to facility j
        d₀    = catchment-radius threshold (metres)
        W(d)  = Gaussian decay weight = exp(−(d/d₀)²)

Step 2 – Accessibility score at each population block i:

        A_i = Σ_{j : d_ij ≤ d₀} R_j · W(d_ij)

Implementation notes
--------------------
* scipy cKDTree used for threshold queries — O(N·k) instead of O(N·M).
* Supply column is always 'supply' (normalised by ingest stage) so this
  module is fully facility-type agnostic.
* Result GeoDataFrame retains all input columns and adds:
      - accessibility_score  (float, units: supply / person)
      - accessibility_norm   (float, min-max normalised 0–1)
"""

from __future__ import annotations

import logging

import geopandas as gpd
import numpy as np
from scipy.spatial import cKDTree

from pipeline.config import load_config

log = logging.getLogger(__name__)


# ── Distance-decay weights ────────────────────────────────────────────────────

def _gaussian_weight(distances: np.ndarray, d0: float) -> np.ndarray:
    return np.exp(-((distances / d0) ** 2))


def _binary_weight(distances: np.ndarray, d0: float) -> np.ndarray:  # noqa: ARG001
    return np.ones_like(distances, dtype=float)


_DECAY_FUNCTIONS = {
    "gaussian": _gaussian_weight,
    "binary":   _binary_weight,
}


# ── Core 2SFCA ────────────────────────────────────────────────────────────────

def compute_2sfca(
    population_gdf: gpd.GeoDataFrame,
    facility_gdf: gpd.GeoDataFrame,
    d0: float,
    decay: str = "gaussian",
    pop_col: str = "population",
    supply_col: str = "supply",
) -> gpd.GeoDataFrame:
    """
    Run the standard 2SFCA model.

    Parameters
    ----------
    population_gdf : GeoDataFrame
        Census blocks in a projected CRS (metres).
    facility_gdf : GeoDataFrame
        Facilities sharing the same CRS. Supply column must be 'supply'
        (normalised by ingest stage).
    d0 : float
        Catchment radius (metres).
    decay : str
        'gaussian' (default) or 'binary'.
    pop_col : str
        Population column name (default: 'population').
    supply_col : str
        Supply column name (default: 'supply' — normalised by ingest).

    Returns
    -------
    GeoDataFrame
        Copy of population_gdf with added columns:
            accessibility_score, accessibility_norm
    """
    if decay not in _DECAY_FUNCTIONS:
        raise ValueError(f"Unknown decay '{decay}'. Choose from {list(_DECAY_FUNCTIONS)}")

    weight_fn = _DECAY_FUNCTIONS[decay]

    pop_centroids = np.column_stack(
        [population_gdf.geometry.centroid.x, population_gdf.geometry.centroid.y]
    )
    fac_coords = np.column_stack(
        [facility_gdf.geometry.centroid.x, facility_gdf.geometry.centroid.y]
    )

    population = population_gdf[pop_col].to_numpy(dtype=float)
    supply = facility_gdf[supply_col].to_numpy(dtype=float)
    n_pop, n_fac = len(pop_centroids), len(fac_coords)

    log.info("2SFCA: %d population blocks, %d facilities, d0=%.0fm, decay=%s",
             n_pop, n_fac, d0, decay)

    pop_tree = cKDTree(pop_centroids)
    fac_tree = cKDTree(fac_coords)

    # Step 1: supply ratios
    supply_ratios = np.zeros(n_fac)
    for j in range(n_fac):
        pop_idx = np.array(pop_tree.query_ball_point(fac_coords[j], r=d0))
        if len(pop_idx) == 0:
            continue
        dists = np.linalg.norm(pop_centroids[pop_idx] - fac_coords[j], axis=1)
        weighted_pop = np.dot(population[pop_idx], weight_fn(dists, d0))
        supply_ratios[j] = supply[j] / weighted_pop if weighted_pop > 0 else 0.0

    log.debug("Step 1 complete: supply ratios for %d facilities", n_fac)

    # Step 2: accessibility scores
    accessibility = np.zeros(n_pop)
    for i in range(n_pop):
        fac_idx = np.array(fac_tree.query_ball_point(pop_centroids[i], r=d0))
        if len(fac_idx) == 0:
            continue
        dists = np.linalg.norm(fac_coords[fac_idx] - pop_centroids[i], axis=1)
        accessibility[i] = np.dot(supply_ratios[fac_idx], weight_fn(dists, d0))

    log.debug("Step 2 complete: accessibility scores for %d blocks", n_pop)

    result = population_gdf.copy()
    result["accessibility_score"] = accessibility

    score_min, score_max = accessibility.min(), accessibility.max()
    if score_max > score_min:
        result["accessibility_norm"] = (accessibility - score_min) / (score_max - score_min)
    else:
        result["accessibility_norm"] = 0.0

    log.info("2SFCA complete — range [%.6f, %.6f], mean=%.6f",
             score_min, score_max, accessibility.mean())
    return result


# ── Pipeline-callable wrapper ─────────────────────────────────────────────────

def run_transform(
    population_gdf: gpd.GeoDataFrame,
    facility_gdf: gpd.GeoDataFrame,
    config: dict | None = None,
) -> gpd.GeoDataFrame:
    """
    Run the standard 2SFCA transform stage using settings from config.

    Reads distance threshold, decay function, and column names from config.
    Supply column is always 'supply' (normalised by ingest stage).

    Parameters
    ----------
    population_gdf : GeoDataFrame
        Validated Silver-layer population blocks.
    facility_gdf : GeoDataFrame
        Validated Silver-layer facilities (supply column = 'supply').
    config : dict, optional
        Pipeline config. Loaded automatically if omitted.

    Returns
    -------
    GeoDataFrame
        Gold-layer result ready for storage.
    """
    if config is None:
        config = load_config()

    cfg_a = config["analysis"]
    return compute_2sfca(
        population_gdf=population_gdf,
        facility_gdf=facility_gdf,
        d0=float(cfg_a["distance_threshold_m"]),
        decay=cfg_a["decay_function"],
        pop_col=cfg_a["population_column"],
        supply_col="supply",   # always normalised — never read raw CMS column here
    )
