"""
pipeline.duckdb_query
----------------------
Loads the Gold-layer GeoParquet into a persistent DuckDB database and
registers analytical views.

Gold file path is derived from config (study area + facility type) so
the same module works for any pipeline run without modification.

Usage
-----
    from pipeline.duckdb_query import build_analytics_db, query

    build_analytics_db()
    df = query("SELECT * FROM accessibility_scores ORDER BY accessibility_score DESC LIMIT 10")
"""

from __future__ import annotations

import logging
import os
from datetime import date
from pathlib import Path

import duckdb

from pipeline.config import load_config
from pipeline.store.s3_store import build_key, _dataset_name   # public helpers

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _get_gold_path(config: dict, run_date: str | None = None) -> str:
    """Return the S3 URI or local path for today's Gold GeoParquet."""
    cfg_s3 = config["s3"]
    run_date = run_date or date.today().isoformat()
    dataset = _dataset_name("scores", config)
    key = build_key(cfg_s3["prefix"], "gold", dataset, run_date)

    bucket = cfg_s3.get("bucket") or os.environ.get("S3_BUCKET")
    if bucket:
        return f"s3://{bucket}/{key}"

    return str(
        _REPO_ROOT / "outputs" / "results"
        / "gold" / f"run_date={run_date}" / f"{dataset}.parquet"
    )


def build_analytics_db(
    config: dict | None = None,
    db_path: str | None = None,
    run_date: str | None = None,
) -> duckdb.DuckDBPyConnection:
    """
    Create or open the DuckDB database and register the Gold accessibility
    scores as a persistent table with analytical views.

    Returns
    -------
    duckdb.DuckDBPyConnection
        Open connection. Caller is responsible for closing it.
    """
    if config is None:
        config = load_config()

    db_path = db_path or config["duckdb"]["db_path"]
    table_name = config["duckdb"]["gold_table"]
    fac_label = config["facility"]["label"]
    area_name = config["study_area"]["name"]

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(db_path)

    for ext in ("spatial", "httpfs"):
        try:
            con.execute(f"INSTALL {ext}; LOAD {ext};")
        except Exception as exc:
            log.warning("DuckDB extension '%s' could not be loaded: %s", ext, exc)

    aws_key = os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret = os.environ.get("AWS_SECRET_ACCESS_KEY")
    aws_region = os.environ.get("AWS_DEFAULT_REGION", config["s3"].get("region", "us-east-1"))
    if aws_key and aws_secret:
        con.execute(f"SET s3_access_key_id='{aws_key}';")
        con.execute(f"SET s3_secret_access_key='{aws_secret}';")
        con.execute(f"SET s3_region='{aws_region}';")

    gold_path = _get_gold_path(config, run_date)
    log.info("Loading Gold GeoParquet from %s into DuckDB", gold_path)

    con.execute(f"""
        CREATE OR REPLACE TABLE {table_name} AS
        SELECT * FROM read_parquet('{gold_path}');
    """)

    # Attach metadata for provenance
    con.execute(f"""
        CREATE OR REPLACE VIEW v_run_metadata AS
        SELECT
            '{area_name}'   AS study_area,
            '{fac_label}'   AS facility_type,
            '{run_date or date.today().isoformat()}' AS run_date;
    """)

    con.execute(f"""
        CREATE OR REPLACE VIEW v_top_accessible AS
        SELECT GEOID, population, accessibility_score, accessibility_norm
        FROM {table_name}
        ORDER BY accessibility_score DESC
        LIMIT 20;
    """)

    con.execute(f"""
        CREATE OR REPLACE VIEW v_zero_access AS
        SELECT GEOID, population, accessibility_score
        FROM {table_name}
        WHERE accessibility_score = 0
        ORDER BY population DESC;
    """)

    con.execute(f"""
        CREATE OR REPLACE VIEW v_score_summary AS
        SELECT
            COUNT(*)                                        AS total_blocks,
            SUM(population)                                 AS total_population,
            AVG(accessibility_score)                        AS mean_score,
            STDDEV(accessibility_score)                     AS std_score,
            MIN(accessibility_score)                        AS min_score,
            MAX(accessibility_score)                        AS max_score,
            PERCENTILE_CONT(0.25) WITHIN GROUP
                (ORDER BY accessibility_score)              AS p25,
            PERCENTILE_CONT(0.50) WITHIN GROUP
                (ORDER BY accessibility_score)              AS median_score,
            PERCENTILE_CONT(0.75) WITHIN GROUP
                (ORDER BY accessibility_score)              AS p75,
            SUM(CASE WHEN accessibility_score = 0
                     THEN population ELSE 0 END) * 1.0
                / NULLIF(SUM(population), 0)                AS pct_pop_no_access
        FROM {table_name};
    """)

    row_count = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    log.info("DuckDB analytics DB ready: table='%s', rows=%d, path=%s",
             table_name, row_count, db_path)
    return con


def query(
    sql: str,
    config: dict | None = None,
    db_path: str | None = None,
) -> list[tuple]:
    """Run ad-hoc SQL against the DuckDB analytics database."""
    if config is None:
        config = load_config()
    db_path = db_path or config["duckdb"]["db_path"]
    con = duckdb.connect(db_path, read_only=False)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()
