"""
Compare accessibility scores with the CDC/ATSDR Social Vulnerability Index (SVI).

For each study, joins 2022 tract-level SVI (RPL_THEMES, the overall percentile
rank among tracts in the state, 0-1) to census blocks by tract GEOID, groups the
study's tracts into SVI quartiles, and reports accessibility by quartile.

Zero-access status depends only on whether a facility lies within the catchment,
not on the socio-economic demand weights, so the zero-access comparison is
independent of the weighting. Mean scores are not fully independent: income,
insurance and age enter the model's demand weight and also overlap SVI themes.

Run from the repository root:
    python scripts/comparison_analysis/svi_validation.py            # all studies
    python scripts/comparison_analysis/svi_validation.py dc nyc     # a subset

SVI files are downloaded once to data/reference/ from the CDC/ATSDR SVI service
(the endpoint used by https://www.atsdr.cdc.gov/place-health/php/svi/).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from scipy.spatial import cKDTree
from scipy.stats import kruskal, spearmanr

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from dashboard.map_details import DILUTED, ISOLATED, classify_bivariate  # noqa: E402
SVI_URL = "https://svi2.cdc.gov/webapi/Documents/download?year=2022&type=csv&category=states&name={state}"
SVI_MISSING = -999
QUARTILE_LABELS = ["Q1 (least vulnerable)", "Q2", "Q3", "Q4 (most vulnerable)"]


@dataclass(frozen=True)
class Study:
    prefix: str
    name: str
    facility: str
    facility_singular: str
    crs: str
    catchment_m: int
    svi_state: str
    svi_abbr: str


STUDIES = {
    "dc": Study("dc_icf", "Washington DC", "intermediate care facilities", "intermediate care facility", "EPSG:26985", 900,
                "DISTRICTOFCOLUMBIA", "DC"),
    "nyc": Study("ny_dialysis", "New York City", "dialysis centers", "dialysis center", "EPSG:32618", 1200,
                 "NEWYORK", "NY"),
    "la": Study("ca_fqhc", "City of Los Angeles", "federally qualified health centers", "federally qualified health center", "EPSG:32611", 1600,
                "CALIFORNIA", "CA"),
}


def latest(layer: str, dataset: str) -> Path:
    return sorted((REPO / "outputs" / "results" / layer).glob(f"run_date=*/{dataset}.parquet"))[-1]


def load_svi(study: Study) -> pd.DataFrame:
    path = REPO / "data" / "reference" / f"svi_2022_{study.svi_abbr}.csv"
    if not path.exists():
        response = requests.get(SVI_URL.format(state=study.svi_state), timeout=300)
        response.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
    svi = pd.read_csv(path, encoding="utf-8-sig", dtype={"FIPS": str})
    svi = svi[["FIPS", "RPL_THEMES"]].rename(columns={"FIPS": "tract"})
    return svi[svi["RPL_THEMES"] != SVI_MISSING].reset_index(drop=True)


def load_blocks(study: Study) -> gpd.GeoDataFrame:
    blocks = gpd.read_parquet(latest("gold", f"{study.prefix}_scores"))
    keep = ["GEOID", "population", "accessibility_score", "geometry"] + \
        (["in_report_area"] if "in_report_area" in blocks else [])
    blocks = blocks[keep].to_crs(study.crs)
    # Blocks with no residents (or outside the reporting area) are scored but not reported.
    reported = blocks["in_report_area"].astype(bool) if "in_report_area" in blocks else True
    blocks = blocks[(blocks["population"] > 0) & reported].copy()
    blocks["GEOID"] = blocks["GEOID"].astype(str)
    blocks["tract"] = blocks["GEOID"].str[:11]
    blocks["zero_access"] = blocks["accessibility_score"] == 0
    left_behind = classify_bivariate(blocks, study.crs)["bivariate_class"]
    blocks["isolated"] = left_behind == ISOLATED
    blocks["diluted"] = left_behind == DILUTED
    return blocks


def assign_facilities(blocks: gpd.GeoDataFrame, study: Study) -> pd.Series:
    """Tract of the nearest block centroid for each study facility."""
    facilities = gpd.read_parquet(latest("silver", f"{study.prefix}_facilities")).to_crs(study.crs)
    block_xy = np.column_stack([blocks.geometry.centroid.x, blocks.geometry.centroid.y])
    facility_xy = np.column_stack([facilities.geometry.centroid.x, facilities.geometry.centroid.y])
    nearest = cKDTree(block_xy).query(facility_xy)[1]
    return blocks["tract"].iloc[nearest].reset_index(drop=True)


def summarise(frame: pd.DataFrame) -> pd.Series:
    residents = frame["population"].sum()
    return pd.Series({
        "tracts": frame["tract"].nunique(),
        "blocks": len(frame),
        "residents": int(residents),
        "mean_score": frame["accessibility_score"].mean(),
        "median_score": frame["accessibility_score"].median(),
        "zero_access_blocks_pct": frame["zero_access"].mean() * 100,
        "zero_access_residents_pct": (
            frame.loc[frame["zero_access"], "population"].sum() / residents * 100
        ),
        "isolated_residents_pct": frame.loc[frame["isolated"], "population"].sum() / residents * 100,
        "diluted_residents_pct": frame.loc[frame["diluted"], "population"].sum() / residents * 100,
    })


def run(study: Study) -> pd.DataFrame:
    print(f"\n{'=' * 78}\n{study.name} ({study.facility}, {study.catchment_m:,} m catchment)\n{'=' * 78}")
    svi = load_svi(study)
    blocks = load_blocks(study)
    facility_tracts = assign_facilities(blocks, study)
    joined = pd.DataFrame(blocks.drop(columns="geometry")).merge(svi, on="tract", how="left")

    unmatched = joined["RPL_THEMES"].isna()
    print(f"Blocks: {len(joined):,} | matched to an SVI tract: {(~unmatched).sum():,} | excluded "
          f"(no valid SVI): {unmatched.sum():,} ({joined.loc[unmatched, 'population'].sum():,.0f} residents)")
    joined = joined[~unmatched].copy()

    # Quartiles are defined on the study's tracts so each tract counts once.
    tract_svi = joined.drop_duplicates("tract").set_index("tract")["RPL_THEMES"]
    quartile = pd.qcut(tract_svi, 4, labels=QUARTILE_LABELS)
    joined["svi_quartile"] = joined["tract"].map(quartile)

    table = joined.groupby("svi_quartile", observed=True).apply(summarise, include_groups=False)
    table["facilities"] = facility_tracts.map(quartile).value_counts().reindex(table.index).fillna(0).astype(int)
    table["facilities_per_100k_residents"] = table["facilities"] / table["residents"] * 1e5
    print("\nAccessibility by SVI quartile (quartiles of this study's tracts):")
    print(table.round(1).to_string())

    # Blocks inside a tract share one SVI value, so the tract is the honest unit.
    per_tract = joined.groupby("tract").apply(
        lambda t: pd.Series({
            "svi": t["RPL_THEMES"].iloc[0],
            "mean_score": t["accessibility_score"].mean(),
            "zero_share": t["zero_access"].mean(),
        }),
        include_groups=False,
    )
    groups = [g["accessibility_score"].to_numpy() for _, g in joined.groupby("svi_quartile", observed=True)]
    h, p_kw = kruskal(*groups)
    print(f"\nKruskal–Wallis, block scores across SVI quartiles: H = {h:.2f}, p = {p_kw:.3g}")

    print(f"\nTract level (n={len(per_tract):,}), Spearman rank correlation with SVI:")
    for column, label in [("mean_score", "mean accessibility score"),
                          ("zero_share", "share of zero-access blocks")]:
        rho, p = spearmanr(per_tract["svi"], per_tract[column])
        print(f"  SVI vs {label}: rho = {rho:+.2f}, p = {p:.3g}")

    table_path = REPO / "outputs" / "results" / f"{study.prefix}_svi_quartiles.csv"
    table_path.parent.mkdir(parents=True, exist_ok=True)
    table.round(2).to_csv(table_path)
    figure_path = plot(study, table)
    print(f"Saved: {figure_path.relative_to(REPO)} and {table_path.relative_to(REPO)}")
    return table


def plot(study: Study, table: pd.DataFrame) -> Path:
    labels = [str(q).replace(" (", "\n(") for q in table.index]
    x = np.arange(len(table))
    width = 0.38
    fig, ax = plt.subplots(figsize=(9, 5.2))
    bars_blocks = ax.bar(x - width / 2, table["zero_access_blocks_pct"], width,
                         color="#087f78", label="Census blocks with no access")
    bars_people = ax.bar(x + width / 2, table["zero_access_residents_pct"], width,
                         color="#e8833a", label="Residents in no-access blocks")
    for bars in (bars_blocks, bars_people):
        ax.bar_label(bars, fmt="%.0f%%", padding=3, fontsize=10, color="#172b3a")
    ax.set_xticks(x, labels)
    ax.set_ylabel("Share with no access (%)")
    ax.set_ylim(0, max(table["zero_access_blocks_pct"].max(), table["zero_access_residents_pct"].max()) * 1.25)
    ax.set_title(f"{study.name}: no-access rate by CDC Social Vulnerability Index quartile",
                 loc="left", fontweight="bold", fontsize=12)
    ax.text(0, -0.2,
            "SVI 2022 overall percentile (RPL_THEMES, ranked within the state); quartiles of this study's census "
            f"tracts.\nNo access = no {study.facility_singular} within the {study.catchment_m:,} m catchment.",
            transform=ax.transAxes, fontsize=8, color="#526779", va="top")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout()
    path = REPO / "outputs" / "figures" / f"{study.prefix}_svi_zero_access.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("studies", nargs="*", choices=list(STUDIES), default=list(STUDIES))
    for key in parser.parse_args().studies:
        run(STUDIES[key])


if __name__ == "__main__":
    main()
