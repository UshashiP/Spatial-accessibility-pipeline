"""
Spatial Accessibility Pipeline — end-to-end runner.

Stages
------
1. Ingest    — Census 2020 blocks + CMS facilities (API with local fallback)
2. Validate  — data quality gates (Bronze → Silver)
3. Transform — standard 2SFCA (Silver → Gold)
4. Store     — GeoParquet medallion store (S3 or local) + PostGIS (optional)
5. Analytics — DuckDB views on Gold layer
6. Visualize — full visualization suite (5 outputs)

All study area and facility parameters come from config.yaml.
To run a different city or facility type, change config.yaml only.

Usage
-----
    python run_pipeline.py
    python run_pipeline.py --config configs/nyc_rhc.yaml
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("run_pipeline")


def main(config_path: str | None = None) -> None:
    from pipeline.config import load_config
    config = load_config(config_path) if config_path else load_config()

    area = config["study_area"]["name"]
    fac  = config["facility"]["label"]
    log.info("=== Spatial Accessibility Pipeline ===")
    log.info("Study area: %s | Facility: %s", area, fac)

    # ── 1. Ingest ─────────────────────────────────────────────────────────
    log.info("--- Stage 1: Ingest ---")
    from pipeline.ingest.census_api import ingest_census_blocks
    from pipeline.ingest.cms_api import ingest_facilities
    from pipeline.store.s3_store import write_bronze_population, write_bronze_facilities

    population_gdf = ingest_census_blocks(config)
    log.info("Census blocks loaded: %d rows", len(population_gdf))

    facility_gdf = ingest_facilities(config)
    log.info("Facilities loaded: %d rows", len(facility_gdf))

    write_bronze_population(population_gdf, config=config)
    write_bronze_facilities(facility_gdf, config=config)

    # ── 2. Validate ───────────────────────────────────────────────────────
    log.info("--- Stage 2: Validate (Bronze → Silver) ---")
    from pipeline.validate.quality_gates import run_quality_gates
    from pipeline.store.s3_store import write_silver_population, write_silver_facilities

    population_gdf, facility_gdf = run_quality_gates(population_gdf, facility_gdf, config)
    log.info("Validation passed — %d blocks, %d facilities",
             len(population_gdf), len(facility_gdf))

    write_silver_population(population_gdf, config=config)
    write_silver_facilities(facility_gdf, config=config)

    # ── 3. Transform (2SFCA) ──────────────────────────────────────────────
    log.info("--- Stage 3: Transform (Silver → Gold) ---")
    from pipeline.transform.sfca_2 import run_transform
    from pipeline.store.s3_store import write_gold_scores

    result_gdf = run_transform(population_gdf, facility_gdf, config)
    n_zero = (result_gdf["accessibility_score"] == 0).sum()
    log.info(
        "2SFCA complete — mean: %.6f | zero-access blocks: %d (%.1f%%)",
        result_gdf["accessibility_score"].mean(),
        n_zero,
        n_zero / len(result_gdf) * 100,
    )

    # Write Gold to S3 / local medallion store
    gold_path = write_gold_scores(result_gdf, config=config)
    log.info("Gold layer written → %s", gold_path)

    # Flat CSV for quick inspection
    state = config["study_area"]["state_abbrev"].lower()
    ftype = config["facility"]["type"].lower()
    csv_path = Path("outputs/results") / f"{state}_{ftype}_standard.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    result_gdf.drop(columns="geometry").to_csv(csv_path, index=False)
    log.info("CSV written → %s", csv_path)

    # ── PostGIS operational store (optional — requires POSTGIS_DSN) ───────
    if os.environ.get("POSTGIS_DSN"):
        log.info("POSTGIS_DSN detected — writing to PostGIS operational store...")
        from pipeline.store.postgis_store import (
            write_silver_population as pg_write_pop,
            write_silver_facilities as pg_write_fac,
            write_gold_scores       as pg_write_gold,
        )
        pg_write_pop(population_gdf, config=config)
        pg_write_fac(facility_gdf,   config=config)
        pg_write_gold(result_gdf,    config=config)
        log.info("PostGIS write complete")
    else:
        log.info("POSTGIS_DSN not set — skipping PostGIS store (set env var to enable)")

    # ── 4. Analytics (DuckDB) ─────────────────────────────────────────────
    log.info("--- Stage 4: Analytics (DuckDB) ---")
    from pipeline.duckdb_query import build_analytics_db

    con = build_analytics_db(config=config)
    summary = con.execute("SELECT * FROM v_score_summary").fetchdf()
    log.info("Score summary:\n%s", summary.to_string(index=False))
    con.close()

    # ── 5. Visualize ──────────────────────────────────────────────────────
    log.info("--- Stage 5: Visualize ---")
    from pipeline.visualize import run_all_visualizations

    viz_paths = run_all_visualizations(result_gdf, facility_gdf=facility_gdf, config=config)
    for name, path in viz_paths.items():
        log.info("  %-20s → %s", name, path)

    log.info("=== Pipeline complete ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Spatial Accessibility Pipeline")
    parser.add_argument(
        "--config", type=str, default=None,
        help="Path to config YAML (default: config.yaml)",
    )
    args = parser.parse_args()

    try:
        main(config_path=args.config)
    except Exception as exc:
        log.error("Pipeline failed: %s", exc, exc_info=True)
        sys.exit(1)
