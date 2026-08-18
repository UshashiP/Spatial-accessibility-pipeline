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
3. bivariate_map            — population density × accessibility (2×2 classification)
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
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize, BoundaryNorm
from mpl_toolkits.axes_grid1 import make_axes_locatable

from pipeline.config import load_config

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent

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

    vmax_pct = config.get("visualization", {}).get("vmax_percentile", 95)
    nonzero = result_gdf[result_gdf[score_col] > 0][score_col]
    vmax = float(np.percentile(nonzero, vmax_pct))
    vmin = 0

    cmap_plot = _softened_cmap(vc["cmap"], low_cut=0.22)

    result_gdf.plot(
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
        ax.legend(loc="lower left", fontsize=9)

    # Stats — population-weighted so map title matches the Lorenz curve
    pop_w   = result_gdf["population"].values.astype(float) if "population" in result_gdf.columns else None
    gini    = _gini(result_gdf[score_col].values)
    n_zero  = (result_gdf[score_col] == 0).sum()
    mean_s  = result_gdf[score_col].mean()

    ax.set_title(
        f"{method} Accessibility to {fac_label} in {area_name}\n"
        f"Mean: {mean_s:.4f}  |  Gini: {gini:.3f}  "
        f"|  Zero-access blocks: {n_zero} ({n_zero/len(result_gdf)*100:.1f}%)",
        fontsize=14, pad=12,
    )
    ax.set_xlabel("Longitude", fontsize=12)
    ax.set_ylabel("Latitude", fontsize=12)

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
    """Population-weighted Lorenz curve with Gini coefficient."""
    if config is None:
        config = load_config()

    vc        = _base_cfg(config)
    area_name = config["study_area"]["name"]
    fac_label = config["facility"]["label"]
    method    = _method_label(config)
    output_path = output_path or _fname(config, "lorenz_curve")
    output_path = Path(output_path)

    scores = result_gdf["accessibility_score"].values
    pop    = result_gdf["population"].values.astype(float)

    order      = np.argsort(scores)
    scores_s   = scores[order]
    pop_s      = pop[order]
    cum_pop    = np.cumsum(pop_s) / pop_s.sum()
    cum_access = np.cumsum(scores_s * pop_s)
    if cum_access[-1] > 0:
        cum_access = cum_access / cum_access[-1]
    else:
        cum_access = cum_pop.copy()

    gini = _gini(scores)

    fig, ax = plt.subplots(figsize=(9, 7))

    ax.plot([0, 1], [0, 1], "k--", linewidth=1.2, label="Perfect equality", alpha=0.6)
    ax.plot(
        np.concatenate([[0], cum_pop]),
        np.concatenate([[0], cum_access]),
        color="#2196F3", linewidth=2.5,
        label=f"{method}  (Gini = {gini:.4f})",
    )
    ax.fill_between(
        np.concatenate([[0], cum_pop]),
        np.concatenate([[0], cum_pop]),
        np.concatenate([[0], cum_access]),
        alpha=0.12, color="#2196F3",
    )

    ax.text(
        0.05, 0.88,
        f"Gini coefficient: {gini:.4f}\n(0 = perfect equality, 1 = maximum inequality)",
        transform=ax.transAxes, fontsize=10,
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white", edgecolor="#cccccc"),
    )

    ax.set_xlabel("Cumulative Share of Population", fontsize=12)
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
    gdf = gdf[gdf["population"] > 0].copy()

    gdf["area_km2"]    = gdf.geometry.area / 1e6
    gdf["pop_density"] = gdf["population"] / gdf["area_km2"].replace(0, np.nan)


    gdf["area_km2"]    = gdf.geometry.area / 1e6
    gdf["pop_density"] = gdf["population"] / gdf["area_km2"].replace(0, np.nan)

    pop_weights = gdf["population"] / gdf["population"].sum()
    pop_med = float(np.average(gdf["pop_density"], weights=pop_weights.fillna(0)))
    score_med = float(np.average(gdf["accessibility_norm"], weights=pop_weights.fillna(0)))

    color_map = {
        "Priority\n(High pop, Low access)":    "#c0392b",
        "Well served\n(High pop, High access)": "#2980b9",
        "Low priority\n(Low pop, Low access)":  "#bdc3c7",
        "Over-served\n(Low pop, High access)":  "#85c1e9",
    }

    def _classify(row):
        hi_pop    = row["pop_density"]        >= pop_med
        hi_access = row["accessibility_norm"] >= score_med
        if hi_pop and not hi_access:
            return "Priority\n(High pop, Low access)"
        elif hi_pop and hi_access:
            return "Well served\n(High pop, High access)"
        elif not hi_pop and not hi_access:
            return "Low priority\n(Low pop, Low access)"
        else:
            return "Over-served\n(Low pop, High access)"

    gdf["bivariate_class"] = gdf.apply(_classify, axis=1)

    fig, ax = plt.subplots(figsize=vc["figsize"])

    for label, colour in color_map.items():
        subset = gdf[gdf["bivariate_class"] == label]
        if len(subset) > 0:
            subset.plot(
                ax=ax, color=colour,
                linewidth=0.1, edgecolor="#e3e6ea",
                alpha=0.95,
                label=label,
            )

    ax.legend(loc="lower left", fontsize=9, title="Pop Density × Accessibility")

    priority_pop = gdf.loc[
        gdf["bivariate_class"] == "Priority\n(High pop, Low access)", "population"
    ].sum()
    priority_n = (gdf["bivariate_class"] == "Priority\n(High pop, Low access)").sum()

    ax.set_title(
        f"Bivariate Map — Population Density × Accessibility\n"
        f"{fac_label} | {area_name}  "
        f"|  Priority zones: {priority_n} blocks ({int(priority_pop):,} people)",
        fontsize=13, pad=12,
    )
    ax.set_xlabel("Longitude", fontsize=12)
    ax.set_ylabel("Latitude", fontsize=12)

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
