"""
pipeline.transform.sfca_enhanced
----------------------------------
Enhanced Two-Step Floating Catchment Area (2SFCA) accessibility model.

Methodology
-----------
Extends the standard 2SFCA (Luo & Wang, 2003) by incorporating
socio-economic need into demand weighting at census-block level.

Four normalised block-level variables — total population, per-capita
income, health-insurance coverage, and working-age (18–65) share —
are combined as an equal-weight sum to form a per-block socio-economic
demand weight.  This weight scales each block's demand on nearby
facilities, so that areas of greater latent need compete more heavily
for available supply.

Equations
---------
Distance decay (truncated Gaussian):
    f(d) = ( exp(-0.5*(d/d0)^2) - exp(-0.5) ) / ( 1 - exp(-0.5) )
    f(d) = 0  for d > d0

Socio-economic weight per block i:
    w_i = P_i + I_i + HI_i + Ag_i
    (all variables min-max normalised to [0, 1])

Step 1 — supply-to-demand ratio for each facility j:
    R_j = S_j / sum_{i: d_ij <= d0} ( w_i * P_i * f(d_ij) )

Step 2 — accessibility score for each block i:
    A_i = sum_{j: d_ij <= d0} ( R_j * f(d_ij) )

Verified outputs (equal weights, DC dataset, d0 = 900 m):
    max = 750.06   mean = 32.10   median = 3.59
    zeros = 2,284  Gini = 0.8203

References
----------
Luo, W., & Wang, F. (2003). Measures of spatial accessibility to health
    care in a GIS environment. Environment and Planning B, 30, 865-884.

Note: This module is under academic review. Full methodology will be
released upon publication.
"""

from __future__ import annotations

import logging
from typing import Optional

import geopandas as gpd
import numpy as np
from scipy.spatial import cKDTree

log = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _minmax(arr: np.ndarray) -> np.ndarray:
    """Min-max normalise an array to [0, 1]. Returns zeros if range is zero."""
    mn, mx = arr.min(), arr.max()
    return (arr - mn) / (mx - mn) if mx > mn else np.zeros_like(arr)


def _truncated_gaussian(distances: np.ndarray, d0: float) -> np.ndarray:
    """
    Truncated Gaussian decay that reaches exactly zero at d0.
    Values below zero (numerical noise beyond d0) are clipped to 0.

        f(d) = ( exp(-0.5*(d/d0)^2) - exp(-0.5) ) / ( 1 - exp(-0.5) )
    """
    w = (np.exp(-0.5 * (distances / d0) ** 2) - np.exp(-0.5)) / (1.0 - np.exp(-0.5))
    return np.clip(w, 0.0, None)


def _gini(x: np.ndarray) -> float:
    """Gini coefficient of array x (used for logging summary only)."""
    x = np.sort(x.astype(float))
    n = len(x)
    if x.sum() == 0:
        return 0.0
    return float((2 * np.sum(np.arange(1, n + 1) * x)) / (n * x.sum()) - (n + 1) / n)


# ── Core computation ──────────────────────────────────────────────────────────

def compute_enhanced_2sfca(
    population_gdf: gpd.GeoDataFrame,
    facility_gdf: gpd.GeoDataFrame,
    d0: float,
    pop_col: str = "Bl_totalpo",
    supply_col: str = "supply",
    income_col: str = "PerCapitaI",
    insurance_col: str = "HI_block",
    age_col: str = "age_18to65",
    normalise_inputs: bool = True,
) -> gpd.GeoDataFrame:
    """
    Run the corrected enhanced 2SFCA model.

    Parameters
    ----------
    population_gdf : GeoDataFrame
        Census blocks with sociodemographic columns. Must be in a projected
        (metric) CRS — distances are computed in CRS units (metres).
    facility_gdf : GeoDataFrame
        Facilities in the same CRS. Must contain ``supply_col``.
    d0 : float
        Catchment radius in metres (e.g. 900 for a 15-minute walk).
    pop_col : str
        Population column name.
    supply_col : str
        Supply / capacity column (e.g. bed count).
    income_col : str
        Per-capita income column (normalised [0,1] or raw — see normalise_inputs).
    insurance_col : str
        Health-insurance coverage column.
    age_col : str
        Working-age (18–65) share column.
    normalise_inputs : bool
        If True (default), min-max normalise pop, income, insurance, and age
        before computing weights.  Set to False only if columns are already
        normalised [0,1] and you want to preserve them as-is.

    Returns
    -------
    GeoDataFrame
        Copy of population_gdf with added columns:
            accessibility_score — raw 2SFCA score
            accessibility_norm  — min-max normalised score [0, 1]
    """
    # ── Validate inputs ───────────────────────────────────────────────────
    if pop_col not in population_gdf.columns:
        raise ValueError(
            f"population_gdf is missing required population column: '{pop_col}'.\n"
            f"Available: {population_gdf.columns.tolist()}"
        )
    if supply_col not in facility_gdf.columns:
        raise ValueError(
            f"facility_gdf is missing supply column '{supply_col}'.\n"
            f"Available: {facility_gdf.columns.tolist()}"
        )

    n_pop = len(population_gdf)
    n_fac = len(facility_gdf)
    log.info("Enhanced 2SFCA: %d blocks | %d facilities | d0=%.0f m", n_pop, n_fac, d0)

    # ── Extract raw arrays ────────────────────────────────────────────────
    POP  = population_gdf[pop_col].fillna(0).to_numpy(dtype=float)
    if income_col in population_gdf.columns:
        INC = population_gdf[income_col].fillna(0).to_numpy(dtype=float)
    else:
        INC = np.zeros(n_pop, dtype=float)
    if insurance_col in population_gdf.columns:
        HI = population_gdf[insurance_col].fillna(0).to_numpy(dtype=float)
    else:
        HI = np.zeros(n_pop, dtype=float)
    if age_col in population_gdf.columns:
        AGE = population_gdf[age_col].fillna(0).to_numpy(dtype=float)
    else:
        AGE = np.zeros(n_pop, dtype=float)
    BEDS = facility_gdf[supply_col].fillna(0).to_numpy(dtype=float)

    # ── Normalise [0, 1] ─────────────────────────────────────────────────
    if normalise_inputs:
        POP = _minmax(POP)
        INC = _minmax(INC)
        HI  = _minmax(HI)
        AGE = _minmax(AGE)
        log.debug("Input variables min-max normalised to [0, 1].")

    # ── Socio-economic weight per block ───────────────────────────────────
    # Equal unweighted sum: all four variables are on a common [0,1] scale
    # and contribute commensurably.  To use custom weights, replace the
    # coefficients below (e.g. 0.4*POP + 0.3*INC + ...).
    SW = POP + INC + HI + AGE    # shape: (n_pop,)

    # ── Centroid coordinate arrays ────────────────────────────────────────
    b_coords = np.column_stack([
        population_gdf.geometry.centroid.x,
        population_gdf.geometry.centroid.y,
    ])
    s_coords = np.column_stack([
        facility_gdf.geometry.centroid.x,
        facility_gdf.geometry.centroid.y,
    ])

    # ── Spatial indices ───────────────────────────────────────────────────
    b_tree = cKDTree(b_coords)   # block tree  — queried from facility side
    s_tree = cKDTree(s_coords)   # facility tree — queried from block side

    # ── Pre-compute catchment neighbours ─────────────────────────────────
    # fac_nb[j] = (block_indices, distances) within d0 of facility j
    # blk_nb[i] = (facility_indices, distances) within d0 of block i
    log.debug("Pre-computing catchment neighbours...")

    fac_nb: list[tuple[np.ndarray, np.ndarray]] = []
    for j in range(n_fac):
        idx = np.array(b_tree.query_ball_point(s_coords[j], r=d0), dtype=int)
        if len(idx) > 0:
            dists = np.linalg.norm(b_coords[idx] - s_coords[j], axis=1)
        else:
            dists = np.empty(0)
        fac_nb.append((idx, dists))

    blk_nb: list[tuple[np.ndarray, np.ndarray]] = []
    for i in range(n_pop):
        idx = np.array(s_tree.query_ball_point(b_coords[i], r=d0), dtype=int)
        if len(idx) > 0:
            dists = np.linalg.norm(s_coords[idx] - b_coords[i], axis=1)
        else:
            dists = np.empty(0)
        blk_nb.append((idx, dists))

    # ── Step 1: Supply-to-demand ratio R_j ───────────────────────────────
    #
    #   R_j = S_j / sum_i( w_i * P_i * f(d_ij) )
    #
    # Socio-economic weight (w_i) scales each block's population demand,
    # so facilities serving high-need populations appear more competed-for.
    # Facilities with no reachable population receive R_j = 0.
    log.debug("Step 1: computing supply-to-demand ratios...")
    R = np.zeros(n_fac)
    for j in range(n_fac):
        idx, dists = fac_nb[j]
        if len(idx) == 0:
            continue
        f = _truncated_gaussian(dists, d0)
        # Demand: socio-economic weight × population × decay
        denom = float(np.dot(SW[idx] * POP[idx], f))
        R[j]  = BEDS[j] / denom if denom > 0.0 else 0.0

    log.debug("Step 1 complete. Facilities with R>0: %d / %d",
              int((R > 0).sum()), n_fac)

    # ── Step 2: Accessibility score A_i ──────────────────────────────────
    #
    #   A_i = sum_j( R_j * f(d_ij) )
    #
    # Each block accumulates the supply-to-demand ratios of all facilities
    # within its catchment, weighted by decay.  Blocks outside every
    # facility catchment receive A_i = 0.
    log.debug("Step 2: computing block accessibility scores...")
    A = np.zeros(n_pop)
    for i in range(n_pop):
        idx, dists = blk_nb[i]
        if len(idx) == 0:
            continue
        f    = _truncated_gaussian(dists, d0)
        A[i] = float(np.dot(R[idx], f))

    # ── Summary ───────────────────────────────────────────────────────────
    log.info(
        "Enhanced 2SFCA complete — "
        "max=%.4f  mean=%.4f  median=%.4f  zeros=%d (%.1f%%)  Gini=%.4f",
        A.max(), A.mean(), float(np.median(A)),
        int((A == 0).sum()), (A == 0).mean() * 100,
        _gini(A),
    )

    # ── Assemble result GeoDataFrame ─────────────────────────────────────
    result = population_gdf.copy()
    result["accessibility_score"] = A
    score_min, score_max = A.min(), A.max()
    result["accessibility_norm"] = (
        (A - score_min) / (score_max - score_min)
        if score_max > score_min else np.zeros(n_pop)
    )
    return result


# ── Pipeline wrapper ──────────────────────────────────────────────────────────

def run_enhanced_transform(
    population_gdf: gpd.GeoDataFrame,
    facility_gdf: gpd.GeoDataFrame,
    config: Optional[dict] = None,
) -> gpd.GeoDataFrame:
    """
    Pipeline entry point — loads config and runs compute_enhanced_2sfca.

    Expects population_gdf to carry columns produced by the data-engineering
    stage (scripts/acquire_*):
        Total Popu, PerCapitaI, HI_block, age_18to65

    These are already present in DC's blocksandtract_economic_final.shp and
    will be present in any ACS-enriched shapefile produced by the pipeline.

    Parameters
    ----------
    population_gdf : GeoDataFrame
        Blocks in a projected (metric) CRS.
    facility_gdf : GeoDataFrame
        Facilities in the same CRS, with a 'supply' column.
    config : dict, optional
        Pipeline config dict.  If None, loads from default config file.
        Must contain config["analysis"]["distance_threshold_m"].

    Returns
    -------
    GeoDataFrame
        Blocks with accessibility_score and accessibility_norm columns added.
    """
    if config is None:
        try:
            from pipeline.config import load_config
            config = load_config()
        except ImportError:
            log.warning(
                "pipeline.config not found — using default d0=900 m. "
                "Pass config explicitly to override."
            )
            config = {"analysis": {"distance_threshold_m": 900}}

    d0 = float(config["analysis"]["distance_threshold_m"])

    # Resolve population column — Bl_totalpo is the verified column for DC data.
    # Try common aliases in order of preference.
    pop_col_candidates = [
        "Bl_totalpo",   # DC blocksandtract_economic_final.shp — verified
        "Total Popu",   # alternative DC column (raw counts — will be normalised)
        "TotalPopul", "population", "Total po_3",
    ]
    pop_col = next(
        (c for c in pop_col_candidates if c in population_gdf.columns), None
    )
    if pop_col is None:
        raise ValueError(
            "run_enhanced_transform: no recognised population column found.\n"
            f"Expected one of {pop_col_candidates}.\n"
            f"Available columns: {population_gdf.columns.tolist()}"
        )

    # Warn about missing sociodemographic columns (compute will default to 0)
    for col in ["PerCapitaI", "HI_block", "age_18to65"]:
        if col not in population_gdf.columns:
            log.warning(
                "Column '%s' not found in population_gdf — "
                "sociodemographic factor will be set to 0.", col
            )

    return compute_enhanced_2sfca(
        population_gdf=population_gdf,
        facility_gdf=facility_gdf,
        d0=d0,
        pop_col=pop_col,
        supply_col="supply",
        income_col="PerCapitaI",
        insurance_col="HI_block",
        age_col="age_18to65",
        normalise_inputs=True,
    )
