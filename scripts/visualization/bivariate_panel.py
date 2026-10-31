"""
Three-city bivariate figure for slides: population density x SDW-2SFCA access.

One panel per study, each in its own frame with a scale bar (the studies are at
different scales), one overall title, and a shared 3x3 legend that names the
corners and the two left-behind cells. Classes, colours and names come from dashboard/map_details.py,
so the figure and the dashboard's "Left behind" tab use one definition.

Blocks with no residents are left white: the legend's light grey is "Sparse".

Run from the repository root:
    python scripts/visualization/bivariate_panel.py
Writes outputs/figures/bivariate_panel.png
"""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from dashboard.map_details import BIVARIATE_COLORS, BIVARIATE_NAMED, classify_bivariate  # noqa: E402
from pipeline.config import load_config  # noqa: E402

STUDIES = [("dc.yaml", "dc_icf"), ("nyc.yaml", "ny_dialysis"), ("la_fqhc.yaml", "ca_fqhc")]
TIERS = ("low", "medium", "high")
OUTPUT = REPO / "outputs" / "figures" / "bivariate_panel.png"
DPI = 300


def latest_scores(prefix: str) -> gpd.GeoDataFrame:
    path = sorted((REPO / "outputs" / "results" / "gold").glob(f"run_date=*/{prefix}_scores.parquet"))[-1]
    return gpd.read_parquet(path)


def draw_legend(ax) -> None:
    """3x3 colour grid with the named cells called out beside it."""
    n = len(TIERS)
    ax.set_xlim(-4.6, n + 4.6)
    ax.set_ylim(-1.45, n + 0.75)
    ax.set_aspect("equal")
    ax.axis("off")

    for col, x_tier in enumerate(TIERS):
        for row, y_tier in enumerate(TIERS):
            ax.add_patch(plt.Rectangle((col, row), 1, 1, facecolor=BIVARIATE_COLORS[f"{x_tier}_{y_tier}"],
                                       edgecolor="white", linewidth=2, zorder=2))

    arrow = dict(arrowstyle="-|>", color="#333333", lw=1.4)
    ax.annotate("", xy=(n, -0.2), xytext=(0, -0.2), arrowprops=arrow)
    ax.text(0, -0.36, "Low", ha="left", va="top", fontsize=10)
    ax.text(n, -0.36, "High", ha="right", va="top", fontsize=10)
    ax.text(n / 2, -0.85, "Population density", ha="center", va="top", fontsize=12, fontweight="bold")

    ax.annotate("", xy=(-0.2, n), xytext=(-0.2, 0), arrowprops=arrow)
    ax.text(-0.32, 0, "None", ha="right", va="bottom", fontsize=10)
    ax.text(-0.32, n, "High", ha="right", va="top", fontsize=10)
    # Horizontal, above the arrow, so the left-hand leader lines don't cross it.
    ax.text(-0.2, n + 0.22, "Accessibility", ha="center", va="bottom", fontsize=12, fontweight="bold")

    # Right-column cells are called out to the right of the grid, left-column ones to the left.
    for key, (title, subtitle) in BIVARIATE_NAMED.items():
        x_tier, y_tier = key.split("_")
        col, row = TIERS.index(x_tier), TIERS.index(y_tier)
        right = col == n - 1
        cy = row + 0.5
        tx = n + 0.55 if right else -1.4
        ha = "left" if right else "right"
        ax.plot([col + 0.5, n + 0.4 if right else -1.25], [cy, cy], color="#333333", lw=0.9, zorder=3)
        ax.plot(col + 0.5, cy, "o", color="white", markeredgecolor="#333333", markersize=5, zorder=4)
        ax.text(tx, cy + 0.06, title, ha=ha, va="bottom", fontsize=13, fontweight="bold")
        ax.text(tx, cy - 0.06, subtitle, ha=ha, va="top", fontsize=10.5, color="#555555")


def scale_bar(ax, fraction: float = 0.22) -> None:
    """Two-tone scale bar in the bottom-right of a metre-based map, with a
    round length close to ``fraction`` of the panel width."""
    (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
    target_km = (x1 - x0) / 1000 * fraction
    length_km = min((1, 2, 5, 10, 20, 50, 100), key=lambda v: abs(v - target_km))
    length = length_km * 1000

    right, bottom = x1 - 0.05 * (x1 - x0), y0 + 0.05 * (y1 - y0)
    height = 0.012 * (y1 - y0)
    half = length / 2
    for i, colour in enumerate(("#333333", "white")):
        ax.add_patch(plt.Rectangle((right - length + i * half, bottom), half, height,
                                   facecolor=colour, edgecolor="#333333", linewidth=0.8, zorder=6))
    for x, label in ((right - length, "0"), (right, f"{length_km:g} km")):
        ax.text(x, bottom + height * 1.8, label, ha="center", va="bottom", fontsize=9, color="#333333", zorder=6)


def main() -> None:
    panels = []
    for config_file, prefix in STUDIES:
        config = load_config(REPO / "case_studies" / config_file)
        blocks = latest_scores(prefix)
        classes = classify_bivariate(blocks, config["study_area"]["coordinate_system"])
        panels.append((config, blocks.loc[classes.index].join(classes)))

    # Width ratios follow each study area's aspect so the panels share a height.
    aspects = []
    for _, gdf in panels:
        x0, y0, x1, y1 = gdf.total_bounds
        aspects.append((x1 - x0) / (y1 - y0))

    fig = plt.figure(figsize=(18, 9.4))
    grid = fig.add_gridspec(2, len(panels), width_ratios=aspects, height_ratios=[1, 0.48],
                            wspace=0.06, hspace=0.06)
    for i, (config, gdf) in enumerate(panels):
        ax = fig.add_subplot(grid[0, i])
        for key, colour in BIVARIATE_COLORS.items():
            subset = gdf[gdf["bivariate_class"] == key]
            if len(subset):
                subset.plot(ax=ax, color=colour, linewidth=0.1, edgecolor=(1.0, 1.0, 1.0, 0.45))
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_edgecolor("#6b6b6b")
            spine.set_linewidth(0.8)
        ax.set_title(f"{config['study_area']['name']}\n{config['facility']['label']}",
                     fontsize=13, pad=8, fontweight="bold", linespacing=1.4)
        scale_bar(ax)

    legend_ax = fig.add_subplot(grid[1, :])
    draw_legend(legend_ax)
    fig.suptitle("Population Density × SDW-2SFCA Accessibility", fontsize=18, fontweight="bold", y=0.97)
    # Footnote directly under the legend (its box shrinks to fit the aspect).
    legend_ax.apply_aspect()
    fig.text(0.5, legend_ax.get_position().y0 - 0.01,
             "Density tiers are population-weighted thirds within each city. Access is none (no facility within the "
             "catchment), or the lower or upper half of blocks with access.\n"
             "Blocks with no residents are left white. Maps are not to a common scale.",
             ha="center", va="top", fontsize=10.5, color="#555555", linespacing=1.5)

    fig.savefig(OUTPUT, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"saved {OUTPUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
