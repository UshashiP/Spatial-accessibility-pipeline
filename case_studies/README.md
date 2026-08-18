# Case Studies

Two reproducible case studies demonstrate the Enhanced 2SFCA pipeline.

| File | City | Facility type | Catchment (d₀) | CRS |
|------|------|--------------|----------------|-----|
| [`dc.yaml`](dc.yaml) | Washington DC | Intermediate Care Facilities (ICF) | 900 m | EPSG:26985 |
| [`nyc.yaml`](nyc.yaml) | New York City | Dialysis facilities | 1 200 m | EPSG:32618 |

## Running a case study

```bash
python run_pipeline.py --config case_studies/dc.yaml
python run_pipeline.py --config case_studies/nyc.yaml
```

## Interactive dashboard

The Streamlit dashboard supports both cities:

```bash
streamlit run dashboard/enhanced_2sfca_dashboard.py
```

Select the city and facility type from the sidebar, provide an optional Census API key for live block data, and hit **Run analysis**.

## Data requirements

Both configs default to `snapshot` mode (`data.snapshot.use_snapshot: true`), which reads from local shapefiles under `data/intermediate_files/`.  Set `use_snapshot: false` to fetch live data from the Census and CMS APIs.

**DC enriched blocks** (`blocksandtract_economic_final.shp`) and **NYC enriched blocks** (`blocks_New_York_City_enhanced.shp`) must contain these columns for the sociodemographic demand weighting in the Enhanced 2SFCA model:

| Column | Description | Normalised range |
|--------|-------------|-----------------|
| `PerCapitaI` | Per-capita income | [0, 1] |
| `HI_block` | Health-insurance coverage rate | [0, 1] |
| `age_18to65` | Working-age population fraction | [0, 1] |

Missing columns default to `0.0` (equal-weight baseline).
