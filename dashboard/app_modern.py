"""
Healthcare Access Intelligence Dashboard - Modern Streamlit Version
--------------------------------------------------------------------
Beautiful, intuitive interface for SDW-2SFCA analysis

Run: streamlit run dashboard/app_modern.py
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

# ── Page Configuration ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Healthcare Access Intelligence",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Modern UI Styling ──────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

/* Global Styles */
* {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

.stApp {
    background: #f8fafc;
}

.main > div {
    background: white;
    border-radius: 16px;
    padding: 1rem 1.5rem;
    margin: 0.5rem;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
}

/* Header */
h1 {
    font-size: 1.6rem;
    font-weight: 700;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 0.25rem;
    margin-top: 0.25rem;
}

h2 {
    font-size: 1.5rem;
    font-weight: 700;
    color: #374151;
    margin-top: 0.75rem;
    margin-bottom: 0.5rem;
}

h3 {
    font-size: 1.1rem;
    font-weight: 600;
    color: #4b5563;
    margin-top: 0.5rem;
    margin-bottom: 0.5rem;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #667eea 0%, #764ba2 100%);
    padding: 2rem 1rem;
}

[data-testid="stSidebar"] h2 {
    color: #ffffff !important;
    font-weight: 700;
}

[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] div {
    color: #ffffff !important;
}

[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stRadio label {
    font-weight: 600;
    font-size: 0.9rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #ffffff !important;
}

[data-testid="stSidebar"] .stSelectbox > div > div {
    background: #1f2937 !important;
    border: 2px solid rgba(255, 255, 255, 0.3) !important;
    color: #ffffff !important;
}

[data-testid="stSidebar"] .stSelectbox input {
    color: #ffffff !important;
}

[data-testid="stSidebar"] [data-baseweb="select"] > div {
    background: #1f2937 !important;
    color: #ffffff !important;
}

[data-testid="stSidebar"] [data-baseweb="select"] input {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
}

[data-testid="stSidebar"] [data-baseweb="popover"] {
    background: #1f2937 !important;
}

[data-testid="stSidebar"] ul[role="listbox"] {
    background: #1f2937 !important;
}

[data-testid="stSidebar"] li[role="option"] {
    background: #1f2937 !important;
    color: #ffffff !important;
}

[data-testid="stSidebar"] li[role="option"]:hover {
    background: #374151 !important;
    color: #ffffff !important;
}

[data-testid="stSidebar"] .stAlert {
    background: rgba(255, 255, 255, 0.15) !important;
    border: 1px solid rgba(255, 255, 255, 0.3) !important;
    color: #ffffff !important;
}

[data-testid="stSidebar"] .stMarkdown {
    color: #ffffff !important;
}

[data-testid="stSidebar"] hr {
    border-color: rgba(255, 255, 255, 0.3) !important;
}

/* Metrics */
[data-testid="stMetricValue"] {
    font-size: 2rem;
    font-weight: 700;
}

[data-testid="stMetricLabel"] {
    font-size: 0.875rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #6b7280 !important;
}

div[data-testid="metric-container"] {
    background: linear-gradient(135deg, #f9fafb 0%, #f3f4f6 100%);
    border: 2px solid #e5e7eb;
    border-radius: 16px;
    padding: 1.5rem;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
    transition: all 0.3s;
}

div[data-testid="metric-container"]:hover {
    transform: translateY(-4px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.1);
}

/* Buttons */
.stButton button {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border: none;
    border-radius: 12px;
    padding: 0.75rem 2rem;
    font-weight: 600;
    font-size: 1rem;
    transition: all 0.3s;
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
}

.stButton button:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
}

.stTabs [data-baseweb="tab"] {
    border-radius: 12px;
    padding: 0.75rem 1.5rem;
    font-weight: 600;
    background: transparent;
    border: 2px solid transparent;
}

.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white !important;
}

/* Alerts */
.stAlert {
    border-radius: 12px;
    border: none;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

/* Cards */
.info-card {
    background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
    border: 2px solid #93c5fd;
    border-radius: 12px;
    padding: 0.75rem 1rem;
    margin: 0.5rem 0;
}

.warning-card {
    background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
    border: 2px solid #fbbf24;
    border-radius: 12px;
    padding: 0.75rem 1rem;
    margin: 0.5rem 0;
}

.success-card {
    background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%);
    border: 2px solid #34d399;
    border-radius: 12px;
    padding: 0.75rem 1rem;
    margin: 0.5rem 0;
}

/* Expander */
.streamlit-expanderHeader {
    border-radius: 12px;
    background: #f9fafb;
    font-weight: 600;
}

/* Dataframe */
[data-testid="stDataFrame"] {
    border-radius: 12px;
    overflow: hidden;
}

</style>
""", unsafe_allow_html=True)

# ── Data Configuration ─────────────────────────────────────────────────────────
CITIES = {
    "Washington DC — ICF Facilities": {
        "prefix": "dc_icf",
        "crs": "EPSG:26985",
        "facility": "Intermediate Care Facilities",
        "supply_label": "certified beds",
        "color": "#667eea",
        "catchment": "900m",
    },
    "New York City — Dialysis Centers": {
        "prefix": "ny_dialysis",
        "crs": "EPSG:32618",
        "facility": "Dialysis Centers",
        "supply_label": "dialysis stations",
        "color": "#10b981",
        "catchment": "1,200m",
    },
    "Los Angeles — FQHCs": {
        "prefix": "ca_fqhc",
        "crs": "EPSG:32611",
        "facility": "Federally Qualified Health Centers",
        "supply_label": "FQHC sites",
        "color": "#f59e0b",
        "catchment": "1,600m",
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
        return gpd.read_parquet(path)
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

def create_lorenz_data(scores: np.ndarray, population: np.ndarray):
    """Generate Lorenz curve coordinates."""
    order = np.argsort(scores)
    s, p = scores[order], population[order].astype(float)
    cum_p = np.cumsum(p) / p.sum()
    cum_a = np.cumsum(s * p)
    if cum_a[-1] > 0:
        cum_a = cum_a / cum_a[-1]
    return np.concatenate([[0], cum_p]), np.concatenate([[0], cum_a])

# ── Main Application ───────────────────────────────────────────────────────────
def main():
    # ═══ TOP SECTION: Header ═══
    st.markdown("""
    <div style='background: white; 
                border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; text-align: center;
                border: 2px solid #e5e7eb;'>
        <h1 style='color: #000000; margin: 0; font-size: 2.4rem; font-weight: 700;'>
            🏥 Healthcare Intelligence App
        </h1>
        <p style='color: #4b5563; margin: 0.5rem 0 0 0; font-size: 0.95rem;'>
            Spatial Distance-Weighted Two-Step Floating Catchment Area (SDW-2SFCA) Analysis
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar Controls
    with st.sidebar:
        st.markdown("""
        <h2 style='text-align: center; margin-bottom: 1.5rem; font-size: 1.5rem;'>
            🎯 Analysis Controls
        </h2>
        """, unsafe_allow_html=True)
        
        st.markdown("<hr style='margin: 1rem 0; border-color: rgba(255, 255, 255, 0.3);'>", unsafe_allow_html=True)
        
        city_key = st.selectbox(
            "📍 SELECT CITY & FACILITY TYPE",
            options=list(CITIES.keys()),
            index=0
        )
        
        cfg = CITIES[city_key]
        
        st.markdown("<hr style='margin: 1.5rem 0; border-color: rgba(255, 255, 255, 0.3);'>", unsafe_allow_html=True)
        
        st.markdown("""
        <div style='background: rgba(255, 255, 255, 0.15); border-radius: 12px; padding: 1.25rem; border: 1px solid rgba(255, 255, 255, 0.3);'>
            <h3 style='color: white; font-size: 1rem; margin-bottom: 1rem; text-transform: uppercase; letter-spacing: 0.05em;'>
                📊 Analysis Details
            </h3>
        """, unsafe_allow_html=True)
        
        st.markdown(f"""
        <p style='margin: 0.5rem 0; color: white;'><strong>Facility Type:</strong><br>{cfg['facility']}</p>
        <p style='margin: 0.5rem 0; color: white;'><strong>Catchment Radius:</strong><br>{cfg['catchment']}</p>
        <p style='margin: 0.5rem 0; color: white;'><strong>Method:</strong><br>SDW-2SFCA (Enhanced)</p>
        """, unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    # Load Data
    scores_gdf = load_scores(cfg["prefix"])
    facilities_gdf = load_facilities(cfg["prefix"])
    
    if scores_gdf.empty:
        st.error("❌ Could not load data. Please check file paths.")
        return
    
    # Compute Statistics
    scores = scores_gdf["accessibility_score"].values
    population = scores_gdf["population"].values
    gini = compute_gini(scores)
    
    zero_access_pct = (scores == 0).mean() * 100
    zero_access_pop = int(scores_gdf.loc[scores == 0, "population"].sum())
    
    # ═══ Quick Stats Bar ═══
    st.markdown("""
    <div style='background: #f8fafc; border-radius: 8px; padding: 0.75rem 1rem; margin-bottom: 1rem; 
                display: flex; justify-content: space-around; border: 1px solid #e2e8f0;'>
        <div style='text-align: center;'>
            <div style='font-size: 1.5rem; font-weight: 700; color: #667eea;'>{:,}</div>
            <div style='font-size: 0.75rem; color: #64748b; text-transform: uppercase;'>Census Blocks</div>
        </div>
        <div style='text-align: center;'>
            <div style='font-size: 1.5rem; font-weight: 700; color: #10b981;'>{:,}</div>
            <div style='font-size: 0.75rem; color: #64748b; text-transform: uppercase;'>Facilities</div>
        </div>
        <div style='text-align: center;'>
            <div style='font-size: 1.5rem; font-weight: 700; color: #ef4444;'>{:.1f}%</div>
            <div style='font-size: 0.75rem; color: #64748b; text-transform: uppercase;'>Zero Access</div>
        </div>
        <div style='text-align: center;'>
            <div style='font-size: 1.5rem; font-weight: 700; color: #f59e0b;'>{:.3f}</div>
            <div style='font-size: 0.75rem; color: #64748b; text-transform: uppercase;'>Gini Index</div>
        </div>
    </div>
    """.format(len(scores_gdf), len(facilities_gdf), zero_access_pct, gini), unsafe_allow_html=True)
    
    # ═══ BODY SECTION: Main Content ═══
    tab1, tab2, tab3, tab4 = st.tabs(["🗺️ Interactive Map", "📊 Inequality Analysis", "🎯 Priority Zones", "📥 Export Data"])
    
    with tab1:
        render_map_tab(scores_gdf, facilities_gdf, cfg)
    
    with tab2:
        render_inequality_tab(scores_gdf, gini)
    
    with tab3:
        render_priority_tab(scores_gdf)
    
    with tab4:
        render_export_tab(scores_gdf)
    
    # ═══ BOTTOM SECTION: Footer ═══
    st.markdown("<div style='margin-top: 2rem;'></div>", unsafe_allow_html=True)
    render_footer()

# ── Tab Renderers ──────────────────────────────────────────────────────────────
def render_map_tab(scores_gdf, facilities_gdf, cfg):
    """Render interactive map visualization."""
    st.markdown("<h3 style='margin-top: 0; margin-bottom: 0.5rem;'>🗺️ Accessibility Distribution Map</h3>", unsafe_allow_html=True)
    
    st.markdown("""
    <div class='info-card' style='margin-top: 0.5rem; margin-bottom: 0.75rem;'>
        <strong>ℹ️ How to Read:</strong> Colors represent accessibility scores. 
        Red/orange areas have lower access, yellow/green areas have higher access to healthcare facilities.
    </div>
    """, unsafe_allow_html=True)
    
    # Create Plotly choropleth
    scores_4326 = scores_gdf.to_crs("EPSG:4326")
    
    fig = px.choropleth_mapbox(
        scores_4326,
        geojson=scores_4326.geometry.__geo_interface__,
        locations=scores_4326.index,
        color="accessibility_score",
        color_continuous_scale=[[0, '#ef4444'], [0.3, '#f59e0b'], [0.6, '#fbbf24'], [0.85, '#a3e635'], [1, '#22c55e']],
        mapbox_style="open-street-map",
        center={"lat": scores_4326.geometry.centroid.y.mean(), 
                "lon": scores_4326.geometry.centroid.x.mean()},
        zoom=10,
        opacity=0.7,
        hover_data={"accessibility_score": ":.2f", "population": ":,"},
        labels={"accessibility_score": "Access Score"}
    )
    
    fig.update_layout(
        height=650,
        margin=dict(l=0, r=0, t=10, b=0),
        font=dict(family="Inter, sans-serif")
    )
    
    st.plotly_chart(fig, use_container_width=True)

def render_inequality_tab(scores_gdf, gini):
    """Render inequality analysis with Lorenz curve."""
    st.markdown("### 📊 Inequality Analysis")
    
    scores = scores_gdf["accessibility_score"].values
    population = scores_gdf["population"].values
    
    # Lorenz Curve
    cum_p, cum_a = create_lorenz_data(scores, population)
    
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
        x=cum_p, y=cum_a,
        mode='lines',
        line=dict(color='#667eea', width=4),
        fill='tonexty',
        fillcolor='rgba(102, 126, 234, 0.2)',
        name='SDW-2SFCA Distribution'
    ))
    
    fig.update_layout(
        title=dict(
            text=f"<b>Lorenz Curve — Gini Coefficient: {gini:.4f}</b>",
            font=dict(size=18, color="#374151"),
            x=0.5,
            xanchor="center"
        ),
        xaxis_title="Cumulative Share of Population",
        yaxis_title="Cumulative Share of Accessibility",
        height=600,
        font=dict(family="Inter, sans-serif"),
        plot_bgcolor='#fafafa',
        paper_bgcolor='white',
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    st.markdown(f"""
    <div class='info-card'>
        <strong>📖 Interpretation:</strong><br>
        The Gini coefficient is <strong>{gini:.4f}</strong>. 
        A value closer to 0 indicates more equal access distribution, 
        while closer to 1 indicates high inequality.
    </div>
    """, unsafe_allow_html=True)
    
    # Distribution histogram
    st.markdown("#### Score Distribution")
    
    fig_hist = go.Figure()
    fig_hist.add_trace(go.Histogram(
        x=scores,
        nbinsx=50,
        marker=dict(color='#667eea', opacity=0.7),
        name="Accessibility Scores"
    ))
    
    fig_hist.update_layout(
        xaxis_title="Accessibility Score",
        yaxis_title="Number of Census Blocks",
        height=400,
        font=dict(family="Inter, sans-serif"),
        plot_bgcolor='#fafafa',
        paper_bgcolor='white',
    )
    
    st.plotly_chart(fig_hist, use_container_width=True)

def render_priority_tab(scores_gdf):
    """Render priority zones identification."""
    st.markdown("### 🎯 Priority Zone Identification")
    
    pop_median = scores_gdf["population"].median()
    score_median = scores_gdf["accessibility_score"].median()
    
    priority = scores_gdf[
        (scores_gdf["population"] > pop_median) &
        (scores_gdf["accessibility_score"] < score_median)
    ].sort_values("population", ascending=False)
    
    n_priority = len(priority)
    pop_affected = int(priority["population"].sum())
    
    # Priority Metrics
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric(
            label="🚨 Priority Blocks",
            value=f"{n_priority:,}",
            delta="High population, low access"
        )
    
    with col2:
        st.metric(
            label="👥 People Affected",
            value=f"{pop_affected:,}",
            delta="Need immediate attention"
        )
    
    st.markdown("""
    <div class='warning-card'>
        <strong>⚠️ Priority Criteria:</strong> Census blocks with above-median population 
        but below-median accessibility scores require immediate policy attention and resource allocation.
    </div>
    """, unsafe_allow_html=True)
    
    # Comparison visualization
    fig = go.Figure()
    
    fig.add_trace(go.Histogram(
        x=scores_gdf["accessibility_score"],
        nbinsx=50,
        name="All Blocks",
        marker=dict(color='#667eea', opacity=0.7)
    ))
    
    fig.add_trace(go.Histogram(
        x=priority["accessibility_score"],
        nbinsx=50,
        name="Priority Blocks",
        marker=dict(color='#ef4444', opacity=0.8)
    ))
    
    fig.update_layout(
        title="Accessibility Score Distribution Comparison",
        xaxis_title="Accessibility Score",
        yaxis_title="Number of Census Blocks",
        barmode='overlay',
        height=400,
        font=dict(family="Inter, sans-serif"),
        plot_bgcolor='#fafafa',
        paper_bgcolor='white',
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Top priority blocks table
    st.markdown("#### 📋 Top 30 Priority Census Blocks")
    
    display_df = priority[["GEOID", "population", "accessibility_score"]].head(30)
    display_df.columns = ["Census Block GEOID", "Population", "Accessibility Score"]
    
    st.dataframe(
        display_df,
        use_container_width=True,
        height=400
    )

def render_export_tab(scores_gdf):
    """Render export options."""
    st.markdown("### 📥 Export Analysis Results")
    
    # Summary statistics
    stats = {
        "Total Census Blocks": len(scores_gdf),
        "Total Population": int(scores_gdf["population"].sum()),
        "Mean Accessibility Score": scores_gdf["accessibility_score"].mean(),
        "Median Accessibility Score": scores_gdf["accessibility_score"].median(),
        "Zero Access Blocks": int((scores_gdf["accessibility_score"] == 0).sum()),
    }
    
    st.markdown("""
    <div class='info-card'>
        <h4>📊 Summary Statistics</h4>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Total Blocks:** {stats['Total Census Blocks']:,}")
        st.markdown(f"**Total Population:** {stats['Total Population']:,}")
        st.markdown(f"**Mean Score:** {stats['Mean Accessibility Score']:.3f}")
    
    with col2:
        st.markdown(f"**Median Score:** {stats['Median Accessibility Score']:.3f}")
        st.markdown(f"**Zero Access Blocks:** {stats['Zero Access Blocks']:,}")
    
    st.markdown("</div>", unsafe_allow_html=True)
    
    # Export options
    st.markdown("#### 💾 Download Options")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        <div class='success-card' style='text-align: center;'>
            <div style='font-size: 2.5rem; margin-bottom: 0.5rem;'>📄</div>
            <h4>CSV Format</h4>
            <p>Comma-separated values for Excel and data analysis</p>
        </div>
        """, unsafe_allow_html=True)
        
        csv = scores_gdf.drop(columns=['geometry']).to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name="accessibility_scores.csv",
            mime="text/csv",
            use_container_width=True
        )
    
    with col2:
        st.markdown("""
        <div class='success-card' style='text-align: center;'>
            <div style='font-size: 2.5rem; margin-bottom: 0.5rem;'>🗺️</div>
            <h4>GeoJSON Format</h4>
            <p>Geographic data for GIS applications</p>
        </div>
        """, unsafe_allow_html=True)
        
        geojson = scores_gdf.to_crs("EPSG:4326").to_json()
        st.download_button(
            label="📥 Download GeoJSON",
            data=geojson,
            file_name="accessibility_scores.geojson",
            mime="application/geo+json",
            use_container_width=True
        )

def render_footer():
    """Render professional footer with credits."""
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; padding: 1.5rem; background: #f8fafc; border-radius: 8px;'>
        <h3 style='color: #334155; font-size: 1.1rem; margin-bottom: 1rem;'>🏥 About This Dashboard</h3>
        <p style='color: #64748b; font-size: 0.9rem; line-height: 1.6; max-width: 800px; margin: 0 auto 1rem auto;'>
            Analyzes healthcare accessibility using Spatial Distance-Weighted Two-Step Floating Catchment Area (SDW-2SFCA) method 
            to identify underserved areas and guide policy decisions.
        </p>
        <p style='color: #94a3b8; font-size: 0.85rem;'>
            <strong>Data:</strong> 2020 Census blocks, CMS facility locations | 
            <strong>Distance:</strong> Euclidean with Gaussian decay
        </p>
        <hr style='border: none; border-top: 1px solid #e2e8f0; margin: 1rem 0;'>
        <p style='color: #64748b; font-size: 0.85rem; margin: 0.5rem 0;'>
            © 2026 Healthcare Intelligence App | 
            <a href='https://github.com/UshashiP' style='color: #667eea; text-decoration: none;'>Ushashi Poddar</a> | 
            Data sources: U.S. Census Bureau, CMS
        </p>
    </div>
    """, unsafe_allow_html=True)

# ── Run Application ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
