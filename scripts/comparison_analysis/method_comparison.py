"""
Compare accessibility methods on identical inputs, adding one ingredient at a time.

Every method uses the pipeline's own inputs for the study — the same blocks and
population (after population_reference / empty_blocks), the same facilities and
supply, the same catchment d0, centroid distances and truncated Gaussian decay —
so differences come from the method alone:

    Cumulative opportunity   facilities within d0                      (availability)
    Gravity                  + supply, decayed with distance            (availability)
    Hansen                   supply x exp(-d / 1 km), no cutoff         (classic potential)
    E2SFCA                   + competition: demand = raw headcount      (accessibility)
    SDW-2SFCA                + demand weighted by socio-economic reliance (equity)

Gini and zero-access share count blocks with residents only, as everywhere else.

Writes outputs/results/<prefix>_method_scores.parquet (one score column per
method), prints the summary table, and draws two figures:
    outputs/figures/<prefix>_method_panel.png    four maps, one per step of the ladder
    outputs/figures/<prefix>_method_lorenz.png   Lorenz curves for all five methods

Run from the repository root:
    python scripts/comparison_analysis/method_comparison.py
    python scripts/comparison_analysis/method_comparison.py --config case_studies/nyc.yaml
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MaxNLocator
import pandas as pd
from scipy.spatial import cKDTree
from scipy.stats import spearmanr

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from dashboard.map_details import DILUTED, ISOLATED, classify_bivariate  # noqa: E402
from pipeline.config import load_config  # noqa: E402
from pipeline.ingest.census_api import ingest_census_blocks  # noqa: E402
from pipeline.ingest.cms_api import ingest_facilities  # noqa: E402
from pipeline.transform.sfca_enhanced import _truncated_gaussian, run_enhanced_transform  # noqa: E402
from pipeline.validate.quality_gates import run_quality_gates  # noqa: E402
from pipeline.visualize import NO_RESIDENTS_COLOR, _gini, _projected_ticks  # noqa: E402

HANSEN_DECAY_M = 1000.0  # exp(-d / 1 km), as in the original Hansen script (alpha = 0.001 per m)
PREFIXES = {"dc.yaml": "dc_icf", "nyc.yaml": "ny_dialysis", "la_fqhc.yaml": "ca_fqhc"}
# Map panel: the ladder, one ingredient added per step
PANEL = [
    ("Cumulative opportunity", "Facilities nearby"),
    ("Gravity", "+ facility size, distance decay"),
    ("E2SFCA", "+ competition for supply"),
    ("SDW-2SFCA", "+ socio-demographic demand weighting (this study)"),
]
LORENZ_STYLE = {
    "Cumulative opportunity": ("#9972af", ":"),
    "Gravity": ("#c85a5a", "-."),
    "Hansen": ("#c8b35a", (0, (5, 2, 1, 2))),
    "E2SFCA": ("#64acbe", "--"),
    "SDW-2SFCA": ("#2f7488", "-"),
}
FIGURES = REPO / "outputs" / "figures"


def method_scores(blocks, facilities, d0: float) -> pd.DataFrame:
    """Scores for every method except SDW-2SFCA, one column each."""
    b = np.column_stack([blocks.geometry.centroid.x, blocks.geometry.centroid.y])
    s = np.column_stack([facilities.geometry.centroid.x, facilities.geometry.centroid.y])
    supply = facilities["supply"].fillna(0).to_numpy(float)
    pop = blocks["population"].to_numpy(float)

    # Block x facility distances within d0, as a sparse matrix.
    pairs = cKDTree(b).sparse_distance_matrix(cKDTree(s), d0, output_type="coo_matrix").tocsr()
    pairs.eliminate_zeros()
    within = pairs.copy()
    within.data = np.ones_like(within.data)
    # Blocks whose centroid sits exactly on a facility have distance 0, which the sparse
    # matrix drops; restore them with full weight.
    exact = cKDTree(b).query_ball_tree(cKDTree(s), 1e-6)
    rows = [i for i, hits in enumerate(exact) for _ in hits]
    cols = [j for hits in exact for j in hits]

    decay = pairs.copy()
    decay.data = _truncated_gaussian(decay.data, d0)
    if rows:
        from scipy.sparse import csr_matrix
        on_top = csr_matrix((np.ones(len(rows)), (rows, cols)), shape=decay.shape)
        decay = decay + on_top
        within = within + on_top

    cumulative = np.asarray(within.sum(axis=1)).ravel()
    gravity = decay @ supply

    dist_all = np.linalg.norm(b[:, None, :] - s[None, :, :], axis=2)
    hansen = np.exp(-dist_all / HANSEN_DECAY_M) @ supply

    demand = decay.T @ pop                       # raw headcount within each catchment
    ratio = np.divide(supply, demand, out=np.zeros_like(supply), where=demand > 0)
    e2sfca = decay @ ratio

    return pd.DataFrame({
        "Cumulative opportunity": cumulative,
        "Gravity": gravity,
        "Hansen": hansen,
        "E2SFCA": e2sfca,
    }, index=blocks.index)


def plot_panel(blocks, facilities, scores: pd.DataFrame, config: dict, path: Path) -> None:
    """2x2 maps, one per ladder step; colours scaled within each method."""
    populated = scores["population"].to_numpy() > 0
    # Full red-yellow-blue ramp: no or low access reads as deep red, as in the original comparison.
    cmap = plt.get_cmap(config["visualization"]["colormap"])
    # Every panel shows the same extent, so axes are shared and labelled on the outer edges only.
    fig, axes = plt.subplots(2, 2, figsize=(10.6, 13.4), sharex=True, sharey=True,
                             gridspec_kw={"wspace": 0.06, "hspace": 0.24})
    for ax, (method, subtitle) in zip(axes.flat, PANEL):
        values = scores[method].to_numpy()
        shown = blocks.assign(score=values)[populated]
        vmax = float(np.percentile(values[populated & (values > 0)], 95))
        shown.plot(column="score", cmap=cmap, vmin=0, vmax=vmax, linewidth=0.08,
                   edgecolor=(1, 1, 1, 0.45), ax=ax)
        blocks[~populated].plot(ax=ax, color=NO_RESIDENTS_COLOR, linewidth=0.08, edgecolor=(1, 1, 1, 0.45))
        facilities.plot(ax=ax, color="#1f2a6b", marker="*", markersize=10, zorder=5)
        v = values[populated]
        ax.set_title(f"{method}\n{subtitle}\nGini {_gini(v):.2f}  ·  zero access {(v == 0).mean():.0%}",
                     fontsize=12, linespacing=1.5,
                     fontweight="bold" if method == "SDW-2SFCA" else "normal")
        _projected_ticks(ax, blocks.crs)
        ax.xaxis.set_major_locator(MaxNLocator(4))
        ax.yaxis.set_major_locator(MaxNLocator(5))
        ax.tick_params(labelsize=8)
        ax.xaxis.label.set_size(10)
        ax.yaxis.label.set_size(10)
        for spine in ax.spines.values():
            spine.set_edgecolor("#6b6b6b")
            spine.set_linewidth(0.8)
    for ax in axes[0]:          # top row: no x labels
        ax.set_xlabel("")
        ax.tick_params(labelbottom=False)
    for ax in axes[:, 1]:       # right column: no y labels
        ax.set_ylabel("")
        ax.tick_params(labelleft=False)
    fig.text(0.5, 0.035,
             "Same blocks, facilities and catchment in every panel; each step adds one ingredient. "
             "Colours run from low (red) to high (blue) within each method, capped at its 95th percentile. "
             "Grey blocks have no residents.",
             ha="center", fontsize=9.5, color="#555555", wrap=True)
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"saved {path.relative_to(REPO)}")


def plot_lorenz(scores: pd.DataFrame, config: dict, path: Path) -> None:
    """Lorenz curves over blocks with residents, each block counted equally."""
    populated = scores[scores["population"] > 0]
    fig, ax = plt.subplots(figsize=(9, 7.5))
    ax.plot([0, 1], [0, 1], color="#555555", linewidth=1, linestyle="--", label="Equality line")
    for method, (colour, dash) in LORENZ_STYLE.items():
        x = np.sort(populated[method].to_numpy(float))
        share = np.r_[0, np.cumsum(x) / x.sum()]
        ax.plot(np.linspace(0, 1, len(share)), share, color=colour, linestyle=dash,
                linewidth=2.8 if method == "SDW-2SFCA" else 2,
                label=f"{method} (Gini {_gini(x):.2f})")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    ax.grid(color="#e3e6ea", linewidth=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_xlabel("Cumulative share of census blocks with residents (lowest to highest access)", fontsize=11)
    ax.set_ylabel("Cumulative share of accessibility", fontsize=11)
    ax.set_title(f"Lorenz Curves by Accessibility Method\n{config['facility']['label']} | "
                 f"{config['study_area']['name']} ({len(populated):,} blocks with residents)", fontsize=13, pad=12)
    ax.legend(loc="upper left", fontsize=10, frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"saved {path.relative_to(REPO)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="case_studies/dc.yaml")
    args = parser.parse_args()
    logging.disable(logging.INFO)

    config = load_config(REPO / args.config)
    d0 = float(config["analysis"]["distance_threshold_m"])
    blocks, facilities = run_quality_gates(ingest_census_blocks(config), ingest_facilities(config), config)

    scores = method_scores(blocks, facilities, d0)
    scores["SDW-2SFCA"] = run_enhanced_transform(blocks, facilities, config)["accessibility_score"].to_numpy()
    scores.insert(0, "population", blocks["population"].to_numpy())
    scores.insert(0, "GEOID", blocks["GEOID"].astype(str).to_numpy())

    populated = scores[scores["population"] > 0]
    methods = [c for c in scores.columns if c not in ("GEOID", "population")]
    print(f"{config['study_area']['name']}: {len(populated):,} blocks with residents, d0 = {d0:,.0f} m")
    print(f"{'Method':24s} {'Gini':>7s} {'Zero access':>12s} {'Rank corr. with SDW':>20s}")
    for m in methods:
        v = populated[m].to_numpy()
        rho = spearmanr(v, populated["SDW-2SFCA"]).statistic
        print(f"{m:24s} {_gini(v):7.4f} {(v == 0).mean() * 100:11.1f}% {rho:20.3f}")

    # Who each method flags as left behind. Isolated blocks (no facility in reach) are
    # the same for every method with a cutoff; diluted blocks need a model of competition.
    crs = config["study_area"]["coordinate_system"]
    flagged = {}
    for m in methods:
        classes = classify_bivariate(blocks.assign(accessibility_score=scores[m].to_numpy()), crs)
        flagged[m] = {k: set(classes.index[classes["bivariate_class"] == k]) for k in (ISOLATED, DILUTED)}
    pop = blocks["population"]
    sdw = flagged["SDW-2SFCA"]
    print(f"\nLeft behind compared with SDW-2SFCA (residents):")
    print(f"{'Method':24s} {'Isolated':>10s} {'Diluted':>10s} {'SDW diluted it misses':>22s}")
    for m in methods:
        missed = sdw[DILUTED] - flagged[m][DILUTED]
        print(f"{m:24s} {int(pop[list(flagged[m][ISOLATED])].sum()):10,} {int(pop[list(flagged[m][DILUTED])].sum()):10,} "
              f"{int(pop[list(missed)].sum()):22,}")

    prefix = PREFIXES.get(Path(args.config).name, Path(args.config).stem)
    out = REPO / "outputs" / "results" / f"{prefix}_method_scores.parquet"
    scores.to_parquet(out, index=False)
    print(f"saved {out.relative_to(REPO)}")

    facilities = facilities.to_crs(blocks.crs)
    plot_panel(blocks, facilities, scores, config, FIGURES / f"{prefix}_method_panel.png")
    plot_lorenz(scores, config, FIGURES / f"{prefix}_method_lorenz.png")


if __name__ == "__main__":
    main()
