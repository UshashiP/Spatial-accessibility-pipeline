# Case Studies

Three reproducible case studies demonstrate the SDW-2SFCA pipeline.

| File | City | Facility type | Catchment (d₀) | CRS |
|------|------|--------------|----------------|-----|
| [`dc.yaml`](dc.yaml) | Washington DC | Intermediate Care Facilities (ICF) | 900 m | EPSG:26985 |
| [`nyc.yaml`](nyc.yaml) | New York City | Dialysis facilities | 1,200 m | EPSG:32618 |
| [`la_fqhc.yaml`](la_fqhc.yaml) | Los Angeles | Federally Qualified Health Centers | 1,600 m | EPSG:32611 |

## Running a case study

```bash
python run_pipeline.py --config case_studies/dc.yaml
python run_pipeline.py --config case_studies/nyc.yaml
python run_pipeline.py --config case_studies/la_fqhc.yaml
```

## Interactive dashboard

The Healthcare Access Intelligence Dashboard displays pre-computed results for all three cities:

```bash
python launch_dashboard.py
# or directly:
streamlit run dashboard/app_modern.py
```

Select the city from the sidebar to explore accessibility scores, Lorenz curves, priority zones, and inequality analysis with a modern, intuitive interface.

## Data requirements

All configs support both **API mode** (live data from Census/CMS) and **local mode** (pre-downloaded shapefiles).

**Recommended workflow:**
1. Download local data using acquisition scripts:
   ```bash
   python scripts/acquire_dc_data.py
   python scripts/acquire_nyc_data.py
   python scripts/acquire_la_data.py
   ```

2. Configure to use local shapefiles by setting in your YAML:
   ```yaml
   data:
     snapshot:
       use_snapshot: true
     local_shapefiles:
       facilities: "data/intermediate_files/<facility_file>.shp"
       census_blocks: "data/intermediate_files/<blocks_file>.shp"
   ```

3. Run the pipeline as shown above.

**DC enriched blocks** (`blocksandtract_economic_final.shp`) and **NYC enriched blocks** (`blocks_New_York_City_enhanced.shp`) must contain these columns for the sociodemographic demand weighting in the SDW-2SFCA model:

| Column | Description | Normalised range |
|--------|-------------|-----------------|
| `PerCapitaI` | Per-capita income | [0, 1] |
| `HI_block` | Health-insurance coverage rate | [0, 1] |
| `age_18to65` | Working-age population fraction | [0, 1] |

Missing columns default to `0.0` (equal-weight baseline).
