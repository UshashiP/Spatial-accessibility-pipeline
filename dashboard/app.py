"""
CareScape - Healthcare Access Intelligence
--------------------------------------------------------------------
Streamlit dashboard for exploring SDW-2SFCA accessibility results.

Run: streamlit run dashboard/app.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import geopandas as gpd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import folium
from streamlit_folium import folium_static
from branca.colormap import LinearColormap
from pathlib import Path
from html import escape
from map_details import (
    BIVARIATE_COLORS, BIVARIATE_NAMED, DILUTED, ISOLATED, LEFT_BEHIND, block_zoom, build_block_details,
    build_color_scale, classify_bivariate, populated_mask, search_blocks,
)

# ── Page Configuration ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CareScape | Healthcare Access Intelligence",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Modern UI Styling ──────────────────────────────────────────────────────────
st.markdown("""
<style>
.stApp {
    background: #f5f7f9;
    color: #172b3a;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    color-scheme: light;
}

.main .block-container {
    max-width: 1500px;
    padding: 2.5rem 2rem;
}

[data-testid="stHeader"] {
    background: #f5f7f9;
}

h1, h2, h3, h4 {
    color: #172b3a;
    letter-spacing: -0.025em;
}

.dashboard-header {
    margin-bottom: 1.5rem;
    padding: 1.5rem;
    border: 1px solid #c6dce9;
    border-radius: 14px;
    background: linear-gradient(115deg, #e1f4f1 0%, #e9efff 65%, #f4eaff 100%);
    box-shadow: 0 4px 18px rgba(38, 76, 113, 0.05);
}

.brand-row {
    display: flex;
    align-items: center;
    gap: 1rem;
}

.brand-icon {
    display: grid;
    place-items: center;
    flex-shrink: 0;
    width: 64px;
    height: 64px;
    font-size: 2rem;
    background: #ffffff;
    border: 1px solid #cce3df;
    border-radius: 16px;
}

.brand-subtitle {
    color: #355b75;
    font-weight: 600;
    font-size: 0.95rem;
}

.eyebrow {
    color: #087f78;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
}

.dashboard-header h1 {
    font-size: clamp(1.75rem, 3vw, 2.5rem);
    font-weight: 700;
    margin: 0.5rem 0;
    padding: 0;
}

.dashboard-header p, .sidebar-intro, .dashboard-footer {
    color: #526779;
    line-height: 1.6;
}

.lab-badge {
    display: inline-block;
    margin-left: 0.5rem;
    padding: 0.2rem 0.5rem;
    border: 1px solid #cbd5df;
    border-radius: 4px;
    color: #526779;
    font-size: 0.65rem;
    letter-spacing: 0.05em;
}

[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #e5f3f1 0%, #eef2fc 60%, #f7f9fc 100%);
    border-right: 1px solid #cbdfe3;
}

@media (min-width: 769px) {
    [data-testid="stSidebar"] {
        width: 340px !important;
        min-width: 340px !important;
        max-width: 340px !important;
    }
}

[data-testid="stSidebar"] > div:first-child {
    padding-left: 1.1rem;
    padding-right: 1.1rem;
}

[data-testid="stSidebar"] h2 {
    font-size: 1.3rem;
}

[data-testid="stSidebar"] [data-baseweb="select"] > div {
    background: #f5f7f9;
    border-color: #cbd5df;
    color: #172b3a;
}

.analysis-details {
    padding: 1rem;
    background: rgba(255, 255, 255, 0.8);
    border: 1px solid #ccdde7;
    border-radius: 8px;
}

.analysis-details dt {
    margin-top: 0.9rem;
    color: #526779;
    font-size: 0.75rem;
}

.analysis-details dt:first-child {
    margin-top: 0;
}

.analysis-details dd {
    margin: 0.25rem 0 0;
    color: #172b3a;
    font-size: 0.9rem;
    font-weight: 600;
}

[data-testid="stMetric"], div[data-testid="metric-container"] {
    background: #ffffff;
    border: 1px solid #dce3e9;
    border-radius: 8px;
    padding: 1.1rem;
    min-height: 115px;
}

[data-testid="stMetricValue"] {
    color: #172b3a;
    font-size: 2rem;
    font-weight: 650;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.04em;
}

[data-testid="stMetricLabel"] {
    color: #526779;
    font-size: 0.85rem;
}

[data-testid="stHorizontalBlock"] > div:nth-child(1) [data-testid="stMetric"] {
    background: #edf3ff;
    border-color: #cbdaf5;
    border-top: 3px solid #4875c7;
}

[data-testid="stHorizontalBlock"] > div:nth-child(1) [data-testid="stMetricValue"] {
    color: #305ba2;
}

[data-testid="stHorizontalBlock"] > div:nth-child(2) [data-testid="stMetric"] {
    background: #e9f6f1;
    border-color: #c5e5d8;
    border-top: 3px solid #16816c;
}

[data-testid="stHorizontalBlock"] > div:nth-child(2) [data-testid="stMetricValue"] {
    color: #146b59;
}

[data-testid="stHorizontalBlock"] > div:nth-child(3) [data-testid="stMetric"] {
    background: #fff2e9;
    border-color: #f0d7c4;
    border-top: 3px solid #c96c30;
}

[data-testid="stHorizontalBlock"] > div:nth-child(3) [data-testid="stMetricValue"] {
    color: #a24c1b;
}

[data-testid="stHorizontalBlock"] > div:nth-child(4) [data-testid="stMetric"] {
    background: #f3edfc;
    border-color: #dfd1f1;
    border-top: 3px solid #8960ba;
}

[data-testid="stHorizontalBlock"] > div:nth-child(4) [data-testid="stMetricValue"] {
    color: #70459f;
}

.stTabs [data-baseweb="tab-list"] {
    gap: 1.5rem;
    border-bottom: 1px solid #dce3e9;
    margin-top: 0.75rem;
}

.stTabs [data-baseweb="tab"] {
    background: transparent;
    border: none;
    color: #526779;
    padding: 0.75rem 0.1rem;
    font-weight: 500;
}

.stTabs [aria-selected="true"] {
    color: #087f78;
    font-weight: 600;
    background: #e1f1ee;
    border-radius: 6px 6px 0 0;
    padding-left: 0.65rem;
    padding-right: 0.65rem;
}

.stTabs [data-baseweb="tab-highlight"] {
    background: #087f78;
}

.stTabs [data-baseweb="tab-panel"] {
    padding-top: 1.25rem;
}

.stButton button, .stDownloadButton button {
    background: #087f78;
    border: 1px solid #087f78;
    border-radius: 6px;
    color: white;
}

.stButton button:hover, .stDownloadButton button:hover {
    background: #06665f;
    border-color: #06665f;
    color: white;
}

.stButton button:focus-visible, .stDownloadButton button:focus-visible,
.stTabs [data-baseweb="tab"]:focus-visible {
    outline: 3px solid #087f78;
    outline-offset: 3px;
}

.info-card, .warning-card, .success-card {
    border-radius: 6px;
    padding: 0.85rem 1rem;
    margin: 0.5rem 0 1rem;
    font-size: 0.9rem;
    line-height: 1.6;
}

.info-card {
    background: #edf6f5;
    border: 1px solid #cce3df;
    color: #26534f;
}

.warning-card {
    background: #fff8eb;
    border: 1px solid #e8d4a8;
    color: #77541b;
}

.success-card {
    background: #ffffff;
    border: 1px solid #dce3e9;
}

[data-testid="stPlotlyChart"], [data-testid="stDataFrame"] {
    background: #ffffff;
    border: 1px solid #dce3e9;
    border-radius: 8px;
    overflow: hidden;
}

.dashboard-footer {
    border-top: 1px solid #dce3e9;
    padding: 1.25rem 0;
    font-size: 0.8rem;
}

.dashboard-footer a {
    color: #087f78;
}

@media (max-width: 768px) {
    .main .block-container {
        padding: 1.5rem 1rem;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 1rem;
    }

    .dashboard-header {
        padding: 1rem;
    }

    .brand-row {
        gap: 0.75rem;
    }

    .brand-icon {
        width: 48px;
        height: 48px;
        font-size: 1.6rem;
    }
}

/* Blocks are clickable, so show an arrow on the map instead of MapLibre's grab hand. */
.stPlotlyChart .maplibregl-canvas-container.maplibregl-interactive,
.stPlotlyChart .maplibregl-canvas {
    cursor: default;
}
.stPlotlyChart .maplibregl-canvas-container.maplibregl-interactive:active,
.stPlotlyChart .maplibregl-canvas:active {
    cursor: grabbing;
}

</style>
""", unsafe_allow_html=True)

MAP_PALETTE = px.colors.sequential.Teal
NO_ACCESS_COLOR = "#e8833a"
NO_RESIDENTS_COLOR = "#dcdcdc"
# Keyless basemaps. "outline" and "facility" keep the selection and markers visible on each.
BASEMAPS = {
    "Light (CARTO Positron)": {"style": "carto-positron", "outline": "#172b3a", "facility": "#172b3a"},
    "Streets (CARTO Voyager)": {"style": "carto-voyager", "outline": "#172b3a", "facility": "#172b3a"},
    "Dark (CARTO Dark Matter)": {"style": "carto-darkmatter", "outline": "#ffd400", "facility": "#ffffff"},
    "OpenStreetMap": {"style": "open-street-map", "outline": "#172b3a", "facility": "#172b3a"},
    "Satellite (Esri)": {
        "style": "white-bg",
        "layers": [{
            "below": "traces",
            "sourcetype": "raster",
            "source": ["https://server.arcgisonline.com/ArcGIS/rest/services/"
                       "World_Imagery/MapServer/tile/{z}/{y}/{x}"],
            "sourceattribution": "Imagery © Esri, Maxar, Earthstar Geographics",
        }],
        "outline": "#ffd400",
        "facility": "#ffffff",
    },
}

# ── Data Configuration ─────────────────────────────────────────────────────────
CITIES = {
    "Washington DC — ICF Facilities": {
        "city": "Washington DC",
        "prefix": "dc_icf",
        "crs": "EPSG:26985",
        "facility": "Intermediate Care Facilities",
        "supply_label": "certified beds",
        "color": "#087f78",
        "catchment": "900m",
        "catchment_m": 900,
    },
    "New York City — Dialysis Centers": {
        "city": "New York City",
        "prefix": "ny_dialysis",
        "crs": "EPSG:32618",
        "facility": "Dialysis Centers",
        "supply_label": "dialysis stations",
        "color": "#10b981",
        "catchment": "1,200m",
        "catchment_m": 1200,
    },
    "Los Angeles — FQHCs": {
        "city": "City of Los Angeles",
        "prefix": "ca_fqhc",
        "crs": "EPSG:32611",
        "facility": "Federally Qualified Health Centers",
        "supply_label": "FQHC sites",
        "color": "#f59e0b",
        "catchment": "1,600m",
        "catchment_m": 1600,
    },
}

# ── Helper Functions ───────────────────────────────────────────────────────────
def find_latest_parquet(layer: str, dataset: str) -> Path | None:
    """Find the most recent parquet file for a dataset in a layer."""
    root = Path("outputs/results") / layer
    candidates = sorted(root.glob(f"run_date=*/{dataset}.parquet"))
    if not candidates:
        return None
    return candidates[-1]  # Most recent date

@st.cache_data(show_spinner="📊 Loading data...")
def load_scores(prefix: str) -> gpd.GeoDataFrame:
    """Load accessibility scores with proper error handling."""
    try:
        path = find_latest_parquet("gold", f"{prefix}_scores")
        if not path:
            st.error(f"No score files found for {prefix}")
            return gpd.GeoDataFrame()
        gdf = gpd.read_parquet(path)
        if "accessibility_score" not in gdf.columns:
            gdf["accessibility_score"] = 0.0
        gdf["accessibility_score"] = pd.to_numeric(gdf["accessibility_score"], errors="coerce").fillna(0.0)
        # Blocks outside the reporting area (e.g. LA County around the City of LA)
        # are modelled but not reported.
        if "in_report_area" in gdf:
            gdf = gdf[gdf["in_report_area"].fillna(False).astype(bool)]
        return gdf
    except Exception as e:
        st.error(f"Error loading scores: {e}")
        return gpd.GeoDataFrame()

@st.cache_data(show_spinner=False)
def load_facilities(prefix: str) -> gpd.GeoDataFrame:
    """Load facility locations."""
    try:
        path = find_latest_parquet("silver", f"{prefix}_facilities")
        if not path:
            st.warning(f"No facility files found for {prefix}")
            return gpd.GeoDataFrame()
        facilities = gpd.read_parquet(path)
        # Show the sites inside the reporting area; the model used them all.
        if "in_report_area" in facilities:
            facilities = facilities[facilities["in_report_area"].fillna(False).astype(bool)]
        return facilities
    except Exception as e:
        st.warning(f"Could not load facilities: {e}")
        return gpd.GeoDataFrame()

def compute_gini(scores: np.ndarray) -> float:
    """Calculate Gini coefficient for inequality measurement."""
    x = np.sort(scores.astype(float))
    n = len(x)
    if x.sum() == 0:
        return 0.0
    return float((2 * np.sum(np.arange(1, n + 1) * x)) / (n * x.sum()) - (n + 1) / n)

def create_lorenz_data(scores: np.ndarray):
    """Lorenz curve with each block counted equally, so its area matches compute_gini."""
    s = np.sort(scores.astype(float))
    cum_b = np.arange(1, len(s) + 1) / len(s)
    cum_a = np.cumsum(s)
    if cum_a[-1] > 0:
        cum_a = cum_a / cum_a[-1]
    return np.concatenate([[0], cum_b]), np.concatenate([[0], cum_a])

# ── Main Application ───────────────────────────────────────────────────────────
def main():
    # ═══ TOP SECTION: Header ═══
    st.markdown("""
    <div class='dashboard-header'>
        <div class='brand-row'>
            <div class='brand-icon' role='img' aria-label='Hospital'>🏥</div>
            <div>
                <h1>CareScape</h1>
                <div class='brand-subtitle'>Healthcare Access Intelligence</div>
            </div>
        </div>
        <p>Explore local access to care, understand disparities, and identify underserved communities.</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar Controls
    with st.sidebar:
        st.markdown("""
        <div class='eyebrow'>🏥 CareScape</div>
        <h2>Explore access</h2>
        <p class='sidebar-intro'>Choose a study area to explore its healthcare accessibility results.</p>
        """, unsafe_allow_html=True)
        
        city_key = st.selectbox(
            "City & facility type",
            options=list(CITIES.keys()),
            index=0
        )
        
        cfg = CITIES[city_key]
        
        st.markdown("#### Study details")
        st.markdown(f"""
        <dl class='analysis-details'>
            <dt>Facility type</dt><dd>{cfg['facility']}</dd>
            <dt>Catchment radius</dt><dd>{cfg['catchment']}</dd>
            <dt>Method</dt><dd>SDW-2SFCA</dd>
        </dl>
        """, unsafe_allow_html=True)
    
    # Load Data
    scores_gdf = load_scores(cfg["prefix"])
    facilities_gdf = load_facilities(cfg["prefix"])
    
    if scores_gdf.empty:
        st.error("❌ Could not load data. Please check file paths.")
        return
    
    # Compute Statistics (blocks with residents only; empty blocks have no one to serve)
    populated_gdf = scores_gdf[populated_mask(scores_gdf)]
    n_empty = len(scores_gdf) - len(populated_gdf)
    scores = populated_gdf["accessibility_score"].values
    gini = compute_gini(scores)

    zero_access_pct = (scores == 0).mean() * 100
    zero_access_pop = int(populated_gdf.loc[scores == 0, "population"].sum())
    total_pop = int(populated_gdf["population"].sum())
    zero_access_pop_pct = zero_access_pop / total_pop * 100 if total_pop else 0.0

    # ═══ Quick Stats Bar ═══
    st.caption(
        f"STUDY OVERVIEW / {city_key} · {len(populated_gdf):,} census blocks with residents"
        + (f" · {n_empty:,} blocks with no residents excluded" if n_empty else "")
    )
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "Residents with no access",
        f"{zero_access_pop:,}",
        help=(
            f"Residents living in census blocks with a zero accessibility score "
            f"({zero_access_pop_pct:.1f}% of {total_pop:,} residents in the study)."
        ),
    )
    col2.metric(
        "Blocks with no access",
        f"{zero_access_pct:.1f}%",
        help="Share of census blocks with residents that have a zero accessibility score.",
    )
    col3.metric("Facilities", f"{len(facilities_gdf):,}", help="Number of facilities in the selected study.")
    col4.metric(
        "Gini index",
        f"{gini:.3f}",
        help="Inequality across the accessibility scores of blocks with residents. "
             "Closer to 0 means more equal; closer to 1 means more unequal.",
    )
    if total_pop:
        st.markdown(
            f"""
            <div class='info-card'>
                <strong>Key finding:</strong> {zero_access_pop:,} of {total_pop:,} residents
                ({zero_access_pop_pct:.0f}%) live in census blocks with no
                {cfg['facility'].lower()} within {cfg['catchment']}.
            </div>
            """,
            unsafe_allow_html=True,
        )
    
    # ═══ BODY SECTION: Main Content ═══
    tab1, tab2, tab3, tab4 = st.tabs(["Access map", "Inequality", "Left behind", "Export data"])
    
    with tab1:
        render_map_tab(scores_gdf, facilities_gdf, cfg)
    
    with tab2:
        render_inequality_tab(populated_gdf, gini)

    with tab3:
        render_left_behind_tab(populated_gdf, facilities_gdf, cfg)
    
    with tab4:
        render_export_tab(scores_gdf, cfg)
    
    # ═══ BOTTOM SECTION: Footer ═══
    st.markdown("<div style='margin-top: 2rem;'></div>", unsafe_allow_html=True)
    render_footer()

def _clicked_geoid(point: dict) -> str | None:
    """GEOID of a clicked choropleth block, from its location or hover customdata."""
    if point.get("location"):
        return str(point["location"])
    customdata = point.get("customdata")
    return str(customdata[0]) if customdata else None


# ── Tab Renderers ──────────────────────────────────────────────────────────────
def render_map_tab(scores_gdf, facilities_gdf, cfg):
    """Render interactive map visualization."""
    st.markdown("### Accessibility across the study area")
    st.caption("Higher SDW-2SFCA score = more modeled access to nearby facilities. "
               "Hover over a block or facility for details; click a block to outline it.")
    prefix = cfg["prefix"]
    search_key = f"block_search_{prefix}"
    clicked_key = f"block_clicked_{prefix}"
    nonce_key = f"map_nonce_{prefix}"
    st.session_state.setdefault(nonce_key, 0)

    def reset_map_selection():
        # A new search replaces any clicked block; a fresh chart key also clears the
        # chart's own selection so it can re-centre on the searched block.
        st.session_state.pop(clicked_key, None)
        st.session_state[nonce_key] += 1

    search_col, basemap_col, toggle_col = st.columns([3, 1.6, 1], vertical_alignment="bottom")
    block_query = search_col.text_input(
        "Find a census block",
        key=search_key,
        on_change=reset_map_selection,
        placeholder="15-digit block GEOID, or a tract / block-group prefix",
        help="Enter a full census block GEOID (e.g. from the Left behind table or a hover "
             "card) to zoom to it. An 11-digit tract or 12-digit block-group ID lists its blocks.",
    )
    basemap = BASEMAPS[basemap_col.selectbox("Basemap", list(BASEMAPS), key="map_basemap")]
    show_facilities = toggle_col.checkbox(
        "Show facilities", value=True, key="show_facilities",
        disabled=facilities_gdf.empty,
        help="Show study facility locations and recorded supply, not real-time availability.",
    )

    if facilities_gdf.empty:
        st.warning("Facility data is unavailable. Nearby counts and nearest distances cannot be calculated.")
    try:
        map_blocks = build_block_details(
            scores_gdf, facilities_gdf, cfg["crs"], cfg["catchment_m"]
        )
        map_blocks["populated"] = populated_mask(map_blocks)
        color_scale = build_color_scale(
            map_blocks.loc[map_blocks["populated"], "accessibility_score"].to_numpy()
        )
    except ValueError as exc:
        st.error(f"Cannot prepare block map details: {exc}")
        return
    map_blocks["facility_count_label"] = map_blocks["nearby_facilities"].map(
        lambda count: "Unavailable" if pd.isna(count) else f"{count:,}"
    )
    map_blocks["nearest_distance_label"] = map_blocks["nearest_facility_m"].map(
        lambda distance: "Unavailable" if pd.isna(distance) else f"{distance:,.0f} m"
    )

    searched_geoid = None
    if block_query.strip():
        search_limit = 50
        matches = search_blocks(map_blocks["GEOID"], block_query, limit=search_limit + 1)
        if not matches:
            st.warning(f"No census block in this study matches '{block_query.strip()}'.")
        elif len(matches) == 1:
            searched_geoid = matches[0]
        else:
            note = (f" (first {search_limit} shown — type more digits to narrow)"
                    if len(matches) > search_limit else "")
            searched_geoid = st.selectbox(
                f"Blocks starting with {''.join(c for c in block_query if c.isdigit())}{note}",
                matches[:search_limit],
                key=f"block_pick_{prefix}",
                on_change=reset_map_selection,
            )
    clicked_geoid = st.session_state.get(clicked_key)
    if clicked_geoid not in set(map_blocks["GEOID"]):
        clicked_geoid = None
    selected_geoid = clicked_geoid or searched_geoid
    if selected_geoid is not None:
        block = map_blocks.loc[map_blocks["GEOID"] == selected_geoid].iloc[0]
        scores = map_blocks.loc[map_blocks["populated"], "accessibility_score"]
        def clear_selection():
            st.session_state[search_key] = ""
            reset_map_selection()

        title_col, clear_col = st.columns([4, 1], vertical_alignment="center")
        title_col.markdown(f"**Census block {selected_geoid}**"
                           + (" · selected on map" if clicked_geoid else ""))
        clear_col.button("Clear selection", key=f"clear_block_{prefix}",
                         on_click=clear_selection, width="stretch")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric(
            "SDW-2SFCA score", f"{block['accessibility_score']:.4g}",
            help="Share of study blocks with a lower score is shown below the value.",
        )
        if block["populated"]:
            m1.caption(f"Higher than {(scores < block['accessibility_score']).mean():.0%} "
                       "of blocks with residents")
        else:
            m1.caption("No residents · not counted in study statistics")
        m2.metric("Population", f"{block['population']:,.0f}")
        m3.metric(f"Facilities within {cfg['catchment_m']:,} m", block["facility_count_label"])
        m4.metric("Nearest study facility", block["nearest_distance_label"])

    if color_scale.capped:
        scale_summary = (
            f"Scores above 0 are colored on a 95th-percentile scale "
            f"(cap {color_scale.upper:,.5g}+). Blocks with no access are shown in orange."
        )
        scale_basis = "the 95th percentile of blocks with residents"
        scale_explanation = (
            f"Colors span 0–{color_scale.upper:,.5g} ({scale_basis}). "
            f"Scores at or above {color_scale.upper:,.5g} share the highest color, "
            "marked + on the legend. Hover cards retain the actual score."
        )
    else:
        scale_summary = "Scores above 0 use full-range colors. Blocks with no access are shown in orange."
        scale_explanation = (
            "The 95th-percentile scale uses the full range because the cutoff is zero "
            "or no scores exceed it."
        )
    n_empty = int((~map_blocks["populated"]).sum())
    if n_empty:
        scale_summary += f" Grey blocks ({n_empty:,}) have no residents."
    st.caption(scale_summary)

    # Light simplification (~1 m) keeps the map payload small without visible change.
    scores_4326 = map_blocks.to_crs("EPSG:4326")
    scores_4326["geometry"] = scores_4326.geometry.simplify(1e-5, preserve_topology=True)
    center = map_blocks.to_crs(cfg["crs"]).geometry.centroid.to_crs("EPSG:4326")
    hover_columns = ["GEOID", "accessibility_score", "population",
                     "facility_count_label", "nearest_distance_label"]
    block_hover = (
        "<b>Census block %{customdata[0]}</b><br>"
        "SDW-2SFCA score: %{customdata[1]:.4g}<br>"
        "Population: %{customdata[2]:,}<br>"
        f"Facilities within {cfg['catchment_m']:,} m: %{{customdata[3]}}<br>"
        "Nearest study facility: %{customdata[4]}<extra></extra>"
    )

    def block_trace(blocks, **kwargs):
        return go.Choroplethmap(
            geojson=blocks[["GEOID", "geometry"]].__geo_interface__,
            featureidkey="properties.GEOID",
            locations=blocks["GEOID"],
            customdata=blocks[hover_columns].to_numpy(),
            hovertemplate=block_hover,
            marker=dict(opacity=0.75, line=dict(width=0.2, color="rgba(255,255,255,0.7)")),
            selected=dict(marker=dict(opacity=0.75)),
            unselected=dict(marker=dict(opacity=0.75)),
            **kwargs,
        )

    fig = go.Figure()
    # Empty blocks are scored like any other but have no one to serve, so they are
    # drawn grey rather than as no access or as well served.
    populated = scores_4326["populated"]
    if (~populated).any():
        fig.add_trace(block_trace(
            scores_4326[~populated],
            z=np.zeros(int((~populated).sum())),
            colorscale=[[0, NO_RESIDENTS_COLOR], [1, NO_RESIDENTS_COLOR]],
            showscale=False,
            showlegend=True,
            name="No residents",
        ))
    no_access = populated & (scores_4326["accessibility_score"] == 0)
    if no_access.any():
        fig.add_trace(block_trace(
            scores_4326[no_access],
            z=np.zeros(int(no_access.sum())),
            colorscale=[[0, NO_ACCESS_COLOR], [1, NO_ACCESS_COLOR]],
            showscale=False,
            showlegend=True,
            name="No access (score 0)",
        ))
    has_access = populated & ~no_access
    if has_access.any():
        fig.add_trace(block_trace(
            scores_4326[has_access],
            z=scores_4326.loc[has_access, "accessibility_score"].clip(upper=color_scale.upper),
            zmin=0,
            zmax=color_scale.upper,
            colorscale=MAP_PALETTE,
            showlegend=False,
            colorbar=dict(
                title="SDW-2SFCA score",
                tickmode="array",
                tickvals=color_scale.ticks,
                ticktext=color_scale.labels,
            ),
        ))
    if show_facilities and not facilities_gdf.empty:
        facility_points = facilities_gdf.to_crs(cfg["crs"]).geometry.centroid.to_crs("EPSG:4326")
        names = (
            facilities_gdf["FAC_NAME"].fillna("Unnamed facility").astype(str).map(escape)
            if "FAC_NAME" in facilities_gdf
            else pd.Series("Unnamed facility", index=facilities_gdf.index)
        )
        supply = (
            pd.to_numeric(facilities_gdf["supply"], errors="coerce")
            if "supply" in facilities_gdf
            else pd.Series(np.nan, index=facilities_gdf.index)
        )
        supply_labels = supply.map(
            lambda value: "Unavailable" if pd.isna(value) else f"{value:,.5g}"
        )
        fig.add_trace(go.Scattermap(
            lat=facility_points.y,
            lon=facility_points.x,
            mode="markers",
            marker=dict(size=5, color=basemap["facility"], opacity=0.9),
            selected=dict(marker=dict(opacity=0.9)),
            unselected=dict(marker=dict(opacity=0.9)),
            name="Study facilities",
            customdata=np.column_stack([names, supply_labels]),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                f"{cfg['facility']}<br>"
                f"Recorded supply ({cfg['supply_label']}): %{{customdata[1]}}"
                "<extra>Study facility</extra>"
            ),
        ))

    block_curves = list(range(len(fig.data) - (1 if show_facilities and not facilities_gdf.empty else 0)))
    map_center = {"lat": center.y.mean(), "lon": center.x.mean()}
    map_zoom = 10
    if selected_geoid is not None:
        selected = scores_4326[scores_4326["GEOID"] == selected_geoid]
        fig.add_trace(block_trace(
            selected,
            z=[0],
            colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]],
            showscale=False,
            showlegend=True,
            name="Selected block",
        ))
        fig.data[-1].marker.update(opacity=1, line=dict(width=3, color=basemap["outline"]))
        fig.data[-1].update(selected=dict(marker=dict(opacity=1)),
                            unselected=dict(marker=dict(opacity=1)))
        block_curves.append(len(fig.data) - 1)
    if selected_geoid is not None:
        selected_center = center[map_blocks["GEOID"] == selected_geoid].iloc[0]
        map_center = {"lat": selected_center.y, "lon": selected_center.x}
        map_zoom = block_zoom(tuple(selected.total_bounds))

    fig.update_layout(
        map=dict(
            style=basemap["style"],
            layers=basemap.get("layers", []),
            center=map_center,
            zoom=map_zoom,
        ),
        height=650,
        margin=dict(l=0, r=0, t=10, b=0),
        font=dict(family="Arial, sans-serif", color="#172b3a"),
        paper_bgcolor="white",
        # Streamlit remounts the chart whenever the figure changes, so the view is set
        # explicitly: centred on the selected block, otherwise the whole study.
        uirevision=f"{prefix}-{selected_geoid}",
        clickmode="event+select",
        legend=dict(orientation="h", y=1.02, x=0),
    )

    chart_key = f"access_map_{prefix}_{st.session_state[nonce_key]}"

    def on_block_click():
        points = st.session_state[chart_key]["selection"]["points"]
        geoids = [_clicked_geoid(point) for point in points
                  if point.get("curve_number") in block_curves]
        geoids = [g for g in geoids if g]
        if geoids:
            st.session_state[clicked_key] = geoids[-1]
        elif not points:
            # Streamlit reports an empty selection when the chart's selection is reset.
            st.session_state.pop(clicked_key, None)

    st.plotly_chart(fig, key=chart_key, on_select=on_block_click, selection_mode="points")
    with st.expander("About this map", expanded=False):
        st.markdown(
            "**Score.** The SDW-2SFCA score (Spatial Distance-Weighted Two-Step Floating "
            "Catchment Area) models facility supply, competing demand, and distance. "
            "Higher means more modeled access; it is not a facility count or percentage."
        )
        st.markdown(
            f"**Colors.** {scale_explanation} Orange blocks have residents but no modeled "
            "access (score 0). Grey blocks have no residents; the model still scores them, "
            "but they are left out of the study statistics. Colors are scaled within each "
            "study, so they are not comparable between cities."
        )
        st.markdown(
            f"**Study.** {cfg['city']} — {cfg['facility']}, with a "
            f"{cfg['catchment_m']:,} m catchment measured from each block centroid. "
            "Distances are straight-line, not walking or driving routes."
        )
        st.markdown(
            "**Limits.** Proximity does not guarantee available capacity or eligibility. "
            "Recorded facility supply is not live availability; for FQHCs it counts sites, "
            "not treatment capacity."
        )

def render_inequality_tab(scores_gdf, gini):
    """Render inequality analysis with Lorenz curve."""
    st.markdown("### How evenly is access distributed?")
    
    scores = scores_gdf["accessibility_score"].values

    # Lorenz Curve
    cum_b, cum_a = create_lorenz_data(scores)
    
    fig = go.Figure()
    
    # Perfect equality line
    fig.add_trace(go.Scatter(
        x=[0, 1], y=[0, 1],
        mode='lines',
        line=dict(dash='dash', color='#9ca3af', width=2),
        name='Perfect Equality'
    ))
    
    # Actual distribution
    fig.add_trace(go.Scatter(
        x=cum_b, y=cum_a,
        mode='lines',
        line=dict(color='#087f78', width=3),
        fill='tonexty',
        fillcolor='rgba(8, 127, 120, 0.12)',
        name='SDW-2SFCA Distribution'
    ))
    
    fig.update_layout(
        title=dict(
            text=f"<b>Lorenz curve · Gini {gini:.4f}</b>",
            font=dict(size=18, color="#374151"),
            x=0.5,
            xanchor="center"
        ),
        xaxis_title="Cumulative Share of Census Blocks with Residents",
        yaxis_title="Cumulative Share of Accessibility",
        height=600,
        font=dict(family="Arial, sans-serif", color="#172b3a"),
        plot_bgcolor='#fafafa',
        paper_bgcolor='white',
    )
    
    st.plotly_chart(fig)
    
    st.markdown(f"""
    <div class='info-card'>
        <strong>Understanding the index</strong><br>
        The Gini coefficient is <strong>{gini:.4f}</strong>, calculated across census blocks
        with residents, each block counted equally. It is the area between the curve above
        and the line of perfect equality, doubled.
        A value closer to 0 indicates more equal access distribution,
        while closer to 1 indicates high inequality.
    </div>
    """, unsafe_allow_html=True)
    
    # Distribution histogram
    st.markdown("#### Score Distribution")

    # Zeros and a long upper tail would flatten the chart, so they are reported
    # in the caption instead of plotted.
    zero_blocks = int((scores == 0).sum())
    positive = scores[scores > 0]
    cap = float(np.percentile(scores, 95)) if (scores > 0).any() else 0.0
    if cap == 0:
        cap = float(scores.max())
    shown = positive[positive <= cap]
    above_cap = int((positive > cap).sum())

    fig_hist = go.Figure()
    fig_hist.add_trace(go.Histogram(
        x=shown,
        nbinsx=40,
        marker=dict(color='#087f78', opacity=0.8),
        name="Accessibility Scores"
    ))
    
    fig_hist.update_layout(
        xaxis_title="Accessibility Score",
        yaxis_title="Number of Census Blocks",
        height=400,
        font=dict(family="Arial, sans-serif", color="#172b3a"),
        plot_bgcolor='#fafafa',
        paper_bgcolor='white',
    )
    
    st.plotly_chart(fig_hist)
    st.caption(
        f"Shows the {len(shown):,} blocks with residents scoring above 0 up to {cap:,.5g} "
        f"(the 95th percentile). Not shown: {zero_blocks:,} blocks with a score of 0 "
        f"({zero_blocks / len(scores):.0%}) and {above_cap:,} blocks above {cap:,.5g}."
    )

_TIER_WORDS = {"low": "Low", "medium": "Medium", "high": "High"}


def _bivariate_label(key: str) -> str:
    """Display name for a density_access class, using the cell names where set."""
    if key in BIVARIATE_NAMED:
        name, description = BIVARIATE_NAMED[key]
        return f"{name} ({description.lower()})"
    density, access = key.split("_")
    return f"{_TIER_WORDS[density]} density · {access} access"


def _bivariate_legend_html() -> str:
    """3x3 colour grid (access up, density across) plus the named cells."""
    cells = "".join(
        f"<div style='background:{BIVARIATE_COLORS[f'{d}_{a}']};aspect-ratio:1'></div>"
        for a in ("high", "medium", "low") for d in ("low", "medium", "high")
    )
    corners = "".join(
        f"<div style='display:flex;gap:.5rem;align-items:flex-start;margin-top:.45rem'>"
        f"<span style='flex:none;width:.9rem;height:.9rem;margin-top:.15rem;"
        f"background:{BIVARIATE_COLORS[key]};border:1px solid #9aa5b1'></span>"
        f"<span><strong>{name}</strong><br><span style='color:#526779'>{description}</span></span></div>"
        for key, (name, description) in BIVARIATE_NAMED.items()
    )
    return (
        "<div style='font-size:.85rem;line-height:1.3'>"
        "<div style='display:grid;grid-template-columns:auto 1fr;gap:.35rem;align-items:center'>"
        "<div style='writing-mode:vertical-rl;transform:rotate(180deg);font-weight:600'>Access →</div>"
        f"<div style='display:grid;grid-template-columns:repeat(3,1fr);gap:2px;max-width:9rem'>{cells}</div>"
        "<div></div><div style='font-weight:600'>Density →</div></div>"
        f"{corners}</div>"
    )


def render_left_behind_tab(scores_gdf, facilities_gdf, cfg):
    """Dense blocks left behind (isolated or diluted), on a density × access bivariate map."""
    st.markdown("### Who gets left behind?")
    st.caption("Blocks with residents, split by population density and SDW-2SFCA access. "
               "Each tier holds about a third of the study's residents.")
    try:
        classes = classify_bivariate(scores_gdf, cfg["crs"])
    except ValueError as exc:
        st.error(f"Cannot classify blocks: {exc}")
        return
    blocks = scores_gdf.loc[classes.index].join(classes)
    left = blocks[blocks["bivariate_class"].isin(LEFT_BEHIND)]
    isolated = left["bivariate_class"] == ISOLATED

    total_pop = int(blocks["population"].sum())
    left_pop = int(left["population"].sum())
    isolated_pop = int(left.loc[isolated, "population"].sum())
    share = lambda n: f"{n / total_pop:.1%} of residents" if total_pop else None
    col1, col2, col3 = st.columns(3)
    col1.metric("Residents left behind", f"{left_pop:,}", share(left_pop), delta_color="off",
                help="Residents of the densest third of blocks that are isolated or diluted.")
    col2.metric("Isolated", f"{isolated_pop:,}", share(isolated_pop), delta_color="off",
                help="Dense blocks with no facility within reach. Any catchment-based method finds the same blocks.")
    col3.metric("Diluted", f"{left_pop - isolated_pop:,}", share(left_pop - isolated_pop), delta_color="off",
                help="Dense blocks with a facility nearby but access in the lower half of blocks with any "
                     "(population-weighted). Only a method that models competition for supply, like "
                     "SDW-2SFCA, can see these.")
    st.markdown(f"""
    <div class='warning-card'>
        <strong>Left behind</strong> means dense blocks — where the most people live — that are
        <strong>isolated</strong> (no facility within {cfg['catchment']}) or
        <strong>diluted</strong> (a facility nearby, but its supply stretched by the demand around it).
        It is a screening view, not a ranking of health need, which the model does not measure.
    </div>
    """, unsafe_allow_html=True)

    blocks_4326 = blocks.to_crs("EPSG:4326")
    blocks_4326["geometry"] = blocks_4326.geometry.simplify(1e-5, preserve_topology=True)
    center = blocks.to_crs(cfg["crs"]).geometry.centroid.to_crs("EPSG:4326")
    basemap = BASEMAPS[st.session_state.get("map_basemap", next(iter(BASEMAPS)))]
    fig = go.Figure()
    for key, colour in BIVARIATE_COLORS.items():
        subset = blocks_4326[blocks_4326["bivariate_class"] == key]
        if subset.empty:
            continue
        label = _bivariate_label(key)
        fig.add_trace(go.Choroplethmap(
            geojson=subset[["GEOID", "geometry"]].__geo_interface__,
            featureidkey="properties.GEOID",
            locations=subset["GEOID"],
            z=np.zeros(len(subset)),
            colorscale=[[0, colour], [1, colour]],
            showscale=False,
            name=label,
            customdata=subset[["GEOID", "population", "density", "accessibility_score"]].to_numpy(),
            hovertemplate=(
                "<b>Census block %{customdata[0]}</b><br>"
                f"{label}<br>"
                "Population: %{customdata[1]:,}<br>"
                "Residents per km²: %{customdata[2]:,.0f}<br>"
                "SDW-2SFCA score: %{customdata[3]:.4g}<extra></extra>"
            ),
            marker=dict(opacity=0.85, line=dict(width=0.2, color="rgba(255,255,255,0.7)")),
        ))
    fig.update_layout(
        map=dict(style=basemap["style"], layers=basemap.get("layers", []),
                 center={"lat": center.y.mean(), "lon": center.x.mean()}, zoom=10),
        height=600, margin=dict(l=0, r=0, t=10, b=0), showlegend=False,
        font=dict(family="Arial, sans-serif", color="#172b3a"), paper_bgcolor="white",
    )
    map_col, legend_col = st.columns([4, 1.2])
    map_col.plotly_chart(fig, key=f"left_behind_map_{cfg['prefix']}")
    legend_col.markdown(_bivariate_legend_html(), unsafe_allow_html=True)
    st.caption("Blocks with no residents are not shown. Density tiers are population-weighted thirds; "
               "access is none, or the lower or upper half of blocks with access. Tiers are set within "
               "this study, so colours are not comparable between cities.")

    st.markdown("#### Left-behind blocks, most residents first")
    try:
        details = build_block_details(left, facilities_gdf, cfg["crs"], cfg["catchment_m"])
        nearest = details["nearest_facility_m"]
    except ValueError:
        nearest = pd.Series(np.nan, index=left.index)
    table = pd.DataFrame({
        "Census Block GEOID": left["GEOID"].astype(str),
        "Pathway": np.where(isolated, "Isolated", "Diluted"),
        "Population": left["population"].astype(int),
        "Residents per km²": left["density"].round(0).astype(int),
        "Nearest study facility (m)": nearest.round(0),
    }).sort_values("Population", ascending=False)
    st.dataframe(table.head(30), height=400, hide_index=True)
    st.download_button(
        label=f"Download all {len(table):,} left-behind blocks (CSV)",
        data=table.to_csv(index=False),
        file_name=f"{cfg['prefix']}_left_behind_blocks.csv",
        mime="text/csv",
    )

def render_export_tab(scores_gdf, cfg):
    """Render export options."""
    st.markdown("### Take the analysis further")
    
    # Summary statistics
    stats = {
        "Total Census Blocks": len(scores_gdf),
        "Total Population": int(scores_gdf["population"].sum()),
        "Mean Accessibility Score": scores_gdf["accessibility_score"].mean(),
        "Median Accessibility Score": scores_gdf["accessibility_score"].median(),
        "Zero Access Blocks": int((scores_gdf["accessibility_score"] == 0).sum()),
    }
    
    st.markdown("#### Summary statistics")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Total Blocks:** {stats['Total Census Blocks']:,}")
        st.markdown(f"**Total Population:** {stats['Total Population']:,}")
        st.markdown(f"**Mean Score:** {stats['Mean Accessibility Score']:.3f}")
    
    with col2:
        st.markdown(f"**Median Score:** {stats['Median Accessibility Score']:.3f}")
        st.markdown(f"**Zero Access Blocks:** {stats['Zero Access Blocks']:,}")
    
    # Export options
    st.markdown("#### Download options")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        <div class='success-card' style='text-align: center;'>
            <h4>CSV Format</h4>
            <p>Comma-separated values for Excel and data analysis</p>
        </div>
        """, unsafe_allow_html=True)
        
        csv = scores_gdf.drop(columns=['geometry']).to_csv(index=False)
        st.download_button(
            label="Download CSV",
            data=csv,
            file_name=f"{cfg['prefix']}_accessibility_scores.csv",
            mime="text/csv",
            width="stretch",
        )
    
    with col2:
        st.markdown("""
        <div class='success-card' style='text-align: center;'>
            <h4>GeoJSON Format</h4>
            <p>Geographic data for GIS applications</p>
        </div>
        """, unsafe_allow_html=True)
        
        geojson = scores_gdf.to_crs("EPSG:4326").to_json()
        st.download_button(
            label="Download GeoJSON",
            data=geojson,
            file_name=f"{cfg['prefix']}_accessibility_scores.geojson",
            mime="application/geo+json",
            width="stretch",
        )

def render_footer():
    """Render professional footer with credits."""
    st.markdown(f"""
    <div class='dashboard-footer'>
        <p><strong>About the analysis</strong><br>
            Spatial Distance-Weighted Two-Step Floating Catchment Area (SDW-2SFCA).
            Euclidean distance with Gaussian decay. Data: 2020 Census blocks and CMS facility locations.
            Blocks with no residents are shown grey and left out of the statistics.
        </p>
        <p>© 2026 CareScape &middot;
            <a href='https://github.com/UshashiP'>Ushashi Podder</a>
        </p>
    </div>
    """, unsafe_allow_html=True)

# ── Run Application ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
