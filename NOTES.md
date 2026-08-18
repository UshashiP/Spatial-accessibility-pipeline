# Personal Project Notes
> This file is gitignored — local reference only.

---

## Repo Structure & What Is Public

This folder is the single source of truth for everything.
The GitHub remote (`Accessibility-2SFCA-`) is the **public portfolio repo**.

### What IS pushed (public):
- `pipeline/` — production DE pipeline (ingest → validate → transform → store → visualize)
- `dags/` — Airflow DAG
- `tests/` — pytest suite
- `notebooks/01–05` — pipeline EDA notebooks (01-03 standalone, 04-05 use pipeline)
- `outputs/figures/` — all method output maps (visual proof)
- `outputs/results/` — accessibility score CSVs and GeoParquet
- `run_pipeline.py`, `config.yaml`, `Dockerfile`, `docker-compose.yml`, `Makefile`
- `requirements.txt`, `requirements-dev.txt`

### What is NOT pushed (gitignored):
- `scripts/` — novel enhanced 2SFCA method, pending publication
- `archived_scripts/` — old experimental scripts
- `data/` — large shapefiles (blocks, ICF facilities) — load locally
- `myenv/`, `.venv/` — virtual environments
- Research notebooks (see below)
- This file (`NOTES.md`)

---

## The Two Versions of 2SFCA

| | File | Status |
|---|---|---|
| **Standard Gaussian 2SFCA** | `pipeline/transform/sfca_2.py` | Public — Luo & Wang (2003), used as reproducible DE baseline |
| **Novel Enhanced 2SFCA** | `scripts/accessibility_methods/advanved2SFCA_block.py` | **Private** — novel enhancements, pending publication |

The public pipeline uses the standard version. The enhanced version was run locally and its output (`outputs/figures/enhanced_2sfca_accessibility.png`) is committed so it can be shown in the README without exposing the method code.

---

## Research Notebooks (kept local, not pushed)

These are in `notebooks/` on disk but gitignored. They document the research process.

| Notebook | What it does |
|---|---|
| `data_preparation.ipynb` | Original data cleaning and shapefile prep |
| `eda_exploration.ipynb` | Exploratory analysis of accessibility patterns |
| `clustering_access.ipynb` | Spatial clustering of accessibility scores |
| `gap_statistics_clustering.ipynb` | Gap statistic to find optimal cluster count |
| `accessibility_api_python.ipynb` | Early API exploration |
| `accessibility_webmap.ipynb` | Interactive webmap prototype |

---

## Comparison Methods

All comparison scripts live in `scripts/comparison_analysis/` (gitignored).
Outputs are in `outputs/figures/` and `outputs/results/` (public).

Methods compared:
- `hansen_accessibility.py` → Hansen gravity model → `outputs/figures/hansen_accessibility.png`
- `cumulative opportunity method.py` → `outputs/figures/cumulative_opportunity_accessibility.png`
- `gravitybased.py` → `outputs/figures/gravity_accessibility.png`
- Novel enhanced 2SFCA → `outputs/figures/enhanced_2sfca_accessibility.png`
- Standard pipeline 2SFCA → `outputs/figures/accessibility_2sfca_map.png`

---

## Data Files (local only, never pushed)

All in `data/intermediate_files/`:
- `blocks_Washington_DC.shp` — 6,012 DC census blocks (2020), EPSG:26985
- `ICFs_DC.shp` — 114 ICF/IID facilities in DC

Key column facts:
- Census shapefile: use `Total Popu` for population (not `Bl_totpop` which is fractional weights 0–1)
- Facilities shapefile: `BEDS` = bed count, `NAME` = facility name

---

## Pipeline Key Decisions

- **CRS**: EPSG:26985 (Maryland State Plane NAD83, metres) throughout
- **Catchment radius**: 900 m (set in `config.yaml`)
- **2SFCA decay**: Gaussian kernel
- **API fallback**: Both Census TIGER and CMS APIs fall back to local shapefiles automatically when they fail
- **S3 fallback**: When `S3_BUCKET` env var is not set, results write to `outputs/results/` locally
- **`.venv` is broken** — use anaconda Python directly (`conda activate base` or `which python`)

---

## Git

- Remote: `https://github.com/UshashiP/Accessibility-2SFCA-.git`
- Working branch: `healthcare_acc_pipeline`
- `main` branch has original research notebooks only (pre-pipeline work)
