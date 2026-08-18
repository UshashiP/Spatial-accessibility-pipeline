from __future__ import annotations

import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import streamlit as st
import folium
from branca.colormap import linear, LinearColormap

from pipeline.ingest.census_api import ingest_census_blocks
from pipeline.ingest.cms_api import ingest_facilities
from pipeline.transform.sfca_enhanced import compute_enhanced_2sfca


@dataclass(frozen=True)
class CitySpec:
    name: str
    state_fips: str
    state_abbrev: str
    county_fips: list[str]
    bbox: tuple[float, float, float, float]
    projected_crs: str
    enriched_blocks_path: str | None = None


CITY_SPECS: dict[str, CitySpec] = {
    "Washington DC": CitySpec(
        name="Washington DC",
        state_fips="11",
        state_abbrev="DC",
        county_fips=["001"],
        bbox=(-77.1198, 38.7916, -76.9094, 38.9955),
        projected_crs="EPSG:26985",
        enriched_blocks_path="data/intermediate_files/blocksandtract_economic_final.shp",
    ),
    "New York City": CitySpec(
        name="New York City",
        state_fips="36",
        state_abbrev="NY",
        county_fips=["005", "047", "061", "081", "085"],
        bbox=(-74.25909, 40.477399, -73.700272, 40.917577),
        projected_crs="EPSG:32618",
        enriched_blocks_path="/Users/ushashi/Documents/codes/NYC_advanced2FCA_replication/data/intermediate_files/blocks_New_York_City_enhanced.shp",
    ),
    "Los Angeles": CitySpec(
        name="Los Angeles",
        state_fips="06",
        state_abbrev="CA",
        county_fips=["037"],
        bbox=(-118.9448, 33.7037, -117.6464, 34.8233),
        projected_crs="EPSG:32611",
        enriched_blocks_path="data/intermediate_files/blocks_Los_Angeles_urban.shp",
    ),
}

FACILITY_DATASETS: dict[str, dict[str, str]] = {
    "Washington DC": {
        "type": "ICF",
        "label": "Intermediate Care Facilities (ICF)",
        "cms_dataset_id": "78j2-v3zx",
        "cms_category_code": "13",
        "supply_column": "CRTFD_BED_CNT",
        "local_facilities_path": "data/intermediate_files/Intermediate_Care_Facilities.shp",
    },
    "New York City": {
        "type": "dialysis",
        "label": "Dialysis",
        "cms_dataset_id": "23ew-n7w9",
        "cms_category_code": "21",
        "supply_column": "TOTAL_DIALYSIS_STATIONS",
        "local_facilities_path": "/Users/ushashi/Documents/codes/NYC_advanced2FCA_replication/data/intermediate_files/Dialysis_NYC.shp",
    },
    "Los Angeles": {
        "type": "FQHC",
        "label": "Federally Qualified Health Centers",
        "cms_dataset_id": "",
        "cms_category_code": "",
        "supply_column": "supply",
        "local_facilities_path": "data/intermediate_files/FQHC_LA.shp",
    },
}

COUNTY_NAMES_BY_CITY: dict[str, dict[str, str]] = {
    "Washington DC": {
        "11001": "District of Columbia",
    },
    "New York City": {
        "36005": "Bronx",
        "36047": "Brooklyn",
        "36061": "Manhattan",
        "36081": "Queens",
        "36085": "Staten Island",
    },
}


def _normalize_0_1(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").fillna(0.0)
    vmin = float(values.min())
    vmax = float(values.max())
    if vmax <= vmin:
        return pd.Series(np.zeros(len(values)), index=values.index)
    return (values - vmin) / (vmax - vmin)


def _sanitize_scores(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    out = gdf.copy()
    if "accessibility_score" not in out.columns:
        out["accessibility_score"] = 0.0
    out["accessibility_score"] = pd.to_numeric(out["accessibility_score"], errors="coerce").fillna(0.0)

    if "accessibility_norm" not in out.columns:
        out["accessibility_norm"] = 0.0
    else:
        out["accessibility_norm"] = pd.to_numeric(out["accessibility_norm"], errors="coerce")

    need_recompute = out["accessibility_norm"].isna().any()
    if need_recompute:
        score_min = float(out["accessibility_score"].min())
        score_max = float(out["accessibility_score"].max())
        if score_max > score_min:
            out["accessibility_norm"] = (out["accessibility_score"] - score_min) / (score_max - score_min)
        else:
            out["accessibility_norm"] = 0.0
    out["accessibility_norm"] = out["accessibility_norm"].fillna(0.0)
    return out


def _apply_supply_variant(facilities: gpd.GeoDataFrame, variant: str) -> gpd.GeoDataFrame:
    out = facilities.copy()
    if "supply" in out.columns:
        raw_supply = pd.to_numeric(out["supply"], errors="coerce").fillna(1.0)
    else:
        raw_supply = pd.Series(1.0, index=out.index)

    if variant == "Uniform (1 per facility)":
        out["supply"] = 1.0
        return out

    if variant == "Type-weighted (metadata)":
        type_col = next(
            (c for c in ["Health Center Type", "SITE_TYPE", "FACILITY_TYPE", "FAC_TYPE", "TYPE"] if c in out.columns),
            None,
        )
        if type_col is None:
            out["supply"] = raw_supply
            return out
        type_text = out[type_col].astype(str).str.lower()
        weights = np.select(
            [
                type_text.str.contains("mobile", na=False),
                type_text.str.contains("school", na=False),
                type_text.str.contains("satellite", na=False),
                type_text.str.contains("main", na=False) | type_text.str.contains("grantee", na=False),
            ],
            [0.5, 0.75, 0.85, 1.25],
            default=1.0,
        )
        out["supply"] = raw_supply * weights
        return out

    out["supply"] = raw_supply
    return out


@st.cache_data(show_spinner=False)
def load_city_inputs(
    city: CitySpec,
    census_api_key: str | None = None,
    supply_variant: str = "Raw supply",
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    facility_cfg = FACILITY_DATASETS[city.name]
    config = {
        "study_area": {
            "name": city.name,
            "state_fips": city.state_fips,
            "state_abbrev": city.state_abbrev,
            "county_fips": city.county_fips,
            "bbox": city.bbox,
            "coordinate_system": city.projected_crs,
        },
        "facility": {
            "type": facility_cfg["type"],
            "label": facility_cfg["label"],
            "cms_dataset_id": facility_cfg["cms_dataset_id"],
            "cms_category_code": facility_cfg["cms_category_code"],
            "supply_column": facility_cfg["supply_column"],
        },
        "census": {
            "year": 2020,
            "dataset": "dec/pl",
            "variables": {"total_population": "P1_001N"},
        },
        "cms": {"api_key": None},
        "data": {
            "snapshot": {"use_snapshot": True},
            "local_shapefiles": {
                "facilities": facility_cfg["local_facilities_path"],
                "census_blocks": city.enriched_blocks_path,
            },
            "population_column": "Total Popu",
            "intermediate": {"path": "data/intermediate_files/"},
        },
    }
    if census_api_key:
        config["census"]["api_key"] = census_api_key

    blocks = ingest_census_blocks(config)
    facilities = ingest_facilities(config)
    facilities = _apply_supply_variant(facilities, supply_variant)
    return blocks, facilities


def enrich_for_enhanced_model(blocks_gdf: gpd.GeoDataFrame, city: CitySpec) -> gpd.GeoDataFrame:
    out = blocks_gdf.copy()
    out["Total Popu"] = out["population"]

    path = city.enriched_blocks_path
    if path and os.path.exists(path):
        enriched = gpd.read_file(path)
        geoid_col = None
        for candidate in ["GEOID", "GEOID20", "GEOCODE", "GEOID_left"]:
            if candidate in enriched.columns:
                geoid_col = candidate
                break
        if geoid_col:
            enriched = enriched.rename(columns={geoid_col: "GEOID"})
            keep = ["GEOID", "PerCapitaI", "HI_block", "age_18to65", "Total Popu"]
            keep = [c for c in keep if c in enriched.columns]
            enriched = pd.DataFrame(enriched[keep])
            out = out.merge(enriched, on="GEOID", how="left", suffixes=("", "_src"))

    if "Total Popu_src" in out.columns:
        out["Total Popu"] = pd.to_numeric(out["Total Popu_src"], errors="coerce").fillna(out["population"])

    for col in ["PerCapitaI", "HI_block", "age_18to65"]:
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)

    out["PerCapitaI"] = _normalize_0_1(out["PerCapitaI"])
    out["HI_block"] = _normalize_0_1(out["HI_block"])
    out["age_18to65"] = _normalize_0_1(out["age_18to65"])

    drop_cols = [c for c in ["Total Popu_src"] if c in out.columns]
    if drop_cols:
        out = out.drop(columns=drop_cols)
    return out


def _derive_supply_variant_options(city_name: str) -> list[str]:
    return ["Raw supply", "Uniform (1 per facility)", "Type-weighted (metadata)"]


def run_enhanced(city: CitySpec, facilities: gpd.GeoDataFrame, blocks: gpd.GeoDataFrame, d0_m: float) -> gpd.GeoDataFrame:
    blocks_proj = blocks.to_crs(city.projected_crs)
    fac_proj = facilities.to_crs(city.projected_crs)
    return compute_enhanced_2sfca(
        population_gdf=blocks_proj,
        facility_gdf=fac_proj,
        d0=d0_m,
        pop_col="Total Popu",
        supply_col="supply",
        income_col="PerCapitaI",
        insurance_col="HI_block",
        age_col="age_18to65",
    )


def _dataset_prefix(city: CitySpec) -> str:
    fac_type = FACILITY_DATASETS[city.name]["type"].lower()
    return f"{city.state_abbrev.lower()}_{fac_type}"


def _latest_parquet(layer: str, dataset: str) -> Path | None:
    root = Path("outputs/results") / layer
    candidates = sorted(root.glob(f"run_date=*/{dataset}.parquet"))
    if not candidates:
        return None
    return candidates[-1]


def _normalize_for_priority(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").fillna(0.0)
    vmin = float(values.min())
    vmax = float(values.max())
    if vmax <= vmin:
        return pd.Series(np.zeros(len(values)), index=values.index)
    return (values - vmin) / (vmax - vmin)


def _first_existing_path(candidates: list[str]) -> Path | None:
    for candidate in candidates:
        p = Path(candidate)
        if p.exists():
            return p
    return None


def _find_street_network_file(city: CitySpec) -> Path | None:
    prefix = _dataset_prefix(city)
    fixed_candidates = [
        f"data/reference/{prefix}_street_network.geojson",
        f"data/reference/{city.state_abbrev.lower()}_street_network.geojson",
        f"data/intermediate_files/{prefix}_street_network.geojson",
        f"data/intermediate_files/{city.state_abbrev.lower()}_street_network.geojson",
        f"data/intermediate_files/{prefix}_streets.geojson",
    ]
    path = _first_existing_path(fixed_candidates)
    if path:
        return path
    dynamic_candidates = sorted(Path("outputs/results/silver").glob(f"run_date=*/{prefix}_street_network.*"))
    if dynamic_candidates:
        return dynamic_candidates[-1]
    return None


@st.cache_data(show_spinner=False)
def load_street_network(city: CitySpec) -> gpd.GeoDataFrame | None:
    path = _find_street_network_file(city)
    if not path:
        return None
    if path.suffix.lower() == ".parquet":
        network = gpd.read_parquet(path)
    else:
        network = gpd.read_file(path)
    return network


@st.cache_data(show_spinner=False)
def load_cached_city_outputs(city: CitySpec) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame] | None:
    prefix = _dataset_prefix(city)
    score_path = _latest_parquet("gold", f"{prefix}_scores")
    fac_path = _latest_parquet("silver", f"{prefix}_facilities")
    if not score_path or not fac_path:
        return None
    result = gpd.read_parquet(score_path)
    result = _sanitize_scores(result)
    facilities = gpd.read_parquet(fac_path)
    return result, facilities


def add_bivariate_class(result_gdf: gpd.GeoDataFrame, city: CitySpec) -> gpd.GeoDataFrame:
    out = result_gdf.copy()
    projected = out.to_crs(city.projected_crs)
    projected["area_km2"] = projected.geometry.area / 1e6
    projected["pop_density"] = projected["population"] / projected["area_km2"].replace(0, np.nan)

    pop_med = float(projected["pop_density"].replace([np.inf, -np.inf], np.nan).fillna(0.0).median())
    score_med = float(projected["accessibility_norm"].median())

    pop_density = projected["pop_density"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    hi_pop = pop_density >= pop_med
    hi_access = projected["accessibility_norm"] >= score_med

    classes = np.select(
        [hi_pop & ~hi_access, hi_pop & hi_access, ~hi_pop & ~hi_access, ~hi_pop & hi_access],
        [
            "Priority (High pop, Low access)",
            "Well served (High pop, High access)",
            "Low priority (Low pop, Low access)",
            "Over-served (Low pop, High access)",
        ],
        default="Low priority (Low pop, Low access)",
    )
    out["bivariate_class"] = classes
    return out


def render_interactive_choropleth(
    result_4326: gpd.GeoDataFrame,
    facilities_4326: gpd.GeoDataFrame,
    city: CitySpec,
    facility_label: str,
    layers: dict[str, bool],
    street_network_4326: gpd.GeoDataFrame | None = None,
    county_boundaries_4326: gpd.GeoDataFrame | None = None,
) -> None:
    columns = ["GEOID", "population", "accessibility_score", "accessibility_norm", "geometry"]
    if "bivariate_class" in result_4326.columns:
        columns.append("bivariate_class")
    display = result_4326[columns].copy()
    display = display[display.geometry.notna() & ~display.geometry.is_empty].copy()
    display["accessibility_score"] = pd.to_numeric(display["accessibility_score"], errors="coerce").fillna(0.0)
    display["population"] = pd.to_numeric(display["population"], errors="coerce").fillna(0.0)
    if display.empty:
        st.error("No valid block geometry available for map rendering.")
        return
    if len(display) > 12000:
        st.info("Rendering all blocks for complete coverage. If the map feels slow, narrow county/percentile filters.")

    display_center = display.to_crs(city.projected_crs)
    centroid = display_center.geometry.union_all().centroid
    centroid_4326 = gpd.GeoSeries([centroid], crs=city.projected_crs).to_crs("EPSG:4326").iloc[0]
    center = [float(centroid_4326.y), float(centroid_4326.x)]
    m = folium.Map(location=center, zoom_start=11, tiles="CartoDB positron")

    score_vmax = max(float(display["accessibility_score"].quantile(0.95)), 1e-9)
    pop_vmax = max(float(display["population"].quantile(0.95)), 1.0)
    score_colormap = LinearColormap(
        colors=["#1b263b", "#415a77", "#2ec4b6", "#ffd166", "#ef476f"],
        vmin=0, vmax=score_vmax,
    )
    score_colormap.caption = f"{facility_label} accessibility score"
    pop_colormap = LinearColormap(
        colors=["#e0fbfc", "#98c1d9", "#3d5a80", "#293241"],
        vmin=0, vmax=pop_vmax,
    )
    pop_colormap.caption = "Population"

    underserved_threshold = float(display["accessibility_score"].quantile(0.1))
    bivariate_palette = {
        "Priority (High pop, Low access)": "#ef476f",
        "Well served (High pop, High access)": "#06d6a0",
        "Low priority (Low pop, Low access)": "#ffd166",
        "Over-served (Low pop, High access)": "#118ab2",
    }

    def score_style_fn(feature):
        score = float(feature["properties"].get("accessibility_score", 0.0))
        if not np.isfinite(score): score = 0.0
        score = min(max(score, 0.0), score_vmax)
        return {"fillColor": score_colormap(score), "color": "#4b4b4b", "weight": 0.2, "fillOpacity": 0.72}

    def pop_style_fn(feature):
        pop = float(feature["properties"].get("population", 0.0))
        if not np.isfinite(pop): pop = 0.0
        pop = min(max(pop, 0.0), pop_vmax)
        return {"fillColor": pop_colormap(pop), "color": "#5f6f88", "weight": 0.2, "fillOpacity": 0.62}

    def underserved_style_fn(feature):
        score = float(feature["properties"].get("accessibility_score", 0.0))
        is_underserved = score <= underserved_threshold
        return {
            "fillColor": "#a50f15" if is_underserved else "#f7f7f7",
            "color": "#7f0000" if is_underserved else "#00000000",
            "weight": 0.2,
            "fillOpacity": 0.78 if is_underserved else 0.0,
        }

    def bivariate_style_fn(feature):
        b_class = feature["properties"].get("bivariate_class", "Low priority (Low pop, Low access)")
        return {"fillColor": bivariate_palette.get(b_class, "#bdc3c7"), "color": "#535353", "weight": 0.2, "fillOpacity": 0.78}

    display_geojson = display.__geo_interface__

    def _tooltip():
        fields = ["GEOID", "population", "accessibility_score", "accessibility_norm"]
        aliases = ["Block GEOID", "Population", "Accessibility score", "Normalized score"]
        if "bivariate_class" in display.columns:
            fields.append("bivariate_class")
            aliases.append("Bivariate class")
        return folium.GeoJsonTooltip(fields=fields, aliases=aliases, localize=True)

    def _popup():
        fields = ["GEOID", "population", "accessibility_score", "accessibility_norm"]
        aliases = ["Block GEOID", "Population", "Accessibility score", "Normalized score"]
        if "bivariate_class" in display.columns:
            fields.append("bivariate_class")
            aliases.append("Bivariate class")
        return folium.GeoJsonPopup(fields=fields, aliases=aliases, localize=True)

    map_mode = layers.get("map_mode", "Accessibility")

    if map_mode == "Accessibility":
        folium.GeoJson(display_geojson, name="Accessibility score", style_function=score_style_fn,
                       tooltip=_tooltip(), popup=_popup(), show=True).add_to(m)
        score_colormap.add_to(m)

    if map_mode == "Population":
        folium.GeoJson(display_geojson, name="Population", style_function=pop_style_fn,
                       tooltip=_tooltip(), popup=_popup(), show=True).add_to(m)
        pop_colormap.add_to(m)

    if map_mode == "Bivariate" and "bivariate_class" in display.columns:
        folium.GeoJson(display_geojson, name="Bivariate: pop density x accessibility",
                       style_function=bivariate_style_fn, tooltip=_tooltip(), popup=_popup(), show=True).add_to(m)
        legend_items = "".join([
            f"<div><span style='display:inline-block;width:10px;height:10px;background:{c};margin-right:8px;'></span>{k}</div>"
            for k, c in bivariate_palette.items()
        ])
        legend_html = (
            "<div style='position:fixed;bottom:20px;left:20px;z-index:9999;"
            "background:rgba(19,24,33,0.92);color:#eef2f7;padding:10px 12px;"
            "border:1px solid rgba(255,255,255,0.18);border-radius:8px;font-size:12px;line-height:1.4;'>"
            "<b>Bivariate legend</b><br>" + legend_items + "</div>"
        )
        m.get_root().html.add_child(folium.Element(legend_html))

    if layers.get("underserved", True):
        folium.GeoJson(display_geojson, name="Underserved blocks (bottom decile)",
                       style_function=underserved_style_fn, tooltip=_tooltip(), popup=_popup(), show=True).add_to(m)

    if layers.get("facilities", True):
        facility_color = "#f15bb5" if "Intermediate Care" in facility_label else "#39ff14"

        def _first_value(row, keys, fallback="n/a"):
            for key in keys:
                val = row.get(key)
                if pd.notna(val) and str(val).strip() != "":
                    return str(val)
            return fallback

        fac_layer = folium.FeatureGroup(name=f"{facility_label} facilities")
        for _, row in facilities_4326.iterrows():
            name = _first_value(row, ["FAC_NAME", "PROVIDER_NAME", "name"], "Facility")
            supply = _first_value(row, ["supply", "CRTFD_BED_CNT", "TOTAL_DIALYSIS_STATIONS"], "n/a")
            address = _first_value(row, ["ADDRESS", "address", "street"], "n/a")
            city_name = _first_value(row, ["CITY", "city"], "n/a")
            state_name = _first_value(row, ["STATE", "state"], "n/a")
            zip_code = _first_value(row, ["ZIP", "zip", "ZIP_CODE"], "n/a")
            phone = _first_value(row, ["PHONE", "phone"], "n/a")
            popup_html = (
                f"<b>{name}</b><br>Type: {facility_label}<br>Supply: {supply}<br>"
                f"Address: {address}, {city_name}, {state_name} {zip_code}<br>Phone: {phone}"
            )
            folium.CircleMarker(
                location=[float(row.geometry.y), float(row.geometry.x)],
                radius=5, color="#121212", fill=True, fill_color=facility_color,
                fill_opacity=1.0, weight=2.0,
                tooltip=f"{name} | Supply: {supply}",
                popup=folium.Popup(popup_html, max_width=300),
            ).add_to(fac_layer)
        fac_layer.add_to(m)

    if layers.get("street_network", False) and street_network_4326 is not None and len(street_network_4326) > 0:
        folium.GeoJson(street_network_4326, name="Street network",
                       style_function=lambda _f: {"color": "#444444", "weight": 1.1, "opacity": 0.55},
                       show=False).add_to(m)

    if layers.get("county_boundaries", False) and county_boundaries_4326 is not None and len(county_boundaries_4326) > 0:
        folium.GeoJson(
            county_boundaries_4326.__geo_interface__,
            name="County boundaries (context)",
            style_function=lambda _f: {"fillOpacity": 0.0, "color": "#f2a65a", "weight": 1.6, "opacity": 0.9},
            tooltip=folium.GeoJsonTooltip(fields=["county_name"], aliases=["County"], localize=True),
            show=True,
        ).add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    st.components.v1.html(m.get_root().render(), height=700, scrolling=False)


def compute_priority_blocks(result_gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    df = result_gdf.copy()
    df["score_gap"] = 1.0 - pd.to_numeric(df["accessibility_norm"], errors="coerce").fillna(0.0)
    df["population_norm"] = _normalize_for_priority(df["population"])

    vuln_components = []
    if "PerCapitaI" in df.columns:
        vuln_components.append(1.0 - _normalize_for_priority(df["PerCapitaI"]))
    if "HI_block" in df.columns:
        vuln_components.append(_normalize_for_priority(df["HI_block"]))
    if "age_18to65" in df.columns:
        vuln_components.append(_normalize_for_priority(df["age_18to65"]))

    if vuln_components:
        df["vulnerability_norm"] = pd.concat(vuln_components, axis=1).mean(axis=1)
    else:
        df["vulnerability_norm"] = 0.5

    df["priority_index"] = (
        0.55 * df["score_gap"] + 0.30 * df["population_norm"] + 0.15 * df["vulnerability_norm"]
    )

    return df[[
        "GEOID", "population", "accessibility_score", "accessibility_norm",
        "priority_index", "vulnerability_norm", "county_name",
    ]].sort_values("priority_index", ascending=False)


def build_recommendations(priority_df: pd.DataFrame, facility_label: str) -> pd.DataFrame:
    top = priority_df.head(15).copy()
    if top.empty:
        return top

    recommendations = []
    for _, row in top.iterrows():
        priority = float(row["priority_index"])
        vulnerability = float(row["vulnerability_norm"])
        access_norm = float(row["accessibility_norm"])

        if priority >= 0.75 or (access_norm <= 0.2 and vulnerability >= 0.6):
            action = f"Increase {facility_label} capacity"
            rationale = "High demand and severe low-access signal"
        elif vulnerability >= 0.65:
            action = "Deploy mobile outreach / navigator support"
            rationale = "High vulnerability likely limits realized access"
        else:
            action = "Improve first-mile transit connectivity"
            rationale = "Moderate vulnerability, likely distance/friction barrier"
        recommendations.append((action, rationale))

    top[["recommended_action", "rationale"]] = pd.DataFrame(recommendations, index=top.index)
    return top[["GEOID", "county_name", "population", "accessibility_score", "priority_index", "recommended_action", "rationale"]]


def build_audience_answers(filtered, priority, recommendations, facility_label):
    answers = {}
    n_counties = int(filtered["county_name"].nunique()) if "county_name" in filtered.columns else 0
    if n_counties <= 1:
        lowest_block = filtered.sort_values(["accessibility_score", "population"], ascending=[True, False]).iloc[0]
        answers["Which county has the highest unmet demand?"] = (
            f"Single county view. Most underserved block is {lowest_block['GEOID']} "
            f"with score {float(lowest_block['accessibility_score']):.4f}."
        )
    else:
        by_county = filtered.groupby("county_name", observed=False).agg(
            mean_score=("accessibility_score", "mean"), total_pop=("population", "sum")
        ).reset_index()
        weakest = by_county.sort_values("mean_score").iloc[0]
        answers["Which county has the highest unmet demand?"] = (
            f"{weakest['county_name']} has the lowest mean accessibility score "
            f"({float(weakest['mean_score']):.4f}) across {int(weakest['total_pop']):,} people."
        )

    top5 = recommendations.head(5)
    top5_blocks = ", ".join(top5["GEOID"].astype(str).tolist()) if len(top5) > 0 else "No blocks available"
    answers["Which 5 blocks should we prioritize first?"] = (
        f"Top priority blocks are {top5_blocks}. They combine low accessibility, higher population, "
        "and elevated vulnerability proxies."
    )

    baseline_mean = float(filtered["accessibility_score"].mean())
    projected_mean = baseline_mean * 1.20
    answers[f"What if we increase {facility_label} capacity by 20%?"] = (
        f"A first-order estimate suggests mean accessibility could increase from {baseline_mean:.4f} "
        f"to about {projected_mean:.4f}. Run the scenario slider at 1.20 and click Run for computed values."
    )
    return answers


def build_policy_brief_text(city_name, facility_label, filtered, recommendations, zero_pct, mean_score, p90):
    top_rows = recommendations.head(10)
    lines = [
        "# Policy Brief — Healthcare Access Equity Intelligence", "",
        f"## Study Area\n- City: {city_name}\n- Facility focus: {facility_label}", "",
        "## Key Findings",
        f"- Mean accessibility score: {mean_score:.6f}",
        f"- Zero-access block share: {zero_pct:.2f}%",
        f"- 90th percentile score: {p90:.6f}",
        f"- Blocks analyzed: {len(filtered):,}",
        f"- Population represented: {int(filtered['population'].sum()):,}", "",
        "## Recommended Priority Blocks",
    ]
    if len(top_rows) == 0:
        lines.append("- No recommendations available for current filter.")
    else:
        for _, row in top_rows.iterrows():
            lines.append(
                f"- GEOID {row['GEOID']} ({row['county_name']}): {row['recommended_action']} "
                f"(priority={float(row['priority_index']):.3f}; rationale: {row['rationale']})"
            )
    lines.extend(["", "## Implementation Note", "- This brief reflects the current dashboard view."])
    return "\n".join(lines)


def render_equity_lens(result_gdf: gpd.GeoDataFrame) -> None:
    st.subheader("Equity lens")
    candidate_cols = [c for c in ["PerCapitaI", "HI_block", "age_18to65"] if c in result_gdf.columns]
    if not candidate_cols:
        st.info("Equity factors not available. They appear when enriched block files are present.")
        return

    plot_df = result_gdf[["accessibility_score", *candidate_cols]].copy()
    for col in candidate_cols:
        plot_df[col] = pd.to_numeric(plot_df[col], errors="coerce")

    vuln_components = []
    if "PerCapitaI" in plot_df.columns:
        vuln_components.append(1.0 - _normalize_for_priority(plot_df["PerCapitaI"]))
    if "HI_block" in plot_df.columns:
        vuln_components.append(_normalize_for_priority(plot_df["HI_block"]))
    if "age_18to65" in plot_df.columns:
        vuln_components.append(_normalize_for_priority(plot_df["age_18to65"]))

    plot_df["vulnerability"] = pd.concat(vuln_components, axis=1).mean(axis=1)

    # ── FIX: handle duplicate bin edges robustly ──────────────────────────────
    quartile_labels = ["Q1 Least vulnerable", "Q2", "Q3", "Q4 Most vulnerable"]
    try:
        n_unique = int(plot_df["vulnerability"].nunique())
        n_bins = min(4, max(2, n_unique))
        labels = quartile_labels[:n_bins]
        plot_df["vulnerability_quartile"] = pd.qcut(
            plot_df["vulnerability"], q=n_bins, labels=labels, duplicates="drop"
        )
    except Exception:
        # Fallback: assign all blocks to a single bucket
        plot_df["vulnerability_quartile"] = "Q1 Least vulnerable"
    # ─────────────────────────────────────────────────────────────────────────

    summary = plot_df.groupby("vulnerability_quartile", observed=False)["accessibility_score"].mean().reset_index()
    summary = summary.rename(columns={"accessibility_score": "mean_accessibility_score"})
    st.caption("Q1–Q4 are vulnerability quartiles. Q1 = least vulnerable 25%, Q4 = most vulnerable 25%.")
    st.bar_chart(summary.set_index("vulnerability_quartile"), use_container_width=True)


def main() -> None:
    st.set_page_config(page_title="Healthcare Access Equity Intelligence", layout="wide")
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap');
    :root{--bg-main:#0c0f14;--bg-panel:#141922;--bg-soft:#1b222e;--text-main:#eef2f7;--text-soft:#a8b3c2;--accent:#3ec7a6;--accent-alt:#f2a65a}
    .stApp{background:radial-gradient(circle at 15% 0%,#1a2230 0%,#0c0f14 42%,#090b10 100%);font-family:'IBM Plex Sans',sans-serif;color:var(--text-main)}
    h1,h2,h3,.stMarkdown h1,.stMarkdown h2,.stMarkdown h3{font-family:'Space Grotesk',sans-serif;letter-spacing:.02em;color:var(--text-main)}
    p,span,label,div{color:var(--text-main)}
    [data-testid="stHeader"]{background:rgba(8,10,14,.78);border-bottom:1px solid rgba(255,255,255,.06)}
    [data-testid="stDecoration"]{background:transparent}
    [data-testid="stSidebar"]{background:linear-gradient(180deg,#121722 0%,#0d121a 100%);border-right:1px solid rgba(255,255,255,.08)}
    div[data-baseweb="select"]>div{background:#1b222e!important;color:var(--text-main)!important;border-color:rgba(255,255,255,.2)!important}
    div[data-baseweb="select"] input{color:var(--text-main)!important;-webkit-text-fill-color:var(--text-main)!important}
    div[data-baseweb="popover"]{background:#1b222e!important;color:var(--text-main)!important;border:1px solid rgba(255,255,255,.12)}
    ul[role="listbox"],[role="listbox"]{background:#1b222e!important}
    ul[role="listbox"] li,[role="option"]{color:var(--text-main)!important;background:#1b222e!important}
    ul[role="listbox"] li:hover,[role="option"]:hover{background:#253044!important}
    [aria-selected="true"][role="option"]{background:#2a3a52!important}
    [data-testid="stToolbar"]{visibility:hidden;height:0;position:fixed}
    [data-testid="stMetric"]{background:linear-gradient(160deg,rgba(30,38,52,.88) 0%,rgba(20,25,34,.9) 100%);border:1px solid rgba(62,199,166,.22);border-radius:14px;padding:.45rem .7rem;box-shadow:0 10px 28px rgba(0,0,0,.35)}
    .stButton button{background:linear-gradient(90deg,var(--accent) 0%,var(--accent-alt) 100%);color:#071015;border:0;font-weight:700}
    .stButton button:hover{filter:brightness(1.08)}
    [data-testid="stDataFrame"]{background:var(--bg-panel);border:1px solid rgba(255,255,255,.08);border-radius:12px}
    .insight-card{background:linear-gradient(150deg,rgba(20,25,34,.95) 0%,rgba(28,35,48,.92) 100%);border:1px solid rgba(242,166,90,.25);border-radius:12px;padding:.8rem .95rem;margin-bottom:.55rem;color:var(--text-main)}
    .insight-title{color:var(--accent);font-weight:700;margin-bottom:.2rem}
    .insight-body{color:var(--text-soft);font-size:.92rem;line-height:1.38}
    </style>
    """, unsafe_allow_html=True)

    st.title("Healthcare Access Equity Intelligence")
    st.caption("Enhanced Two-Step Floating Catchment Area (2SFCA) for policy-grade city accessibility analysis")

    with st.sidebar:
        st.header("Case Study")
        city_name = st.selectbox("City", list(CITY_SPECS.keys()))
        st.header("Parameters")
        d0_m = st.slider("Catchment radius (meters)", min_value=400, max_value=3000, value=1200, step=100)
        supply_variant = st.selectbox("Supply variant", _derive_supply_variant_options(city_name))
        st.caption("Type-weighted uses facility metadata when available; otherwise falls back to loaded supply values.")
        supply_multiplier = st.slider("Scenario supply multiplier", min_value=0.50, max_value=1.50, value=1.00, step=0.05)
        st.header("Map layers")
        map_mode = st.radio("Thematic map", ["Accessibility", "Population", "Bivariate"], index=0)
        split_compare_mode = st.checkbox("Split compare mode", value=False)
        compare_modes = ["Accessibility", "Bivariate"]
        if split_compare_mode:
            left_mode = st.selectbox("Left map", compare_modes, index=0)
            right_mode = st.selectbox("Right map", compare_modes, index=1)
        else:
            left_mode = map_mode
            right_mode = "Bivariate"
        show_underserved = st.checkbox("Underserved overlay", value=True)
        show_facilities = st.checkbox("Facility markers", value=True)
        show_street_network = st.checkbox("Street network overlay", value=False)
        show_county_boundaries = st.checkbox("County boundaries (context)", value=False)
        census_api_key = os.getenv("CENSUS_API_KEY", "")

    city = CITY_SPECS[city_name]
    facility_type = FACILITY_DATASETS[city_name]["label"]

    current_signature = {
        "city": city_name, "d0_m": int(d0_m),
        "supply_variant": supply_variant, "supply_multiplier": float(supply_multiplier),
    }
    run_requested = st.button("Run Enhanced 2SFCA", type="primary", use_container_width=True)

    if "dashboard_state" not in st.session_state:
        st.session_state["dashboard_state"] = None
    if "last_metrics_by_city" not in st.session_state:
        st.session_state["last_metrics_by_city"] = {}
    if "baseline_results_by_city" not in st.session_state:
        st.session_state["baseline_results_by_city"] = {}

    saved_state = st.session_state["dashboard_state"]

    if run_requested:
        # ── FIX: load from cached parquet first (instant), recompute only if needed ──
        cached = load_cached_city_outputs(city)
        if cached is not None and float(supply_multiplier) == 1.0:
            result, facilities = cached
            live_mode = False
            st.success("Loaded from pre-computed pipeline results.")
        else:
            with st.spinner("Loading city inputs..."):
                try:
                    blocks, facilities = load_city_inputs(city, census_api_key or None, supply_variant=supply_variant)
                    live_mode = True
                except Exception as exc:
                    if cached is None:
                        st.error(f"Could not load city inputs: {exc}")
                        st.stop()
                    result, facilities = cached
                    live_mode = False
                    st.warning("Live ingestion failed; showing latest precomputed results.")

            if live_mode:
                if float(supply_multiplier) != 1.0:
                    facilities = facilities.copy()
                    facilities["supply"] = pd.to_numeric(facilities["supply"], errors="coerce").fillna(0.0) * float(supply_multiplier)
                    st.info(f"Scenario: supply scaled by x{supply_multiplier:.2f}")
                with st.spinner("Preparing enhanced inputs..."):
                    blocks_enriched = enrich_for_enhanced_model(blocks, city)
                with st.spinner("Running enhanced 2SFCA (this may take a few minutes)..."):
                    result = run_enhanced(city, facilities, blocks_enriched, d0_m=d0_m)

        result = _sanitize_scores(result)
        st.session_state["dashboard_state"] = {"signature": current_signature, "result": result, "facilities": facilities}
        if float(supply_multiplier) == 1.0:
            st.session_state["baseline_results_by_city"][city_name] = result.copy()
        saved_state = st.session_state["dashboard_state"]

    if saved_state is None:
        st.info("Select inputs and click **Run Enhanced 2SFCA**.")
        return

    if saved_state["signature"] != current_signature and not run_requested:
        st.info("Parameters changed. Click Run Enhanced 2SFCA to refresh.")

    result = saved_state["result"]
    facilities = saved_state["facilities"]
    result = add_bivariate_class(result, city)
    result = result.copy()
    result["county_fips"] = result["GEOID"].astype(str).str.zfill(12).str[:5]
    county_name_map = COUNTY_NAMES_BY_CITY.get(city_name, {})
    result["county_name"] = result["county_fips"].map(county_name_map).fillna(result["county_fips"])

    county_stats = (
        result.groupby(["county_name", "county_fips"], observed=False)
        .size().reset_index(name="n_blocks")
        .sort_values(["county_name", "county_fips"])
    )
    county_display_map = {
        row["county_name"]: f"{row['county_name']} ({int(row['n_blocks']):,} blocks)"
        for _, row in county_stats.iterrows()
    }
    county_options = county_stats["county_name"].tolist()

    filter_c1, filter_c2 = st.columns([2, 3])
    if len(county_options) == 1:
        selected_counties = county_options
        filter_c1.info(f"Single county: {county_display_map[county_options[0]]}")
    else:
        selected_counties = filter_c1.multiselect(
            "County filters", options=county_options, default=county_options,
            format_func=lambda x: county_display_map.get(x, x),
        )
    percentile_range = filter_c2.slider("Accessibility score percentile brush", 0, 100, (0, 100), step=5)

    filtered = result[result["county_name"].isin(selected_counties)].copy() if selected_counties else result.iloc[0:0].copy()
    if not filtered.empty:
        lower_q = float(filtered["accessibility_score"].quantile(percentile_range[0] / 100.0))
        upper_q = float(filtered["accessibility_score"].quantile(percentile_range[1] / 100.0))
        filtered = filtered[(filtered["accessibility_score"] >= lower_q) & (filtered["accessibility_score"] <= upper_q)].copy()

    if filtered.empty:
        st.warning("No blocks remain after filters. Reset county or percentile filters.")
        return

    county_boundaries = filtered[["county_name", "geometry"]].dissolve(by="county_name", as_index=False)
    result_4326 = filtered.to_crs("EPSG:4326")
    facilities_4326 = facilities.to_crs("EPSG:4326")
    street_network = load_street_network(city) if show_street_network else None
    street_network_4326 = street_network.to_crs("EPSG:4326") if street_network is not None else None
    county_boundaries_4326 = county_boundaries.to_crs("EPSG:4326")

    mean_score = float(filtered["accessibility_score"].mean())
    zero_pct = float((filtered["accessibility_score"] == 0).mean() * 100)
    p90 = float(filtered["accessibility_score"].quantile(0.9))
    n_fac = int(len(facilities_4326))
    covered_pop = int(filtered["population"].sum())

    current_metrics = {"mean_score": mean_score, "zero_pct": zero_pct, "p90": p90, "covered_pop": float(covered_pop)}
    previous_metrics = st.session_state["last_metrics_by_city"].get(city_name)
    if run_requested:
        st.session_state["last_metrics_by_city"][city_name] = current_metrics

    mean_delta = None if previous_metrics is None else mean_score - float(previous_metrics["mean_score"])
    zero_delta = None if previous_metrics is None else zero_pct - float(previous_metrics["zero_pct"])
    p90_delta = None if previous_metrics is None else p90 - float(previous_metrics["p90"])
    pop_delta = None if previous_metrics is None else covered_pop - float(previous_metrics["covered_pop"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Mean enhanced score", f"{mean_score:.6f}", None if mean_delta is None else f"{mean_delta:+.6f}")
    c2.metric("Zero-access blocks", f"{zero_pct:.1f}%", None if zero_delta is None else f"{zero_delta:+.2f}%", delta_color="inverse")
    c3.metric("90th percentile", f"{p90:.6f}", None if p90_delta is None else f"{p90_delta:+.6f}")
    c4.metric("Population in view", f"{covered_pop:,}", None if pop_delta is None else f"{pop_delta:+,.0f}")
    st.caption(f"Showing {len(filtered):,} blocks · {n_fac:,} {facility_type} facilities")

    st.subheader("Executive insights")
    priority_share = float((filtered["bivariate_class"] == "Priority (High pop, Low access)").mean() * 100)
    top_gap_geoid = str(filtered.sort_values(["accessibility_score", "population"], ascending=[True, False]).iloc[0]["GEOID"])
    insight_col1, insight_col2, insight_col3 = st.columns(3)
    with insight_col1:
        st.markdown(f"<div class='insight-card'><div class='insight-title'>Coverage Stress</div><div class='insight-body'>{zero_pct:.1f}% of blocks have zero measurable access. These zones should be first-pass intervention targets.</div></div>", unsafe_allow_html=True)
    with insight_col2:
        st.markdown(f"<div class='insight-card'><div class='insight-title'>Bivariate Priority Load</div><div class='insight-body'>{priority_share:.1f}% of blocks are High population + Low access, indicating concentrated equity pressure.</div></div>", unsafe_allow_html=True)
    with insight_col3:
        st.markdown(f"<div class='insight-card'><div class='insight-title'>Most Underserved Block</div><div class='insight-body'>Block {top_gap_geoid} is the weakest combined signal in view (low access + high demand).</div></div>", unsafe_allow_html=True)

    layer_settings = {
        "map_mode": map_mode, "underserved": show_underserved, "facilities": show_facilities,
        "street_network": show_street_network, "county_boundaries": show_county_boundaries,
    }

    st.subheader("Interactive choropleth map")
    if split_compare_mode:
        left_col, right_col = st.columns(2)
        with left_col:
            st.caption(f"Left: {left_mode}")
            render_interactive_choropleth(result_4326, facilities_4326, city, facility_type,
                                          {**layer_settings, "map_mode": left_mode},
                                          street_network_4326, county_boundaries_4326)
        with right_col:
            st.caption(f"Right: {right_mode}")
            render_interactive_choropleth(result_4326, facilities_4326, city, facility_type,
                                          {**layer_settings, "map_mode": right_mode},
                                          street_network_4326, county_boundaries_4326)
    else:
        render_interactive_choropleth(result_4326, facilities_4326, city, facility_type,
                                      layer_settings, street_network_4326, county_boundaries_4326)

    st.subheader("Priority blocks for intervention")
    priority = compute_priority_blocks(filtered)
    st.dataframe(priority.head(20), use_container_width=True)
    st.caption("Priority index combines low accessibility, high population, and vulnerability proxies.")

    st.subheader("Actionable recommendations")
    recommendations = build_recommendations(priority, facility_type)
    st.dataframe(recommendations.head(10), use_container_width=True)

    st.subheader("Scenario impact")
    baseline_city = st.session_state["baseline_results_by_city"].get(city_name)
    if baseline_city is not None:
        baseline_city = baseline_city.copy()
        baseline_city["county_fips"] = baseline_city["GEOID"].astype(str).str.zfill(12).str[:5]
        baseline_city["county_name"] = baseline_city["county_fips"].map(county_name_map).fillna(baseline_city["county_fips"])
        baseline_filtered = baseline_city[baseline_city["county_name"].isin(selected_counties)].copy() if selected_counties else baseline_city.iloc[0:0].copy()
        if not baseline_filtered.empty:
            low_q = float(baseline_filtered["accessibility_score"].quantile(percentile_range[0] / 100.0))
            hi_q = float(baseline_filtered["accessibility_score"].quantile(percentile_range[1] / 100.0))
            baseline_filtered = baseline_filtered[(baseline_filtered["accessibility_score"] >= low_q) & (baseline_filtered["accessibility_score"] <= hi_q)].copy()
        if not baseline_filtered.empty:
            b_mean = float(baseline_filtered["accessibility_score"].mean())
            b_zero = float((baseline_filtered["accessibility_score"] == 0).mean() * 100)
            s1, s2 = st.columns(2)
            s1.metric("Scenario vs baseline mean", f"{mean_score:.6f}", f"{(mean_score - b_mean):+.6f}")
            s2.metric("Scenario vs baseline zero-access", f"{zero_pct:.2f}%", f"{(zero_pct - b_zero):+.2f}%", delta_color="inverse")
        else:
            st.info("Baseline exists but current filters exclude all baseline blocks.")
    else:
        st.info("Run baseline first (multiplier = 1.00) to unlock scenario impact deltas.")

    st.subheader("Audience question mode")
    answers = build_audience_answers(filtered, priority, recommendations, facility_type)
    selected_question = st.selectbox("Ask a common policy question", list(answers.keys()))
    st.markdown(f"<div class='insight-card'><div class='insight-title'>Answer</div><div class='insight-body'>{answers[selected_question]}</div></div>", unsafe_allow_html=True)

    brief_text = build_policy_brief_text(city_name, facility_type, filtered, recommendations, zero_pct, mean_score, p90)
    st.download_button(
        label="Download policy brief (Markdown)",
        data=brief_text.encode("utf-8"),
        file_name=f"{city.state_abbrev.lower()}_{facility_type.lower().replace(' ', '_')}_policy_brief.md",
        mime="text/markdown", use_container_width=True,
    )

    render_equity_lens(filtered)

    st.subheader("Top 25 blocks by enhanced score")
    top = filtered[["GEOID", "population", "accessibility_score", "accessibility_norm"]].sort_values(
        "accessibility_score", ascending=False).head(25)
    st.dataframe(top, use_container_width=True)

    csv = filtered.drop(columns="geometry").to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download enhanced scores CSV",
        data=csv,
        file_name=f"{city.state_abbrev.lower()}_{facility_type.lower().replace(' ', '_')}_enhanced_2sfca.csv",
        mime="text/csv", use_container_width=True,
    )

    st.caption(
        "Data loaded using local snapshots first, API fallback when needed. "
        "Sociodemographic factors joined from enriched block files when available."
    )


if __name__ == "__main__":
    main()
