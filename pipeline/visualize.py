"""
pipeline.visualize
-------------------
Generates the full visualization suite for 2SFCA accessibility results.
Visual style matches original research outputs — block boundaries visible,
RdYlBu colormap, clean professional appearance.

Outputs
-------
1. accessibility_map        — choropleth with block boundaries + facility overlay
2. lorenz_curve             — accessibility inequality + Gini coefficient
3. bivariate_map            — population density × accessibility (3×3 classification)
4. access_gap_chart         — cumulative zero-access population by block
5. interactive_map          — Folium HTML map
"""

from __future__ import annotations

import logging
from logging import config
from pathlib import Path

import geopandas as gpd
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize, BoundaryNorm
from mpl_toolkits.axes_grid1 import make_axes_locatable

from pipeline.config import load_config

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Fill for blocks with no residents, so they read as neither served nor underserved.
NO_RESIDENTS_COLOR = "#dcdcdc"

import matplotlib
matplotlib.use("Agg")


# ── Shared helpers ────────────────────────────────────────────────────────────

def _fig_dir(config: dict) -> Path:
    d = _REPO_ROOT / config["data"]["output"]["figures"]
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fname(config: dict, suffix: str) -> Path:
    state = config["study_area"]["state_abbrev"].lower()
    ftype = config["facility"]["type"].lower()
    fmt   = config.get("visualization", {}).get("save_format", "png")
    return _fig_dir(config) / f"{state}_{ftype}_{suffix}.{fmt}"


def _base_cfg(config: dict) -> dict:
    cfg = config.get("visualization", {})
    return {
        "dpi":     cfg.get("figure_dpi", 300),
        "figsize": cfg.get("figure_size", [12, 10]),
        "cmap":    cfg.get("colormap", "RdYlBu"),
    }


def _gini(values: np.ndarray, weights: np.ndarray | None = None) -> float:
    """Unweighted Gini coefficient treating each block equally (matches paper)."""
    x = np.sort(values.astype(float))
    n = len(x)
    if x.sum() == 0:
        return 0.0
    return float((2 * np.sum(np.arange(1, n + 1) * x)) / (n * x.sum()) - (n + 1) / n)


def _method_label(config: dict) -> str:
    """Return method label from config or default."""
    return config.get("analysis", {}).get("method_label", "2SFCA")


def _softened_cmap(name: str, low_cut: float = 0.22, n: int = 256):
    """Return a truncated colormap with a lighter low-end ramp."""
    base = plt.get_cmap(name)
    colors = base(np.linspace(low_cut, 1.0, n))
    return mcolors.LinearSegmentedColormap.from_list(f"{name}_soft", colors)


def _draw_bivariate_legend(
    ax,
    quadrant_colors: dict[str, str],
    tiers: tuple[str, ...] = ("low", "high"),
    *,
    loc: tuple[float, float] = (0.98, 0.02),
    unit_in: float = 0.34,
    x_label: str = "Population density",
    y_label: str = "Accessibility",
) -> None:
    """
    Draw a compact NxN bivariate colour-matrix legend beside ``ax``,
    matching the plain colour-grid style used on joshuastevens.net (no
    text inside the cells — just the colour grid and two axis arrows).

    ``quadrant_colors`` keys are ``f"{x_tier}_{y_tier}"`` for every
    combination of ``tiers`` (e.g. 'low_low', 'medium_high', ...).

    ``loc`` is the legend's lower-right corner in ``ax`` axes coordinates;
    the default tucks it into the bottom-right of the map frame, which is
    empty in every study area, on a white backing so any block that does
    reach that corner can't show through. The legend is sized in inches (``unit_in`` per grid
    cell) rather than as a fraction of ``ax``, so text spacing stays the
    same whatever the shape of the study area.
    """
    from mpl_toolkits.axes_grid1.inset_locator import inset_axes

    n = len(tiers)
    # Data extent of the legend: grid occupies [0, n] x [0, n]; the right
    # and bottom margins hold the arrows, "Low"/"High" ticks and the bold
    # axis-name labels, each in its own band so nothing overlaps.
    x_min, x_max = -0.15, n + 2.4
    y_min, y_max = -1.45, n + 0.3
    legend_ax = inset_axes(
        ax,
        width=(x_max - x_min) * unit_in,
        height=(y_max - y_min) * unit_in,
        loc="lower right",
        bbox_to_anchor=loc,
        bbox_transform=ax.transAxes,
        borderpad=0,
    )
    legend_ax.set_xlim(x_min, x_max)
    legend_ax.set_ylim(y_min, y_max)
    legend_ax.set_aspect("equal")
    legend_ax.axis("off")
    legend_ax.add_patch(
        mpatches.Rectangle(
            (x_min, y_min), x_max - x_min, y_max - y_min,
            facecolor="white", edgecolor="none", alpha=0.9, zorder=0,
        )
    )

    for col, x_tier in enumerate(tiers):
        for row, y_tier in enumerate(tiers):
            colour = quadrant_colors[f"{x_tier}_{y_tier}"]
            legend_ax.add_patch(
                mpatches.Rectangle(
                    (col, row), 1, 1,
                    facecolor=colour, edgecolor="white", linewidth=1.0,
                )
            )

    # X-axis: horizontal arrow below the grid, "Low"/"High" ticks, then the
    # bold axis-name label on its own line underneath.
    legend_ax.annotate(
        "", xy=(n, -0.2), xytext=(0, -0.2),
        arrowprops=dict(arrowstyle="-|>", color="#333333", lw=1.1),
        annotation_clip=False,
    )
    legend_ax.text(0, -0.38, "Low", ha="left", va="top", fontsize=8)
    legend_ax.text(n, -0.38, "High", ha="right", va="top", fontsize=8)
    legend_ax.text(n / 2, -0.95, x_label, ha="center", va="top",
                   fontsize=9.5, fontweight="bold")

    # Y-axis: vertical arrow to the right of the grid, "Low"/"High" ticks
    # beside it, and the rotated axis-name label in its own column further
    # right, clear of the tick words.
    legend_ax.annotate(
        "", xy=(n + 0.2, n), xytext=(n + 0.2, 0),
        arrowprops=dict(arrowstyle="-|>", color="#333333", lw=1.1),
        annotation_clip=False,
    )
    legend_ax.text(n + 0.38, 0, "Low", ha="left", va="bottom", fontsize=8)
    legend_ax.text(n + 0.38, n, "High", ha="left", va="top", fontsize=8)
    legend_ax.text(n + 2.05, n / 2, y_label, ha="center", va="center",
                   rotation=90, fontsize=9.5, fontweight="bold")


def _weighted_quantile(values: np.ndarray, weights: np.ndarray, quantiles: list[float]) -> np.ndarray:
    """Population-weighted quantiles (used to split variables into tertiles)."""
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    sorter = np.argsort(values)
    values, weights = values[sorter], weights[sorter]
    cum_weights = np.cumsum(weights) - 0.5 * weights
    cum_weights /= np.sum(weights)
    return np.interp(quantiles, cum_weights, values)


def _projected_ticks(ax, crs) -> None:
    """
    Label a map's axes in its projected CRS (metres), as Easting / Northing
    with the EPSG code, so every study's frame reads the same way.
    """
    from matplotlib.ticker import FuncFormatter
    from pyproj import CRS

    epsg = CRS.from_user_input(crs).to_epsg() if crs is not None else None
    suffix = f"m, EPSG:{epsg}" if epsg else "m"
    thousands = FuncFormatter(lambda v, _: f"{v:,.0f}")
    ax.xaxis.set_major_formatter(thousands)
    ax.yaxis.set_major_formatter(thousands)
    ax.tick_params(labelsize=10)
    ax.set_xlabel(f"Easting ({suffix})", fontsize=12)
    ax.set_ylabel(f"Northing ({suffix})", fontsize=12)


def _populated(gdf: gpd.GeoDataFrame) -> pd.Series:
    """Blocks with residents. SDW-2SFCA scores every block, but empty ones
    (parks, rail yards, airports) have no one to serve, so summary statistics
    and inequality measures count populated blocks only."""
    if "population" not in gdf.columns:
        return pd.Series(True, index=gdf.index)
    return (pd.to_numeric(gdf["population"], errors="coerce").fillna(0) > 0) & _in_report_area(gdf)


def _in_report_area(gdf: gpd.GeoDataFrame) -> pd.Series:
    """Rows inside the study's reporting area (see study_area.report_area); all rows if unset."""
    if "in_report_area" not in gdf.columns:
        return pd.Series(True, index=gdf.index)
    return gdf["in_report_area"].fillna(False).astype(bool)


# ── 1. Accessibility Map ──────────────────────────────────────────────────────

def plot_accessibility_map(
    result_gdf: gpd.GeoDataFrame,
    facility_gdf: gpd.GeoDataFrame | None = None,
    config: dict | None = None,
    score_col: str = "accessibility_score",
    output_path: str | Path | None = None,
) -> Path:
    """
    Choropleth of 2SFCA accessibility scores.
    Style: block boundaries visible (white edges), RdYlBu colormap,
    facility markers as stars, axis labels showing projected coordinates.
    Matches original research visualization style.
    """
    if config is None:
        config = load_config()

    vc        = _base_cfg(config)
    area_name = config["study_area"]["name"]
    fac_label = config["facility"]["label"]
    method    = _method_label(config)
    output_path = output_path or _fname(config, "accessibility_map")
    output_path = Path(output_path)

    # Use raw score (not normalised) to match original style
    if score_col not in result_gdf.columns:
        score_col = "accessibility_norm"

    fig, ax = plt.subplots(figsize=vc["figsize"])

    result_gdf = result_gdf[_in_report_area(result_gdf)]
    if facility_gdf is not None:
        facility_gdf = facility_gdf[_in_report_area(facility_gdf)]
    populated = _populated(result_gdf)
    blocks    = result_gdf[populated]
    empty     = result_gdf[~populated]

    vmax_pct = config.get("visualization", {}).get("vmax_percentile", 95)
    nonzero = blocks[blocks[score_col] > 0][score_col]
    vmax = float(np.percentile(nonzero, vmax_pct))
    vmin = 0

    cmap_plot = _softened_cmap(vc["cmap"], low_cut=0.22)

    blocks.plot(
        column=score_col,
        cmap=cmap_plot,
        linewidth=0.10,
        edgecolor=(1.0, 1.0, 1.0, 0.45),
        legend=True,
        ax=ax,
        vmin=vmin,
        vmax=vmax,
        alpha=0.92,
        legend_kwds={
            "label": "Accessibility Score",
            "orientation": "vertical",
            "shrink": 0.7,
        },
        missing_kwds={"color": "#eef2f7", "label": "No data"},
    )
    if len(empty):
        empty.plot(ax=ax, color=NO_RESIDENTS_COLOR, linewidth=0.10, edgecolor=(1.0, 1.0, 1.0, 0.45))

    # Overlay facilities
    if facility_gdf is not None and len(facility_gdf) > 0:
        fac_plot = (
            facility_gdf.to_crs(result_gdf.crs)
            if facility_gdf.crs != result_gdf.crs
            else facility_gdf
        )
        fac_plot.plot(
            ax=ax,
            color="blue",
            marker="*",
            markersize=8,
            zorder=5,
            label=fac_label,
        )
    handles, _ = ax.get_legend_handles_labels()
    if len(empty):
        handles.append(mpatches.Patch(color=NO_RESIDENTS_COLOR,
                                      label=f"No residents ({len(empty):,} blocks)"))
    if handles:
        ax.legend(handles=handles, loc="lower left", fontsize=9)

    # Stats over blocks with residents; Gini counts each block equally, as does the Lorenz curve
    gini    = _gini(blocks[score_col].values)
    n_zero  = int((blocks[score_col] == 0).sum())
    mean_s  = blocks[score_col].mean()

    ax.set_title(
        f"{method} Accessibility to {fac_label} in {area_name}\n"
        f"Mean: {mean_s:.4f}  |  Gini: {gini:.3f}  "
        f"|  Zero-access blocks: {n_zero:,} ({n_zero/len(blocks)*100:.1f}%"
        f"{' of blocks with residents' if len(empty) else ''})",
        fontsize=14, pad=12,
    )
    _projected_ticks(ax, result_gdf.crs)

    plt.tight_layout()
    fig.savefig(output_path, dpi=vc["dpi"], bbox_inches="tight")
    plt.close(fig)

    log.info("Accessibility map saved → %s", output_path)
    return output_path


# ── 2. Lorenz Curve ───────────────────────────────────────────────────────────

def plot_lorenz_curve(
    result_gdf: gpd.GeoDataFrame,
    config: dict | None = None,
    output_path: str | Path | None = None,
) -> Path:
    """Lorenz curve over blocks with residents, each counted equally, so the
    area between the curve and the equality line matches the Gini shown."""
    if config is None:
        config = load_config()

    vc        = _base_cfg(config)
    area_name = config["study_area"]["name"]
    fac_label = config["facility"]["label"]
    method    = _method_label(config)
    output_path = output_path or _fname(config, "lorenz_curve")
    output_path = Path(output_path)

    scores = result_gdf.loc[_populated(result_gdf), "accessibility_score"].values

    scores_s   = np.sort(scores.astype(float))
    cum_blocks = np.arange(1, len(scores_s) + 1) / len(scores_s)
    cum_access = np.cumsum(scores_s)
    if cum_access[-1] > 0:
        cum_access = cum_access / cum_access[-1]
    else:
        cum_access = cum_blocks.copy()

    gini = _gini(scores)

    fig, ax = plt.subplots(figsize=(9, 7))

    ax.plot([0, 1], [0, 1], "k--", linewidth=1.2, label="Perfect equality", alpha=0.6)
    ax.plot(
        np.concatenate([[0], cum_blocks]),
        np.concatenate([[0], cum_access]),
        color="#2196F3", linewidth=2.5,
        label=f"{method}  (Gini = {gini:.4f})",
    )
    ax.fill_between(
        np.concatenate([[0], cum_blocks]),
        np.concatenate([[0], cum_blocks]),
        np.concatenate([[0], cum_access]),
        alpha=0.12, color="#2196F3",
    )

    ax.text(
        0.05, 0.88,
        f"Gini coefficient: {gini:.4f}\n(0 = perfect equality, 1 = maximum inequality)",
        transform=ax.transAxes, fontsize=10,
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white", edgecolor="#cccccc"),
    )

    ax.set_xlabel("Cumulative Share of Census Blocks with Residents", fontsize=12)
    ax.set_ylabel("Cumulative Share of Accessibility", fontsize=12)
    ax.set_title(
        f"Lorenz Curve — {fac_label} Accessibility Inequality\n{area_name}",
        fontsize=13,
    )
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    plt.tight_layout()
    fig.savefig(output_path, dpi=vc["dpi"], bbox_inches="tight")
    plt.close(fig)

    log.info("Lorenz curve saved → %s  (Gini=%.4f)", output_path, gini)
    return output_path


# ── 3. Bivariate Map ──────────────────────────────────────────────────────────

def plot_bivariate_map(
    result_gdf: gpd.GeoDataFrame,
    config: dict | None = None,
    output_path: str | Path | None = None,
) -> Path:
    """
    Bivariate choropleth: population density × accessibility score.
    Style: white block boundaries, axis labels, clean legend.
    """
    if config is None:
        config = load_config()

    vc        = _base_cfg(config)
    area_name = config["study_area"]["name"]
    fac_label = config["facility"]["label"]
    output_path = output_path or _fname(config, "bivariate_map")
    output_path = Path(output_path)

    gdf = result_gdf.copy()

# Filter to populated blocks only — removes empty rural/mountain blocks
# that dominate LA County geography and obscure urban patterns
    gdf = gdf[_populated(gdf)].copy()

    gdf["area_km2"]    = gdf.geometry.area / 1e6
    gdf["pop_density"] = gdf["population"] / gdf["area_km2"].replace(0, np.nan)

    pop_weights = (gdf["population"] / gdf["population"].sum()).fillna(0)
    pop_q33, pop_q66 = _weighted_quantile(
        gdf["pop_density"].fillna(0), pop_weights, [1 / 3, 2 / 3]
    )
    acc_q33, acc_q66 = _weighted_quantile(
        gdf["accessibility_norm"].fillna(0), pop_weights, [1 / 3, 2 / 3]
    )

    tiers = ("low", "medium", "high")

    # Joshua Stevens-style red/blue bivariate palette, 3x3: population
    # density runs grey -> red, accessibility runs grey -> blue, so dense
    # blocks with low access stand out in strong red.
    # https://www.joshuastevens.net/cartography/make-a-bivariate-choropleth-map/
    quadrant_colors = {
        "low_low":       "#e8e8e8",
        "low_medium":    "#b0d5df",
        "low_high":      "#64acbe",
        "medium_low":    "#e4acac",
        "medium_medium": "#ad9ea5",
        "medium_high":   "#627f8c",
        "high_low":      "#c85a5a",
        "high_medium":   "#985356",
        "high_high":     "#574249",
    }

    def _tier(value: float, q33: float, q66: float) -> str:
        if value <= q33:
            return "low"
        elif value <= q66:
            return "medium"
        return "high"

    def _classify(row):
        x_tier = _tier(row["pop_density"], pop_q33, pop_q66)
        y_tier = _tier(row["accessibility_norm"], acc_q33, acc_q66)
        return f"{x_tier}_{y_tier}"

    gdf["bivariate_class"] = gdf.apply(_classify, axis=1)

    fig, ax = plt.subplots(figsize=vc["figsize"])

    for key, colour in quadrant_colors.items():
        subset = gdf[gdf["bivariate_class"] == key]
        if len(subset) > 0:
            subset.plot(
                ax=ax, color=colour,
                linewidth=0.1, edgecolor="#e3e6ea",
                alpha=0.95,
                label=key,
            )

    _draw_bivariate_legend(
        ax, quadrant_colors, tiers,
        x_label="Pop. density", y_label="Accessibility",
    )

    ax.set_title(
        f"Bivariate Map — Population Density × Accessibility\n"
        f"{fac_label} | {area_name}",
        fontsize=13, pad=12,
    )
    _projected_ticks(ax, gdf.crs)

    plt.tight_layout()
    fig.savefig(output_path, dpi=vc["dpi"], bbox_inches="tight")
    plt.close(fig)

    log.info("Bivariate map saved → %s", output_path)
    return output_path


# ── 4. Access Gap Chart ───────────────────────────────────────────────────────

def plot_access_gap_chart(
    result_gdf: gpd.GeoDataFrame,
    config: dict | None = None,
    output_path: str | Path | None = None,
) -> Path:
    """Bar chart of zero-access blocks ranked by population."""
    if config is None:
        config = load_config()

    vc        = _base_cfg(config)
    area_name = config["study_area"]["name"]
    fac_label = config["facility"]["label"]
    output_path = output_path or _fname(config, "access_gap_chart")
    output_path = Path(output_path)

    result_gdf = result_gdf[_populated(result_gdf)]
    gaps = (
        result_gdf[result_gdf["accessibility_score"] == 0]
        .copy()
        .sort_values("population", ascending=False)
        .reset_index(drop=True)
    )

    if len(gaps) == 0:
        log.info("No zero-access blocks — skipping gap chart")
        return output_path

    top_n = min(30, len(gaps))
    gaps  = gaps.head(top_n)
    total_gap_pop = result_gdf.loc[
        result_gdf["accessibility_score"] == 0, "population"
    ].sum()
    cum_pct = gaps["population"].cumsum() / total_gap_pop * 100

    fig, ax1 = plt.subplots(figsize=(14, 6))
    ax2 = ax1.twinx()

    ax1.bar(range(top_n), gaps["population"], color="#c0392b", alpha=0.8, label="Block population")
    ax2.plot(range(top_n), cum_pct, color="#2c3e50", linewidth=2,
             marker="o", markersize=4, label="Cumulative % of gap population")

    ax1.set_xlabel("Census Block (ranked by population)", fontsize=11)
    ax1.set_ylabel("Population in zero-access block", fontsize=11, color="#c0392b")
    ax2.set_ylabel("Cumulative % of total gap population", fontsize=11, color="#2c3e50")
    ax2.set_ylim(0, 105)

    ax1.set_xticks(range(top_n))
    ax1.set_xticklabels(
        [g[:8] + "…" if len(g) > 8 else g for g in gaps["GEOID"].astype(str)],
        rotation=90, fontsize=7,
    )

    idx_80 = np.searchsorted(cum_pct.values, 80)
    if idx_80 < top_n:
        ax2.axvline(idx_80, color="orange", linestyle="--", linewidth=1.5,
                    label=f"Top {idx_80+1} blocks cover 80% of gap pop")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="center right", fontsize=9)

    total_gap_blocks = (result_gdf["accessibility_score"] == 0).sum()
    ax1.set_title(
        f"Zero-Access Blocks Ranked by Population — {fac_label} | {area_name}\n"
        f"Total zero-access blocks: {total_gap_blocks:,} | "
        f"Total affected population: {int(total_gap_pop):,}",
        fontsize=12,
    )

    plt.tight_layout()
    fig.savefig(output_path, dpi=vc["dpi"], bbox_inches="tight")
    plt.close(fig)

    log.info("Access gap chart saved → %s", output_path)
    return output_path


# ── 5. Interactive Folium Map ─────────────────────────────────────────────────

def plot_interactive_map(
    result_gdf: gpd.GeoDataFrame,
    facility_gdf: gpd.GeoDataFrame | None = None,
    config: dict | None = None,
    output_path: str | Path | None = None,
) -> Path:
    """Interactive HTML map using Folium."""
    try:
        import folium
        from folium.features import GeoJsonTooltip
        import branca.colormap as cm
    except ImportError:
        log.warning("folium not installed — skipping interactive map")
        return Path("outputs/figures/interactive_map_skipped.txt")

    if config is None:
        config = load_config()

    area_name = config["study_area"]["name"]
    fac_label = config["facility"]["label"]
    state     = config["study_area"]["state_abbrev"].lower()
    ftype     = config["facility"]["type"].lower()

    output_path = output_path or (
        _fig_dir(config) / f"{state}_{ftype}_interactive_map.html"
    )
    output_path = Path(output_path)

    gdf_4326  = result_gdf.to_crs("EPSG:4326")
    centroid  = gdf_4326.geometry.unary_union.centroid
    m = folium.Map(
        location=[centroid.y, centroid.x],
        zoom_start=12,
        tiles="CartoDB positron",
    )

    score_min = gdf_4326["accessibility_norm"].min()
    score_max = gdf_4326["accessibility_norm"].max()
    cmap_plot = _softened_cmap(config.get("visualization", {}).get("colormap", "RdYlBu"), low_cut=0.22)
    colormap  = cm.LinearColormap(
        [mcolors.to_hex(cmap_plot(0.0)), mcolors.to_hex(cmap_plot(0.5)), mcolors.to_hex(cmap_plot(1.0))],
        vmin=score_min, vmax=score_max,
        caption="Accessibility Score (normalised)",
    )

    def _style(feature):
        score = feature["properties"].get("accessibility_norm", 0)
        return {
            "fillColor":   colormap(score),
            "color":       "rgba(255,255,255,0.45)",
            "weight":      0.15,
            "fillOpacity": 0.80,
        }

    folium.GeoJson(
        gdf_4326[["GEOID", "population", "accessibility_score",
                  "accessibility_norm", "geometry"]].__geo_interface__,
        style_function=_style,
        tooltip=GeoJsonTooltip(
            fields=["GEOID", "population", "accessibility_score", "accessibility_norm"],
            aliases=["Block GEOID", "Population", "Accessibility Score", "Normalised Score"],
            localize=True,
        ),
        name="Accessibility Scores",
    ).add_to(m)
    colormap.add_to(m)

    if facility_gdf is not None and len(facility_gdf) > 0:
        fac_4326  = facility_gdf.to_crs("EPSG:4326")
        fac_group = folium.FeatureGroup(name=fac_label)
        for _, row in fac_4326.iterrows():
            name   = row.get("FAC_NAME", "Facility")
            supply = row.get("supply", "N/A")
            folium.Marker(
                location=[row.geometry.y, row.geometry.x],
                popup=folium.Popup(f"<b>{name}</b><br>Supply: {supply}", max_width=200),
                tooltip=f"{name} (supply={supply})",
                icon=folium.Icon(color="blue", icon="plus-sign"),
            ).add_to(fac_group)
        fac_group.add_to(m)

    folium.LayerControl().add_to(m)
    title_html = f"""
    <div style="position:fixed;top:10px;left:50%;transform:translateX(-50%);
                z-index:1000;background:white;padding:8px 16px;
                border-radius:4px;box-shadow:0 2px 6px rgba(0,0,0,0.3);
                font-family:Arial;font-size:14px;font-weight:bold;">
        {fac_label} Accessibility — {area_name}
    </div>"""
    m.get_root().html.add_child(folium.Element(title_html))
    m.save(str(output_path))

    log.info("Interactive map saved → %s", output_path)
    return output_path


# ── Master runner ─────────────────────────────────────────────────────────────

def run_all_visualizations(
    result_gdf: gpd.GeoDataFrame,
    facility_gdf: gpd.GeoDataFrame | None = None,
    config: dict | None = None,
) -> dict[str, Path]:
    """Generate the full visualization suite."""
    if config is None:
        config = load_config()

    paths = {}

    log.info("Generating accessibility map...")
    paths["accessibility_map"] = plot_accessibility_map(result_gdf, facility_gdf, config)

    log.info("Generating Lorenz curve...")
    paths["lorenz_curve"] = plot_lorenz_curve(result_gdf, config)

    log.info("Generating bivariate map...")
    paths["bivariate_map"] = plot_bivariate_map(result_gdf, config)

    log.info("Generating access gap chart...")
    paths["access_gap_chart"] = plot_access_gap_chart(result_gdf, config)

    log.info("Generating interactive map...")
    paths["interactive_map"] = plot_interactive_map(result_gdf, facility_gdf, config)

    log.info("All visualizations complete:")
    for name, path in paths.items():
        log.info("  %-20s → %s", name, path)

    return paths
