"""
Healthcare Access Equity Intelligence Dashboard
Streamlit Cloud deployment — reads pre-computed parquet files only.
No pipeline imports required.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import geopandas as gpd
import streamlit as st
import folium
from branca.colormap import LinearColormap
from pathlib import Path

st.set_page_config(
    page_title="Healthcare Access Equity Intelligence",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap');
:root{--accent:#3ec7a6;--accent-alt:#f2a65a;--text-main:#eef2f7;--text-soft:#a8b3c2}
.stApp{background:radial-gradient(circle at 15% 0%,#1a2230 0%,#0c0f14 42%,#090b10 100%);font-family:'IBM Plex Sans',sans-serif;color:var(--text-main)}
h1,h2,h3{font-family:'Space Grotesk',sans-serif;color:var(--text-main)}
p,span,label,div{color:var(--text-main)}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#121722 0%,#0d121a 100%);border-right:1px solid rgba(255,255,255,.08)}
div[data-baseweb="select"]>div{background:#1b222e!important;color:var(--text-main)!important;border-color:rgba(255,255,255,.2)!important}
div[data-baseweb="select"] input{color:var(--text-main)!important;-webkit-text-fill-color:var(--text-main)!important}
div[data-baseweb="popover"]{background:#1b222e!important;color:var(--text-main)!important}
ul[role="listbox"],[role="listbox"]{background:#1b222e!important}
ul[role="listbox"] li,[role="option"]{color:var(--text-main)!important;background:#1b222e!important}
ul[role="listbox"] li:hover,[role="option"]:hover{background:#253044!important}
[data-testid="stMetric"]{background:linear-gradient(160deg,rgba(30,38,52,.88) 0%,rgba(20,25,34,.9) 100%);border:1px solid rgba(62,199,166,.22);border-radius:14px;padding:.45rem .7rem;box-shadow:0 10px 28px rgba(0,0,0,.35)}
.stButton button{background:linear-gradient(90deg,var(--accent) 0%,var(--accent-alt) 100%);color:#071015;border:0;font-weight:700}
.insight-card{background:linear-gradient(150deg,rgba(20,25,34,.95) 0%,rgba(28,35,48,.92) 100%);border:1px solid rgba(242,166,90,.25);border-radius:12px;padding:.8rem .95rem;margin-bottom:.55rem}
.insight-title{color:#3ec7a6;font-weight:700;margin-bottom:.2rem}
.insight-body{color:#a8b3c2;font-size:.92rem;line-height:1.38}
</style>
""", unsafe_allow_html=True)

# ── Data config ────────────────────────────────────────────────────────────────
CITIES = {
    "Washington DC — ICF Facilities": {
        "scores":    "outputs/results/gold/run_date=2026-06-04/dc_icf_scores.parquet",
        "facilities":"outputs/results/silver/run_date=2026-06-04/dc_icf_facilities.parquet",
        "crs":       "EPSG:26985",
        "facility":  "Intermediate Care Facilities",
        "supply_label": "certified beds",
        "gini_std":  0.00,
        "color":     "#3ec7a6",
        "catchment": "900m",
        "county_map": {"11001": "District of Columbia"},
    },
    "New York City — Dialysis Centers": {
        "scores":    "outputs/results/gold/run_date=2026-06-04/ny_dialysis_scores.parquet",
        "facilities":"outputs/results/silver/run_date=2026-06-04/ny_dialysis_facilities.parquet",
        "crs":       "EPSG:32618",
        "facility":  "Dialysis Centers",
        "supply_label": "dialysis stations",
        "gini_std":  0.588,
        "color":     "#2980b9",
        "catchment": "1,200m",
        "county_map": {
            "36005": "Bronx", "36047": "Brooklyn",
            "36061": "Manhattan", "36081": "Queens", "36085": "Staten Island",
        },
    },
    "Los Angeles — FQHCs": {
        "scores":    "outputs/results/gold/run_date=2026-06-06/ca_fqhc_scores.parquet",
        "facilities":"outputs/results/silver/run_date=2026-06-04/dc_icf_facilities.parquet",
        "crs":       "EPSG:32611",
        "facility":  "Federally Qualified Health Centers",
        "supply_label": "FQHC sites",
        "gini_std":  None,
        "color":     "#f2a65a",
        "catchment": "1,600m",
        "county_map": {},
    },
}

# ── Helpers ────────────────────────────────────────────────────────────────────
def _gini(scores: np.ndarray, pop: np.ndarray) -> float:
    order = np.argsort(scores)
    s, p = scores[order], pop[order].astype(float)
    cum_p = np.cumsum(p) / p.sum()
    cum_a = np.cumsum(s * p)
    if cum_a[-1] > 0:
        cum_a = cum_a / cum_a[-1]
    else:
        cum_a = cum_p.copy()
    return float(1 - 2 * np.trapz(cum_a, cum_p))

def _lorenz(scores: np.ndarray, pop: np.ndarray):
    order = np.argsort(scores)
    s, p = scores[order], pop[order].astype(float)
    cum_p = np.cumsum(p) / p.sum()
    cum_a = np.cumsum(s * p)
    if cum_a[-1] > 0:
        cum_a = cum_a / cum_a[-1]
    return np.concatenate([[0], cum_p]), np.concatenate([[0], cum_a])

def _normalize(series: pd.Series) -> pd.Series:
    v = pd.to_numeric(series, errors="coerce").fillna(0.0)
    mn, mx = v.min(), v.max()
    return (v - mn) / (mx - mn) if mx > mn else pd.Series(0.0, index=v.index)

@st.cache_data(show_spinner="Loading data...")
def load_scores(path: str) -> gpd.GeoDataFrame:
    gdf = gpd.read_parquet(path)
    if "accessibility_score" not in gdf.columns:
        gdf["accessibility_score"] = 0.0
    gdf["accessibility_score"] = pd.to_numeric(gdf["accessibility_score"], errors="coerce").fillna(0.0)
    if "accessibility_norm" not in gdf.columns:
        s = gdf["accessibility_score"]
        mn, mx = s.min(), s.max()
        gdf["accessibility_norm"] = (s - mn) / (mx - mn) if mx > mn else 0.0
    gdf["accessibility_norm"] = pd.to_numeric(gdf["accessibility_norm"], errors="coerce").fillna(0.0)
    return gdf

@st.cache_data(show_spinner=False)
def load_facilities(path: str) -> gpd.GeoDataFrame:
    try:
        return gpd.read_parquet(path)
    except Exception:
        return gpd.GeoDataFrame()

def add_bivariate(gdf: gpd.GeoDataFrame, crs: str) -> gpd.GeoDataFrame:
    out = gdf.copy()
    proj = out.to_crs(crs)
    proj["area_km2"] = proj.geometry.area / 1e6
    proj["pop_density"] = proj["population"] / proj["area_km2"].replace(0, np.nan)
    pop_med = float(proj["pop_density"].replace([np.inf, -np.inf], np.nan).fillna(0.0).median())
    score_med = float(proj["accessibility_norm"].median())
    pd_ = proj["pop_density"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    hi_pop = pd_ >= pop_med
    hi_acc = proj["accessibility_norm"] >= score_med
    out["bivariate_class"] = np.select(
        [hi_pop & ~hi_acc, hi_pop & hi_acc, ~hi_pop & ~hi_acc, ~hi_pop & hi_acc],
        ["Priority (High pop, Low access)", "Well served (High pop, High access)",
         "Low priority (Low pop, Low access)", "Over-served (Low pop, High access)"],
        default="Low priority (Low pop, Low access)",
    )
    return out

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🏥 Healthcare Access")
    city_key = st.selectbox("Select city & facility", list(CITIES.keys()))
    cfg = CITIES[city_key]
    st.markdown("---")
    st.markdown(f"""
    **Facility:** {cfg['facility']}
    **Catchment:** {cfg['catchment']}
    **Method:** Enhanced 2SFCA
    **Data:** 2020 US Census blocks
    """)
    st.markdown("---")
    st.markdown("""
    **Enhanced 2SFCA** adds three components to standard proximity analysis:
    - Truncated Gaussian distance decay
    - Supply-side capacity weighting
    - Sociodemographic demand adjustment

    *Methodology under peer review*
    """)
    st.markdown("---")
    st.caption("Stack: GeoPandas · DuckDB · dbt · Airflow · PostGIS · Streamlit")

# ── Load data ──────────────────────────────────────────────────────────────────
scores_gdf  = load_scores(cfg["scores"])
fac_gdf     = load_facilities(cfg["facilities"])
scores_gdf  = add_bivariate(scores_gdf, cfg["crs"])

# Add county names
scores_gdf["county_fips"] = scores_gdf["GEOID"].astype(str).str.zfill(12).str[:5]
scores_gdf["county_name"] = scores_gdf["county_fips"].map(cfg["county_map"]).fillna(scores_gdf["county_fips"])

# ── Title ──────────────────────────────────────────────────────────────────────
st.title("Healthcare Access Equity Intelligence")
st.caption("Enhanced Two-Step Floating Catchment Area (2SFCA) · Washington DC · New York City · Los Angeles")

# ── Filters ────────────────────────────────────────────────────────────────────
county_options = sorted(scores_gdf["county_name"].unique().tolist())
fc1, fc2 = st.columns([2, 3])
if len(county_options) == 1:
    selected_counties = county_options
    fc1.info(f"County: {county_options[0]}")
else:
    selected_counties = fc1.multiselect("County filter", county_options, default=county_options)
pct_range = fc2.slider("Accessibility percentile brush", 0, 100, (0, 100), step=5)

filtered = scores_gdf[scores_gdf["county_name"].isin(selected_counties)].copy() if selected_counties else scores_gdf.iloc[0:0].copy()
if not filtered.empty:
    lo = float(filtered["accessibility_score"].quantile(pct_range[0] / 100))
    hi = float(filtered["accessibility_score"].quantile(pct_range[1] / 100))
    filtered = filtered[(filtered["accessibility_score"] >= lo) & (filtered["accessibility_score"] <= hi)].copy()

if filtered.empty:
    st.warning("No blocks after filters. Reset filters.")
    st.stop()

# ── Key metrics ────────────────────────────────────────────────────────────────
scores  = filtered["accessibility_score"].values
pop     = filtered["population"].values.astype(float)
gini_v  = _gini(scores, pop)
zero_pct = float((scores == 0).mean() * 100)
zero_pop = int(pop[scores == 0].sum())
mean_s  = float(scores.mean())
p90     = float(np.percentile(scores, 90))
total_supply = int(fac_gdf["supply"].sum()) if "supply" in fac_gdf.columns and len(fac_gdf) > 0 else 0

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Census blocks",     f"{len(filtered):,}")
c2.metric("Zero access",       f"{zero_pct:.1f}%")
c3.metric("Pop. w/o access",   f"{zero_pop:,}")
c4.metric("Gini (Enhanced)",   f"{gini_v:.3f}")
c5.metric(cfg["supply_label"].title(), f"{total_supply:,}" if total_supply else "N/A")

# ── Executive insights ─────────────────────────────────────────────────────────
priority_pct = float((filtered["bivariate_class"] == "Priority (High pop, Low access)").mean() * 100)
top_block = str(filtered.sort_values(["accessibility_score", "population"], ascending=[True, False]).iloc[0]["GEOID"])

i1, i2, i3 = st.columns(3)
with i1:
    st.markdown(f"<div class='insight-card'><div class='insight-title'>Coverage Stress</div><div class='insight-body'>{zero_pct:.1f}% of blocks have zero access — first-pass intervention targets.</div></div>", unsafe_allow_html=True)
with i2:
    st.markdown(f"<div class='insight-card'><div class='insight-title'>Priority Load</div><div class='insight-body'>{priority_pct:.1f}% of blocks are High population + Low access — concentrated equity pressure.</div></div>", unsafe_allow_html=True)
with i3:
    st.markdown(f"<div class='insight-card'><div class='insight-title'>Most Underserved Block</div><div class='insight-body'>Block {top_block} — lowest access combined with highest demand.</div></div>", unsafe_allow_html=True)

# ── Tabs ────────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🗺️ Accessibility Map", "📊 Lorenz Curve",
    "🎯 Priority Zones", "📈 Equity Lens", "🏙️ Cross-City"
])

# ── Tab 1: Interactive Map ─────────────────────────────────────────────────────
with tab1:
    map_mode = st.radio("Map layer", ["Accessibility", "Bivariate", "Population"], horizontal=True)
    show_fac = st.checkbox("Show facilities", value=True)

    disp = filtered[["GEOID", "population", "accessibility_score", "accessibility_norm", "bivariate_class", "geometry"]].copy()
    disp = disp[disp.geometry.notna() & ~disp.geometry.is_empty].to_crs("EPSG:4326")

    proj = disp.to_crs(cfg["crs"])
    centroid = proj.geometry.union_all().centroid
    c4326 = gpd.GeoSeries([centroid], crs=cfg["crs"]).to_crs("EPSG:4326").iloc[0]
    m = folium.Map(location=[c4326.y, c4326.x], zoom_start=11, tiles="CartoDB positron")

    vmax = max(float(disp["accessibility_score"].quantile(0.95)), 1e-9)
    pop_vmax = max(float(disp["population"].quantile(0.95)), 1.0)
    score_cm = LinearColormap(["#1b263b","#415a77","#2ec4b6","#ffd166","#ef476f"], vmin=0, vmax=vmax)
    pop_cm   = LinearColormap(["#e0fbfc","#98c1d9","#3d5a80","#293241"], vmin=0, vmax=pop_vmax)
    biv_pal  = {
        "Priority (High pop, Low access)": "#ef476f",
        "Well served (High pop, High access)": "#06d6a0",
        "Low priority (Low pop, Low access)": "#ffd166",
        "Over-served (Low pop, High access)": "#118ab2",
    }

    if map_mode == "Accessibility":
        def style_fn(f):
            s = min(max(float(f["properties"].get("accessibility_score", 0)), 0), vmax)
            return {"fillColor": score_cm(s), "color": "#333", "weight": 0.2, "fillOpacity": 0.75}
        score_cm.caption = f"{cfg['facility']} accessibility"
        score_cm.add_to(m)
    elif map_mode == "Population":
        def style_fn(f):
            p = min(max(float(f["properties"].get("population", 0)), 0), pop_vmax)
            return {"fillColor": pop_cm(p), "color": "#333", "weight": 0.2, "fillOpacity": 0.65}
        pop_cm.caption = "Population"
        pop_cm.add_to(m)
    else:
        def style_fn(f):
            cls = f["properties"].get("bivariate_class", "Low priority (Low pop, Low access)")
            return {"fillColor": biv_pal.get(cls, "#ccc"), "color": "#333", "weight": 0.2, "fillOpacity": 0.78}

    folium.GeoJson(
        disp.__geo_interface__,
        style_function=style_fn,
        tooltip=folium.GeoJsonTooltip(
            fields=["GEOID", "population", "accessibility_score", "bivariate_class"],
            aliases=["Block", "Population", "Score", "Class"],
            localize=True,
        ),
    ).add_to(m)

    if show_fac and len(fac_gdf) > 0:
        fac4326 = fac_gdf.to_crs("EPSG:4326") if fac_gdf.crs else fac_gdf
        fac_layer = folium.FeatureGroup(name="Facilities")
        for _, row in fac4326.iterrows():
            name   = str(row.get("FAC_NAME", row.get("name", "Facility")))
            supply = str(row.get("supply", "N/A"))
            folium.CircleMarker(
                location=[float(row.geometry.y), float(row.geometry.x)],
                radius=5, color="#000", fill=True, fill_color=cfg["color"],
                fill_opacity=1.0, weight=1.5,
                tooltip=f"{name} | Supply: {supply}",
            ).add_to(fac_layer)
        fac_layer.add_to(m)

    if map_mode == "Bivariate":
        legend_html = "<div style='position:fixed;bottom:20px;left:20px;z-index:9999;background:rgba(19,24,33,.92);color:#eef2f7;padding:10px 12px;border-radius:8px;font-size:12px'><b>Bivariate legend</b><br>" + "".join([f"<div><span style='display:inline-block;width:10px;height:10px;background:{c};margin-right:6px'></span>{k}</div>" for k, c in biv_pal.items()]) + "</div>"
        m.get_root().html.add_child(folium.Element(legend_html))

    folium.LayerControl().add_to(m)
    st.components.v1.html(m.get_root().render(), height=600, scrolling=False)

# ── Tab 2: Lorenz ──────────────────────────────────────────────────────────────
with tab2:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cp, ca = _lorenz(scores, pop)
    fig, ax = plt.subplots(figsize=(8, 5))
    fig.patch.set_facecolor("#0c0f14")
    ax.set_facecolor("#141922")
    ax.plot([0,1],[0,1], "w--", linewidth=1, alpha=0.4, label="Perfect equality")
    ax.plot(cp, ca, color=cfg["color"], linewidth=2.5, label=f"SDW-2SFCA (Gini={gini_v:.4f})")
    ax.fill_between(cp, cp, ca, alpha=0.12, color=cfg["color"])
    if cfg["gini_std"] is not None:
        ax.plot([0,1],[0,1], color="#94a3b8", linewidth=1.5, linestyle=":",
                label=f"Standard 2SFCA (Gini={cfg['gini_std']:.3f})")
    ax.set_xlabel("Cumulative Share of Population", color="white", fontsize=11)
    ax.set_ylabel("Cumulative Share of Accessibility", color="white", fontsize=11)
    ax.set_title(f"Lorenz Curve — {cfg['facility']}", color="white", fontsize=13)
    ax.tick_params(colors="white")
    ax.spines[:].set_color("#334155")
    ax.legend(fontsize=10, facecolor="#1b222e", labelcolor="white")
    ax.grid(True, alpha=0.15, color="white")
    col1, col2 = st.columns([3, 1])
    with col1:
        st.pyplot(fig)
        plt.close(fig)
    with col2:
        st.markdown(f"""
        <div style='background:#1b222e;border-radius:12px;padding:1.5rem;text-align:center;margin-bottom:1rem;border:1px solid rgba(62,199,166,.3)'>
            <div style='font-size:.8rem;color:#94a3b8'>SDW-2SFCA</div>
            <div style='font-size:2.5rem;font-weight:700;color:{cfg["color"]}'>{gini_v:.3f}</div>
            <div style='font-size:.8rem;color:#94a3b8'>Severe inequality</div>
        </div>
        """, unsafe_allow_html=True)
        if cfg["gini_std"] is not None:
            st.markdown(f"""
            <div style='background:#1b222e;border-radius:12px;padding:1.5rem;text-align:center;border:1px solid rgba(148,163,184,.3)'>
                <div style='font-size:.8rem;color:#94a3b8'>Standard 2SFCA</div>
                <div style='font-size:2.5rem;font-weight:700;color:#94a3b8'>{cfg["gini_std"]:.3f}</div>
                <div style='font-size:.8rem;color:#94a3b8'>{'Masks disparities' if cfg['gini_std'] < 0.1 else 'Lower estimate'}</div>
            </div>
            """, unsafe_allow_html=True)

# ── Tab 3: Priority Zones ──────────────────────────────────────────────────────
with tab3:
    biv_counts = filtered["bivariate_class"].value_counts()
    biv_pop    = filtered.groupby("bivariate_class")["population"].sum()
    biv_df = pd.DataFrame({"Blocks": biv_counts, "Population": biv_pop}).fillna(0)
    biv_df["Population"] = biv_df["Population"].astype(int)
    st.dataframe(biv_df, use_container_width=True)

    priority_df = filtered[filtered["bivariate_class"] == "Priority (High pop, Low access)"].copy()
    priority_df = priority_df.sort_values("population", ascending=False)
    st.markdown(f"**Top priority blocks** ({len(priority_df):,} blocks, {int(priority_df['population'].sum()):,} people)")
    st.dataframe(
        priority_df[["GEOID", "county_name", "population", "accessibility_score", "accessibility_norm"]]
        .head(20).reset_index(drop=True),
        use_container_width=True,
    )

# ── Tab 4: Equity Lens ─────────────────────────────────────────────────────────
with tab4:
    eq_cols = [c for c in ["PerCapitaI", "HI_block", "age_18to65"] if c in filtered.columns]
    if not eq_cols:
        st.info("Equity factors not available for this city/run. Present when sociodemographic data is joined.")
    else:
        plot_df = filtered[["accessibility_score"] + eq_cols].copy()
        vuln = pd.concat([
            1 - _normalize(plot_df["PerCapitaI"]) if "PerCapitaI" in plot_df.columns else pd.Series(),
            _normalize(plot_df["HI_block"])       if "HI_block"   in plot_df.columns else pd.Series(),
            _normalize(plot_df["age_18to65"])     if "age_18to65" in plot_df.columns else pd.Series(),
        ], axis=1).mean(axis=1)
        plot_df["vulnerability"] = vuln
        try:
            n_bins = min(4, max(2, int(plot_df["vulnerability"].nunique())))
            labels = ["Q1 Least", "Q2", "Q3", "Q4 Most"][:n_bins]
            plot_df["quartile"] = pd.qcut(plot_df["vulnerability"], q=n_bins, labels=labels, duplicates="drop")
        except Exception:
            plot_df["quartile"] = "Q1 Least"
        summary = plot_df.groupby("quartile", observed=False)["accessibility_score"].mean().reset_index()
        summary.columns = ["Vulnerability quartile", "Mean accessibility score"]
        st.caption("Do more vulnerable communities have lower accessibility? Q4 = most vulnerable.")
        st.bar_chart(summary.set_index("Vulnerability quartile"), use_container_width=True)

        st.markdown("#### Correlation matrix")
        corr = filtered[["accessibility_score"] + eq_cols].corr()
        st.dataframe(corr.round(3), use_container_width=True)

# ── Tab 5: Cross-City ──────────────────────────────────────────────────────────
with tab5:
    st.markdown("#### Same pipeline · One YAML change · Three cities")
    comp = pd.DataFrame({
        "Metric": ["Facility type","Census blocks","Facilities","Zero-access blocks",
                   "Pop. w/o access","Gini (Enhanced)","Gini (Standard)","Catchment"],
        "Washington DC": ["ICF/IDD","6,012","114","38%","303,833","0.721","0.00","900m"],
        "New York City": ["Dialysis","37,984","135","47%","3,112,366","0.652","0.588","1,200m"],
        "Los Angeles":   ["FQHCs","65,626+","808","42.1%","~3.8M","0.747","N/A","1,600m"],
    })
    st.dataframe(comp.set_index("Metric"), use_container_width=True)

    fig2, ax2 = plt.subplots(figsize=(7, 4))
    fig2.patch.set_facecolor("#0c0f14")
    ax2.set_facecolor("#141922")
    cities_l  = ["DC\n(ICFs)", "NYC\n(Dialysis)", "LA\n(FQHCs)"]
    enh_vals  = [0.721, 0.652, 0.747]
    std_vals  = [0.00, 0.588, 0]
    colors_l  = ["#3ec7a6", "#2980b9", "#f2a65a"]
    x = np.arange(3)
    bars = ax2.bar(x - 0.18, enh_vals, 0.32, color=colors_l, alpha=0.9, label="SDW-2SFCA")
    ax2.bar(x + 0.18, std_vals, 0.32, color="#475569", alpha=0.7, label="Standard 2SFCA")
    ax2.axhline(0.6, color="#ef4444", linestyle="--", linewidth=1, alpha=0.6, label="Severe threshold (0.6)")
    for bar, val in zip(bars, enh_vals):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                 f"{val:.3f}", ha="center", va="bottom", fontsize=10,
                 fontweight="bold", color="white")
    ax2.set_xticks(x); ax2.set_xticklabels(cities_l, color="white", fontsize=12)
    ax2.set_ylabel("Gini Coefficient", color="white"); ax2.set_ylim(0, 0.85)
    ax2.tick_params(colors="white"); ax2.spines[:].set_color("#334155")
    ax2.legend(fontsize=9, facecolor="#1b222e", labelcolor="white")
    ax2.set_title("Healthcare Accessibility Inequality — Three US Cities", color="white", fontsize=12)
    st.pyplot(fig2)
    plt.close(fig2)

    st.markdown("""
    > **Key finding:** Across all three cities the enhanced method reveals significantly higher
    > inequality than standard 2SFCA. In DC, standard 2SFCA reports Gini=0.00 (perfect equality)
    > while the enhanced method reveals Gini=0.721 — severe structural inequality hidden by proximity-only analysis.
    """)

# ── Download ───────────────────────────────────────────────────────────────────
csv = filtered.drop(columns="geometry").to_csv(index=False).encode("utf-8")
st.download_button(
    "📥 Download enhanced scores CSV", csv,
    file_name=f"enhanced_2sfca_{city_key.split('—')[0].strip().lower().replace(' ','_')}.csv",
    mime="text/csv", use_container_width=True,
)

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("""
<div style='text-align:center;color:#64748b;font-size:.85rem;padding:1rem'>
    <strong>Ushashi Podder</strong> · University of Maryland, College Park<br>
    Methodology under review · Paper in preparation · FOSS4G NA 2026<br>
    GeoPandas · DuckDB · dbt · Apache Airflow · PostGIS · S3 GeoParquet · Streamlit
</div>
""", unsafe_allow_html=True)
