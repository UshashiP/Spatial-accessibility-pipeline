# Healthcare Accessibility Research Project
## Comprehensive Project Summary for Proposal Submission

---

## 1. PROJECT OVERVIEW

### Executive Summary
This is a **production-grade geospatial data engineering pipeline** that measures healthcare accessibility disparities across urban census blocks using the Enhanced Two-Step Floating Catchment Area (2SFCA) method. The project demonstrates a complete medallion architecture (Bronze → Silver → Gold) with live API integrations, automated workflows, interactive dashboards, and publication-ready visualizations.

**Research Focus**: Mapping and quantifying healthcare access deserts in underserved urban communities, with sociodemographic demand weighting to expose equity gaps.

**Target Audience**: Healthcare policy makers, health equity researchers, urban planners, and data engineers.

**Repository**: https://github.com/UshashiP/Accessibility-2SFCA-

---

## 2. RESEARCH METHODOLOGY

### Enhanced 2SFCA Method

The **Two-Step Floating Catchment Area (2SFCA)** is a spatial accessibility measure from health geography literature (Luo & Wang, 2003). This project enhances the standard method with two innovations:

#### Step 1: Supply-Side Catchment (Facility Perspective)
```
For each facility f:
    catchment(f) = facilities within radius d₀ from f
    supply_ratio(f) = beds(f) / sum(beds in catchment(f))
```

#### Step 2: Demand-Side Catchment (Block Perspective) with Enhancements
```
For each census block b:
    accessibility(b) = Σ(supply_ratio(f) × decay_weight(d) × sociodemographic_demand(b))
    
    where:
    - decay_weight(d) = truncated Gaussian (reaches 0 at d₀, not asymptotic)
    - sociodemographic_demand(b) = weighted combination of:
        • Per-capita income normalization
        • Health insurance coverage rate
        • Working-age population fraction (18–65 years)
```

### Key Enhancements

1. **Truncated Gaussian Decay**: Unlike standard Gaussian kernels (asymptotic to 0), this decay function reaches exactly 0 at the catchment boundary, providing cleaner interpretation and computational efficiency.

2. **Sociodemographic Demand Weighting**: Not all blocks have equal healthcare needs. The model scales effective demand by:
   - `PerCapitaI`: Per-capita income (inversely related to burden)
   - `HI_block`: Health insurance coverage (uninsured populations have higher need)
   - `age_18to65`: Working-age fraction (chronic disease patterns vary by age)
   
   This prevents deprived communities from being under-counted in supply-demand ratios.

3. **Spatial Index Optimization**: Uses `scipy.cKDTree` to reduce complexity from O(N·M) to O(N·k), where k is average facilities per catchment (~20–50 facilities for 6K–65K blocks).

### Validation Metrics

- **Gini Coefficient**: Unweighted measure of inequality (0=perfect equity, 1=maximum inequality)
- **Lorenz Curve**: Cumulative distribution of accessibility across cumulative population
- **Zero-Access Blocks**: Count and population of completely underserved areas
- **Access Gap Charts**: Cumulative population with access ≤ threshold

---

## 3. CODEBASE STRUCTURE

### Repository Layout

```
healthcare_accessibility_research/
│
├── README.md                          # Public-facing documentation
├── NOTES.md                           # Private project notes
├── config.yaml                        # Central configuration (all parameters)
├── run_pipeline.py                    # Main entrypoint
│
├── pipeline/                          # ✅ PUBLIC — Production data pipeline
│   ├── __init__.py
│   ├── config.py                      # Configuration loader (12-factor app)
│   ├── run_pipeline.py                # 6-stage ETL orchestration
│   ├── visualize.py                   # Publication-ready visualization suite (5 outputs)
│   ├── duckdb_query.py                # Analytics layer on Gold data
│   │
│   ├── ingest/                        # Stage 1: Live API data acquisition
│   │   ├── __init__.py
│   │   ├── census_api.py              # Census Bureau TIGER blocks + demographics
│   │   └── cms_api.py                 # CMS provider locations (national datasets)
│   │
│   ├── validate/                      # Stage 2: Data quality gates (Bronze → Silver)
│   │   ├── __init__.py
│   │   └── data_quality.py            # CRS validation, geometry repair, null checks
│   │
│   ├── transform/                     # Stage 3: Accessibility computation (Silver → Gold)
│   │   ├── __init__.py
│   │   ├── sfca_2.py                  # ✅ PUBLIC — Standard 2SFCA (Luo & Wang 2003)
│   │   └── sfca_enhanced.py           # Enhanced 2SFCA (private pending publication)
│   │
│   └── store/                         # Stage 4: Medallion data lake
│       ├── __init__.py
│       └── s3_store.py                # Parquet + GeoParquet to S3 or local outputs/
│
├── dashboard/                         # ✅ Interactive Streamlit web app
│   ├── app.py                         # Placeholder (main is enhanced_2sfca_dashboard.py)
│   └── enhanced_2sfca_dashboard.py    # Full dashboard (DC, NYC, LA case studies)
│
├── dags/                              # Airflow DAG for scheduled pipeline runs
│   └── accessibility_pipeline_dag.py
│
├── case_studies/                      # Configuration for reproducible studies
│   ├── README.md
│   ├── dc.yaml                        # Washington DC, Intermediate Care Facilities
│   ├── nyc.yaml                       # New York City, Dialysis Facilities
│   └── la_fqhc.yaml                   # Los Angeles, FQHCs
│
├── notebooks/                         # ✅ Jupyter analysis & documentation
│   ├── 01_ingest_census.ipynb         # Census data exploration
│   ├── 02_ingest_facilities.ipynb     # Facility data exploration
│   ├── 03_validate.ipynb              # Data quality validation
│   ├── 04_transform_2sfca.ipynb       # 2SFCA computation walkthrough
│   ├── 05_visualize.ipynb             # Visualization output examples
│   ├── eda_exploration.ipynb          # Accessibility pattern analysis
│   ├── clustering_access.ipynb        # K-means spatial clustering
│   └── ... (other research notebooks)
│
├── tests/                             # Pytest test suite
│   ├── conftest.py                    # Fixtures
│   ├── test_ingest.py                 # API mocking, schema validation
│   ├── test_validate.py               # Data quality rules
│   ├── test_transform.py              # 2SFCA math verification
│   └── test_store.py                  # Parquet I/O
│
├── scripts/                           # ⚠️ PRIVATE — Novel research code (not pushed)
│   ├── accessibility_methods/         # Enhanced 2SFCA implementation (pending publication)
│   ├── comparison_analysis/           # Alternative methods (Hansen, gravity, etc.)
│   └── database/                      # PostgreSQL + PostGIS schema design
│
├── archived_scripts/                  # ⚠️ PRIVATE — Legacy experimental code
│   └── (old 2SFCA iterations)
│
├── data/                              # ⚠️ PRIVATE — Large shapefiles (gitignored)
│   ├── intermediate_files/            # TIGER blocks, facility shapefiles, enriched datasets
│   ├── reference/                     # Citation databases, metadata
│   └── shapefiles/                    # Raw Census blocks
│
├── outputs/                           # ✅ PUBLIC — Results & visualizations
│   ├── results/
│   │   ├── bronze/                    # Raw ingested data (Parquet, timestamped)
│   │   ├── silver/                    # Validated data (Parquet)
│   │   └── gold/                      # Accessibility scores (GeoParquet + CSV)
│   └── figures/                       # All 5 visualization outputs (PNG)
│
├── logs/                              # Pipeline execution logs
│   └── case_runs/                     # Timestamped logs per case study run
│
├── docs/                              # Technical documentation
│   ├── DASHBOARD_DEPLOYMENT.md        # Docker, Streamlit Cloud, Render deployment
│   ├── DATA_ENGINEERING.md            # ETL architecture & design decisions
│   └── POSTGRES_INSTALLATION.md       # PostGIS database setup
│
├── myenv/                             # ⚠️ PRIVATE — Python virtual environment
├── Dockerfile                         # Container image for deployment
├── docker-compose.yml                 # Multi-container orchestration
├── Makefile                           # Workflow automation
├── requirements.txt                   # Production dependencies
├── requirements-dev.txt               # Development & testing dependencies
└── .gitignore                         # Excludes data, notebooks, env, scripts
```

### Public vs. Private Content

| Component | Status | Reason |
|-----------|--------|--------|
| `pipeline/` (ingest, validate, transform, store, visualize) | ✅ PUBLIC | Reproducible research + data engineering showcase |
| `notebooks/01–05` | ✅ PUBLIC | Educational + demonstrates pipeline usage |
| `outputs/figures/`, `outputs/results/` | ✅ PUBLIC | Visual proof + method validation |
| `config.yaml`, `Makefile`, `docker-compose.yml` | ✅ PUBLIC | DevOps/infrastructure as code |
| `scripts/accessibility_methods/` | ⚠️ PRIVATE | Novel methodology pending journal publication |
| `notebooks/` (research-specific) | ⚠️ PRIVATE | Sensitive research iterations |
| `data/` | ⚠️ PRIVATE | Large files (shapefiles > 100 MB), use local paths |

---

## 4. PIPELINE ARCHITECTURE

### ETL Medallion Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       STAGE 1: INGEST                            │
├─────────────────────────────────────────────────────────────────┤
│  Census Bureau TIGER API      │    CMS Provider API              │
│  (2020 blocks, demographics)  │    (National facility dataset)   │
│        ↓                      │           ↓                      │
│  ingest_census_blocks()       │    ingest_facilities()           │
│  - Fetch by State FIPS        │    - Fetch by facility type      │
│  - CRS: As-delivered          │    - CRS: As-delivered           │
│  - Columns: geom, pop, age... │    - Columns: geom, beds, name.. │
└─────────────┬──────────────────────────────┬────────────────────┘
              │                              │
              └──────────────┬───────────────┘
                             ▼
        ┌──────────────────────────────────────────────┐
        │      BRONZE LAYER (S3 or outputs/)          │
        │  write_bronze_population(gdf, config)      │
        │  write_bronze_facilities(gdf, config)      │
        │  Format: Parquet (partitioned by run_date) │
        └──────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼────────────────────────────────────────┐
│                   STAGE 2: VALIDATE                            │
├──────────────────────────────────────────────────────────────┤
│  validate_silver()                                            │
│  ✓ Check null geometries → drop or log                       │
│  ✓ Reproject to study-area CRS (EPSG:26985, etc.)          │
│  ✓ Repair invalid geometries (buffer(0), make_valid)        │
│  ✓ Validate schema (required columns present)               │
│  ✓ Log data quality metrics (row counts, bounds)            │
│  Fail mode: DataQualityError on hard failures               │
└──────────────┬───────────────────────────────────────────────┘
               │
        ┌──────▼────────────────────────────────────┐
        │    SILVER LAYER (S3 or outputs/)          │
        │  Cleaned, reprojected, ready for compute │
        │  Format: Parquet (same partitioning)     │
        └──────┬───────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────┐
│                STAGE 3: TRANSFORM                            │
├──────────────────────────────────────────────────────────────┤
│  compute_enhanced_2sfca(population, facilities, config)     │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━    │
│                                                               │
│  1. Clip facilities to study-area bounding box              │
│  2. For each facility: compute catchment ratio              │
│     - Find all facilities within radius d₀                 │
│     - Ratio = beds(f) / sum(beds in catchment)            │
│                                                               │
│  3. Build spatial index: cKDTree(facility centroids)        │
│     - O(N log N) build time                                │
│     - O(N·k) query time for k facilities/catchment         │
│                                                               │
│  4. For each block: compute accessibility                  │
│     - Query: "which facilities within d₀?"                │
│     - For each facility f in results:                      │
│        * weight = truncated_gaussian(distance, d₀)        │
│        * weight *= supply_ratio(f)                         │
│        * weight *= sociodemographic_scaling(block)        │
│        * accessibility += weight                           │
│                                                               │
│  5. Sociodemographic demand weighting (if enriched blocks)  │
│     - Scale = (PerCapitaI * HI_block * age_18to65) or 1.0 │
│     - Missing columns default to 0.0 (equal-weight)        │
│                                                               │
│  Return: GeoDataFrame with accessibility scores            │
└──────────────┬──────────────────────────────────────────────┘
               │
        ┌──────▼────────────────────────────────────┐
        │     GOLD LAYER (S3 or outputs/)          │
        │  Accessibility scores ready for viz      │
        │  Format: GeoParquet + CSV                │
        │  Partitioning: case_study / run_date    │
        └──────┬───────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────┐
│            STAGE 4: STORE & STAGE 5: ANALYTICS             │
├──────────────────────────────────────────────────────────────┤
│  write_gold_accessibility(result_gdf, config)              │
│  build_duckdb_analytics(gold_parquet_path)                 │
│                                                               │
│  DuckDB Views:                                              │
│  - analytics.block_scores                                   │
│  - analytics.aggregate_stats (Gini, zero_access_pop)      │
│  - analytics.facility_catchments                            │
└──────────────┬──────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────┐
│             STAGE 6: VISUALIZE                              │
├──────────────────────────────────────────────────────────────┤
│  plot_accessibility_map()      → choropleth (PNG)           │
│  plot_lorenz_curve()           → inequality analysis (PNG)  │
│  plot_bivariate_map()          → population × access (PNG)  │
│  plot_access_gap_chart()       → cumulative gaps (PNG)      │
│  plot_interactive_map()        → Folium HTML map            │
│                                                               │
│  All outputs: `outputs/figures/{state}_{facility}_*.png`   │
└──────────────────────────────────────────────────────────────┘
```

### Error Handling & Fallbacks

```python
# API fallback strategy
try:
    blocks = fetch_census_api(state_fips, county_fips)
except APITimeoutError:
    log.warning("Census API unavailable, falling back to local shapefile")
    blocks = read_shapefile(f"data/intermediate_files/blocks_{city}.shp")

# S3 fallback strategy
try:
    write_to_s3(data, s3_path, bucket=s3_bucket)
except S3CredentialsError:
    log.warning("S3 unavailable, writing to local outputs/")
    write_to_local(data, f"outputs/results/{relative_path}")
```

---

## 5. CASE STUDIES

### Three Cities, Three Facility Types

#### **Case Study 1: Washington DC — Intermediate Care Facilities (ICF)**

| Parameter | Value |
|-----------|-------|
| **Study Area** | Washington, DC (city limits) |
| **Facility Type** | Intermediate Care Facilities / IID (skilled nursing) |
| **Catchment Radius** | 900 m (~10 min walk) |
| **Census Blocks** | ~6,012 blocks |
| **Facilities** | 114 ICF/IID facilities |
| **Population** | ~620,000 residents |
| **CRS** | EPSG:26985 (Maryland State Plane NAD83, metres) |
| **Config** | [`case_studies/dc.yaml`](case_studies/dc.yaml) |
| **Data Sources** | TIGER 2020 blocks, CMS HCQIS provider directory |
| **Gini Coefficient** | 0.8203 (highly unequal distribution) |
| **Zero-Access Blocks** | ~1,200 blocks (20% of population) |

**Key Insight**: Large geographical disparities with outer wards (SE/NE) having significantly lower ICF accessibility, exacerbated by sociodemographic factors (lower income, higher uninsured rates).

---

#### **Case Study 2: New York City — Dialysis Facilities**

| Parameter | Value |
|-----------|-------|
| **Study Area** | New York City (5 boroughs) |
| **Facility Type** | Dialysis treatment centers (ESRD patients) |
| **Catchment Radius** | 1,200 m (~15 min walk) |
| **Census Blocks** | ~37,984 blocks |
| **Facilities** | 154 dialysis centers |
| **Population** | ~8.3 million residents |
| **CRS** | EPSG:32618 (UTM 18N, metres) |
| **Config** | [`case_studies/nyc.yaml`](case_studies/nyc.yaml) |
| **Data Sources** | TIGER 2020 blocks, CMS UNOS dialysis center directory |
| **Gini Coefficient** | 0.6555 (moderate inequality) |
| **Zero-Access Blocks** | ~4,100 blocks (29% of population) |
| **Special Features** | Live Census API fallback when local shapefiles unavailable |

**Key Insight**: Dialysis facilities cluster in Manhattan and outer outer-boroughs with connectivity challenges. NYC's diverse demographic landscape creates pockets of low accessibility despite overall network density.

---

#### **Case Study 3: Los Angeles — Federally Qualified Health Centers (FQHC)**

| Parameter | Value |
|-----------|-------|
| **Study Area** | Los Angeles County (urban core) |
| **Facility Type** | Federally Qualified Health Centers (FQHC, primary care) |
| **Catchment Radius** | 1,600 m (~20 min walk) |
| **Census Blocks** | ~65,485 blocks |
| **Facilities** | 630 FQHCs |
| **Population** | ~13 million residents |
| **CRS** | EPSG:2230 (California State Plane NAD83, metres) |
| **Config** | [`case_studies/la_fqhc.yaml`](case_studies/la_fqhc.yaml) |
| **Data Sources** | TIGER 2020 blocks, HRSA FQHC directory |
| **Gini Coefficient** | 0.7186 (moderate-high inequality) |
| **Zero-Access Blocks** | ~2,800 blocks (12% of population) |

**Key Insight**: FQHC network is more uniformly distributed than specialized care, but significant accessibility gaps persist in areas with topographical barriers (canyons, mountains) and sparse settlement.

---

## 6. DATA SOURCES

### Live APIs (Primary)

#### **U.S. Census Bureau TIGER / Decennial 2020**
- **Endpoint**: `https://data.census.gov/` (via `Census` Python package)
- **Data Retrieved**:
  - Census block geometries (2020 blocks, resolution ~300 m²)
  - Total population per block
  - Demographic columns (age distribution, race/ethnicity)
- **Fallback**: Local shapefile if API unavailable
- **Auth**: Census API key via `CENSUS_API_KEY` environment variable

#### **Centers for Medicare & Medicaid Services (CMS)**
- **Datasets Used**:
  - HCQIS Skilled Nursing Facilities directory (ICF)
  - UNOS Dialysis Center directory (Dialysis)
  - HRSA Federally Qualified Health Centers (FQHC)
- **Format**: CSV files with lat/lon, bed counts, facility names
- **Fallback**: Cached snapshots in `data/intermediate_files/`

### Local Reference Data

#### **Shapefiles (in `data/intermediate_files/`)**
```
blocks_Washington_DC.shp              (6,012 blocks, EPSG:26985)
blocks_New_York_City.shp              (37,984 blocks, EPSG:32618)
blocks_Los_Angeles_urban.shp          (65,485 blocks, EPSG:2230)

ICFs_DC.shp                            (114 ICF facilities, EPSG:26985)
Dialysis_NYC.shp                       (154 dialysis centers, EPSG:32618)
FQHC_LA.shp                            (630 FQHCs, EPSG:2230)

blocks_Los_Angeles_enhanced.shp        (LA blocks enriched with sociodemographic columns)
```

#### **Enriched Demographic Columns** (Optional)
When local shapefiles include sociodemographic enrichment:
```
PerCapitaI         [0, 1] normalized per-capita income
HI_block           [0, 1] health insurance coverage rate
age_18to65         [0, 1] working-age population fraction
```
If missing, defaults to 0.0 (equal-weight baseline).

---

## 7. TECHNICAL STACK

### Programming Languages
- **Python 3.11+** — Primary language for pipeline, analysis, dashboards
- **SQL** — DuckDB for analytical queries, PostGIS for spatial database (optional)
- **Bash** — Makefile automation, deployment scripts
- **YAML** — Configuration management

### Core Libraries

#### **Geospatial**
- **GeoPandas** — Vector data manipulation, CRS management, spatial joins
- **Shapely** — Geometry operations (buffer, intersection, union)
- **Folium** — Interactive web maps (Leaflet.js wrapper)
- **Pyproj** — Coordinate reference system transformations
- **scipy.cKDTree** — Spatial indexing for nearest-neighbor queries

#### **Data Processing**
- **Pandas** — Tabular data manipulation, aggregation, CSV I/O
- **NumPy** — Numerical arrays, vectorized operations, statistical functions
- **DuckDB** — In-process analytics SQL engine on Parquet files
- **Pyarrow** — Apache Arrow columnar format, GeoParquet support

#### **Visualization**
- **Matplotlib** — Static publication-ready plots (choropleth, Lorenz curves)
- **Branca** — Folium color map utilities

#### **Web Application**
- **Streamlit** — Rapid interactive dashboard prototyping
- **Pydantic** — Data validation and serialization

#### **Data Storage**
- **Parquet / GeoParquet** — Compressed columnar format for Bronze/Silver/Gold layers
- **PostgreSQL + PostGIS** — Spatial database (optional production backend)
- **Amazon S3** — Cloud object storage (optional)

#### **Development & Testing**
- **pytest** — Unit and integration testing
- **pytest-cov** — Code coverage reporting
- **black** — Code formatting
- **ruff** — Linting
- **mypy** — Static type checking (optional)

#### **Infrastructure**
- **Docker** — Container images for reproducible environments
- **Docker Compose** — Multi-container orchestration (Streamlit + PostGIS locally)
- **Airflow** — Scheduled pipeline DAGs (optional)

---

## 8. OUTPUT ARTIFACTS

### Bronze Layer (Raw Ingested Data)
**Location**: `outputs/results/bronze/run_date=YYYY-MM-DD/`
```
ca_fqhc_population.parquet         (65,485 rows, ~2 MB)
ca_fqhc_facilities.parquet         (630 rows, ~100 KB)
dc_icf_population.parquet          (6,012 rows, ~200 KB)
dc_icf_facilities.parquet          (114 rows, ~20 KB)
ny_dialysis_population.parquet     (37,984 rows, ~1.2 MB)
ny_dialysis_facilities.parquet     (154 rows, ~50 KB)
```
- **Schema**: Geometry column + raw API data + metadata
- **CRS**: As-delivered from Census/CMS (varies)
- **Format**: Parquet (compressed)

### Silver Layer (Validated, Standardized)
**Location**: `outputs/results/silver/run_date=YYYY-MM-DD/`
```
dc_icf_population.parquet          (6,012 rows, reprojected to EPSG:26985)
dc_icf_facilities.parquet          (114 rows, validated)
... (same for NYC, LA)
```
- **Schema**: Validated, nulls removed, CRS standardized
- **Quality Checks Applied**: Geometry validity, schema completeness, coordinate bounds
- **Format**: Parquet

### Gold Layer (Accessibility Scores)
**Location**: `outputs/results/gold/run_date=YYYY-MM-DD/`
```
dc_icf_accessibility.parquet       (6,012 blocks × 1 score = accessibility index)
ny_dialysis_accessibility.parquet  (37,984 blocks × 1 score)
ca_fqhc_accessibility.parquet      (65,485 blocks × 1 score)

dc_icf_accessibility.csv           (human-readable export)
ny_dialysis_accessibility.csv
ca_fqhc_accessibility.csv
```
- **Columns**: `geom` (Point), `block_id`, `population`, `accessibility_score`, `method`, `run_date`
- **Format**: GeoParquet (compressed columnar) + CSV
- **Statistics Embedded**: Gini coefficient, zero-access population, bounds

### Visualization Suite
**Location**: `outputs/figures/`

#### **1. Accessibility Choropleth Map** (`{state}_{facility}_accessibility_map.png`)
- **Type**: Static raster (300 DPI, publication-ready)
- **Features**:
  - Full block coverage choropleth with RdYlBu colormap (red=low, blue=high)
  - Facility locations overlay (black dots)
  - Semi-transparent block boundaries (alpha=0.45)
  - Map title with Gini coefficient and study area name
  - Scale bar, north arrow, legend
- **Dimensions**: 12×10 inches
- **Use Case**: Research papers, policy briefs, presentations

#### **2. Lorenz Curve & Gini Coefficient** (`{state}_{facility}_lorenz_curve.png`)
- **Type**: Line plot showing cumulative accessibility distribution
- **Content**:
  - X-axis: Cumulative population (0–100%)
  - Y-axis: Cumulative accessibility (0–100%)
  - Diagonal reference line (perfect equality)
  - Lorenz curve for study area
  - Gini value displayed (matches choropleth title)
  - Area shaded between curve and diagonal
- **Use Case**: Equity metrics, research papers

#### **3. Bivariate Map** (`{state}_{facility}_bivariate_map.png`)
- **Type**: 2×2 classification map (population density × accessibility)
- **Classes**:
  - High pop, high access (green)
  - High pop, low access (red) ← **priority areas**
  - Low pop, high access (light blue)
  - Low pop, low access (gray)
- **Use Case**: Priority area identification for interventions

#### **4. Access Gap Chart** (`{state}_{facility}_access_gap.png`)
- **Type**: Cumulative distribution function
- **Shows**: What % of population has accessibility ≤ threshold?
- **Use Case**: Setting minimum service standards

#### **5. Interactive Folium Map** (`{state}_{facility}_map.html`)
- **Type**: Zoomable web map (Leaflet.js)
- **Features**:
  - Block choropleth with hover tooltips (block ID, population, score)
  - Facility markers clickable (name, beds, address)
  - Layer control (satellite/street tiles)
  - Export button for CSV
- **Use Case**: Stakeholder engagement, policy forums

---

## 9. DASHBOARD APPLICATION

### Streamlit Interactive Dashboard
**File**: `dashboard/enhanced_2sfca_dashboard.py`

**Features**:
1. **City Selector**: Dropdown to switch between DC / NYC / LA
2. **Facility Type Selector**: Auto-populated from config (ICF, Dialysis, FQHC)
3. **Sociodemographic Weighting Toggle**: Enable/disable demand weighting
4. **Scenario Multiplier Slider**: Simulate 0.5–2.0× facility bed capacity
5. **Live Results Display**:
   - Updated accessibility choropleth
   - Summary statistics (Gini, zero-access population)
   - Facilities meeting demand vs. shortfall
6. **CSV Export**: Download accessibility scores to file

**Data Flow**:
```
User selects city → Load population (API or shapefile)
                 → Load facilities from S3 or local
                 → Run Enhanced 2SFCA
                 → Display results + metrics
                 → Export CSV
```

**Deployment Options**:
- **Local**: `streamlit run dashboard/enhanced_2sfca_dashboard.py`
- **Docker**: `docker-compose up streamlit`
- **Streamlit Cloud**: Push to GitHub, connect via dashboard.streamlit.io
- **Render.com**: Containerized deployment with environment secrets
- **AWS EC2 / Azure VM**: Manual setup with Nginx reverse proxy

---

## 10. CONFIGURATION SYSTEM

### Central Configuration File: `config.yaml`

```yaml
study_area:
  name: "Washington DC"
  state_abbrev: "dc"
  state_fips: 11
  county_fips: [1]  # DC is a single entity
  
facility:
  type: "intermediate_care_facility"
  label: "Intermediate Care Facilities"
  demand_column: "beds"  # facility supply metric
  
analysis:
  method: "enhanced_2sfca"
  method_label: "Enhanced 2SFCA with Sociodemographic Weighting"
  catchment_distance_m: 900  # catchment radius d₀
  decay_type: "truncated_gaussian"  # truncated vs. standard
  decay_bandwidth_m: 300
  
  # Sociodemographic demand weighting (if enriched blocks available)
  sociodemographic_columns:
    - "PerCapitaI"
    - "HI_block"
    - "age_18to65"
  
  # If columns missing, what value to use?
  missing_column_default: 0.0  # 0=equal-weight baseline
  
crs:
  epsg: 26985  # Maryland State Plane NAD83
  
data:
  snapshot:
    use_snapshot: true  # true = use local shapefiles, false = fetch API
    blocks_shapefile: "data/intermediate_files/blocks_Washington_DC.shp"
    facilities_shapefile: "data/intermediate_files/ICFs_DC.shp"
  
  output:
    figures: "outputs/figures"
    results: "outputs/results"

visualization:
  colormap: "RdYlBu"
  vmax_percentile: 95
  figure_dpi: 300
  figure_size: [12, 10]
  save_format: "png"
```

**Key Design Principle**: All study-area parameters live in YAML. Swap config to run different cities/methods without changing code.

---

## 11. TESTING & VALIDATION

### Test Suite
**Location**: `tests/`

```python
# test_ingest.py — Mock API responses, validate schema
def test_ingest_census_blocks():
    """Verify Census API call returns valid GeoDataFrame."""
    
def test_ingest_facilities_with_fallback():
    """Verify facilities fallback to shapefile when API fails."""

# test_validate.py — Data quality checks
def test_validate_null_geometries():
    """Nulls are removed, row count logged."""
    
def test_validate_crs_reprojection():
    """CRS is reprojected to target EPSG."""

# test_transform.py — 2SFCA math
def test_2sfca_truncated_gaussian_decay():
    """Decay reaches exactly 0 at d₀."""
    
def test_2sfca_sociodemographic_weighting():
    """Demand scaling applied correctly."""

# test_store.py — Parquet I/O
def test_write_gold_layer_creates_parquet():
    """Gold GeoParquet file created with correct schema."""
```

### Validation Metrics

| Metric | DC | NYC | LA |
|--------|----|----|-----|
| **Blocks Processed** | 6,012 | 37,984 | 65,485 |
| **Facilities Matched** | 114 | 154 | 630 |
| **% Blocks with Access** | 80% | 71% | 88% |
| **Gini Coefficient** | 0.8203 | 0.6555 | 0.7186 |
| **Mean Accessibility Score** | 2.1 | 1.8 | 3.4 |

---

## 12. DEPLOYMENT OPTIONS

### Option A: Local Development
```bash
# Install dependencies
pip install -r requirements-dev.txt

# Configure Census API key (if live ingestion needed)
export CENSUS_API_KEY="your-key-here"

# Run pipeline for DC
python run_pipeline.py --config case_studies/dc.yaml

# Launch dashboard
streamlit run dashboard/enhanced_2sfca_dashboard.py
```

### Option B: Docker (Isolated Environment)
```bash
# Build image
docker build -t healthcare-accessibility:latest .

# Run pipeline inside container
docker run --rm \
  -e CENSUS_API_KEY="your-key" \
  -v $(pwd)/outputs:/app/outputs \
  healthcare-accessibility:latest \
  python run_pipeline.py --config case_studies/dc.yaml

# Run Streamlit inside container
docker run -p 8501:8501 \
  -e CENSUS_API_KEY="your-key" \
  healthcare-accessibility:latest \
  streamlit run dashboard/enhanced_2sfca_dashboard.py
```

### Option C: Streamlit Cloud
```bash
# 1. Push code to GitHub (healthcare_acc_pipeline branch)
git push origin healthcare_acc_pipeline

# 2. Go to https://share.streamlit.io/
#    Connect GitHub account
#    Select repo + branch + app file

# 3. Add secrets in Streamlit Cloud console
#    CENSUS_API_KEY = "your-key"
#    S3_BUCKET = "optional-bucket-name"

# 4. Dashboard live at: https://yourusername-healthcare-accessibility.streamlit.app/
```

### Option D: AWS Deployment (Production)
```bash
# Push image to ECR
aws ecr get-login-password | docker login ...
docker tag healthcare-accessibility:latest $ECR_URL/healthcare-accessibility:latest
docker push $ECR_URL/healthcare-accessibility:latest

# Deploy on ECS/Fargate with environment secrets from AWS Secrets Manager
# Configure S3 bucket for medallion data lake
# Set up Airflow for scheduled pipeline runs
```

---

## 13. RESEARCH IMPACT & PUBLICATIONS

### Paper-Ready Outputs
- ✅ All three choropleth maps with correct statistical annotations
- ✅ Lorenz curves matching Gini coefficients
- ✅ Zero-access population statistics
- ✅ Bivariate maps showing priority areas
- ✅ Reproducible methods + code available

### Presentations
- **FOSS4G 2024**: "Measuring and Mapping Healthcare Access Deserts: An Enhanced 2SFCA Approach for Urban Census Blocks"
- **Health Geography Conference**: Comparative analysis of Standard vs. Enhanced 2SFCA
- **Urban Planning Workshop**: Policy implications of accessibility mapping

### Future Work
1. **PostGIS Database**: Migrate from Parquet to PostgreSQL + PostGIS for real-time querying
2. **Spatial Clustering**: K-means on accessibility scores to identify clusters of inequality
3. **Predictive Modeling**: Machine learning to forecast facility demand 2–5 years forward
4. **Network Analysis**: Graph-based routing on street networks instead of Euclidean distance
5. **Multi-City Comparison**: Standardized accessibility benchmarks across 50+ US metros

---

## 14. HOW TO USE THIS PROJECT FOR PROPOSAL SUBMISSION

### For Data Engineering Roles
**Highlight**: 
- Bronze → Silver → Gold medallion architecture
- Configuration-driven portability (swap YAML, run any city)
- Error handling & fallback strategies (API failures → local files)
- Parquet partitioning by `run_date` for scalability
- Docker containerization for reproducibility

### For Analytics Engineer Roles
**Highlight**:
- DuckDB analytics layer on Gold data
- SQL queries for Gini, zero-access, block profiles
- Dashboard built on top of gold layer
- Metrics validation pipeline

### For Research/Science Roles
**Highlight**:
- Novel Enhanced 2SFCA method with sociodemographic weighting
- Population-weighted Gini coefficient calculation
- Reproducible research with Jupyter notebooks
- Three case studies with 109,000+ census blocks

### For Full-Stack Engineer Roles
**Highlight**:
- End-to-end system (backend pipeline + frontend Streamlit dashboard)
- Multiple deployment options (local, Docker, cloud)
- API integrations (Census, CMS)
- Environment secrets management

---

## 15. KEY STATISTICS

| Metric | Value |
|--------|-------|
| **Lines of Code (Pipeline)** | ~3,500 |
| **Lines of Code (Dashboard)** | ~1,200 |
| **Test Coverage** | ~70% |
| **Configuration Parameters** | 40+ |
| **Supported Cities** | 3 (DC, NYC, LA) |
| **Facility Types** | 3 (ICF, Dialysis, FQHC) |
| **Total Census Blocks Analyzed** | 109,481 |
| **Total Facilities Mapped** | 898 |
| **Visualization Outputs** | 5 per city (15 total) |
| **Historical Runs** | 15+ (timestamped logs) |
| **Documentation Pages** | 8+ (README, docs/, notebooks) |

---

## 16. REPOSITORY INFORMATION

- **URL**: https://github.com/UshashiP/Accessibility-2SFCA-
- **Active Branch**: `healthcare_acc_pipeline` (latest development)
- **Main Branch**: Archived research notebooks only
- **License**: MIT (open source)
- **Status**: Production-ready pipeline + research-grade analytics

---

## Conclusion

This project demonstrates a **complete data engineering + geospatial analysis pipeline** suitable for healthcare policy, urban planning, and health equity research. The codebase showcases:

✅ **Production-Grade DevOps**: Configuration management, containerization, CI/CD-ready
✅ **Scalable Data Architecture**: Medallion medallion pattern on Parquet + optional PostGIS
✅ **Spatial Computing**: GeoPandas, CRS management, spatial indexing (cKDTree)
✅ **User-Facing Analytics**: Interactive Streamlit dashboard with export capabilities
✅ **Reproducible Research**: Jupyter notebooks, test suite, version-controlled configs
✅ **Publication-Ready Outputs**: Professional visualizations (choropleth, Lorenz, bivariate)

The enhanced 2SFCA method with sociodemographic weighting addresses equity gaps overlooked by standard approaches, making this suitable for both **academic research** and **policy-driven interventions**.
