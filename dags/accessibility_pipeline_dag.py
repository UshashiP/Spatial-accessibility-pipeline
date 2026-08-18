"""
dags/accessibility_pipeline_dag
--------------------------------
Airflow DAG that orchestrates the Spatial Accessibility Pipeline end-to-end.

DAG ID        : spatial_accessibility_pipeline
Schedule      : @quarterly  (aligns with CMS Provider of Services releases)
Max active    : 1 run at a time
Catchup       : disabled

Task graph
----------

ingest_census ──┐
                ├──▶ validate_silver ──▶ transform_2sfca ──▶ store_gold ──▶ build_analytics
ingest_cms ─────┘

All study area and facility parameters come from config.yaml.
To schedule a different facility type or city, point to a different config.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

log = logging.getLogger(__name__)

default_args = {
    "owner": "accessibility-pipeline",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


# ── Task callables ────────────────────────────────────────────────────────────

def _task_ingest_census(**context) -> dict:
    from pipeline.ingest.census_api import ingest_census_blocks
    from pipeline.store.s3_store import write_bronze_population

    run_date = context["ds"]
    gdf = ingest_census_blocks()
    uri = write_bronze_population(gdf, run_date=run_date)
    return {"uri": uri, "rows": len(gdf)}


def _task_ingest_cms(**context) -> dict:
    from pipeline.ingest.cms_api import ingest_facilities   # facility-agnostic name
    from pipeline.store.s3_store import write_bronze_facilities

    run_date = context["ds"]
    gdf = ingest_facilities()
    uri = write_bronze_facilities(gdf, run_date=run_date)
    return {"uri": uri, "rows": len(gdf)}


def _task_validate_silver(**context) -> dict:
    from pipeline.store.s3_store import read_layer, write_silver_population, write_silver_facilities
    from pipeline.validate.quality_gates import run_quality_gates

    run_date = context["ds"]
    pop_gdf = read_layer("bronze", "population", run_date=run_date)
    fac_gdf = read_layer("bronze", "facilities", run_date=run_date)

    pop_clean, fac_clean = run_quality_gates(pop_gdf, fac_gdf)

    return {
        "pop_uri": write_silver_population(pop_clean, run_date=run_date),
        "pop_rows": len(pop_clean),
        "fac_uri": write_silver_facilities(fac_clean, run_date=run_date),
        "fac_rows": len(fac_clean),
    }


def _task_transform_2sfca(**context) -> dict:
    from pipeline.store.s3_store import read_layer, write_gold_scores
    from pipeline.transform.sfca_2 import run_transform

    run_date = context["ds"]
    pop_gdf = read_layer("silver", "population", run_date=run_date)
    fac_gdf = read_layer("silver", "facilities", run_date=run_date)

    result_gdf = run_transform(pop_gdf, fac_gdf)
    uri = write_gold_scores(result_gdf, run_date=run_date)
    return {"uri": uri, "rows": len(result_gdf), "mean_score": float(result_gdf["accessibility_score"].mean())}


def _task_build_analytics(**context) -> dict:
    from pipeline.duckdb_query import build_analytics_db

    con = build_analytics_db(run_date=context["ds"])
    summary = con.execute("SELECT * FROM v_score_summary").fetchdf().to_dict(orient="records")
    con.close()
    return {"summary": summary}


# ── DAG definition ────────────────────────────────────────────────────────────

with DAG(
    dag_id="spatial_accessibility_pipeline",
    description="Spatial Accessibility ETL — Bronze → Silver → Gold on S3",
    schedule_interval="@quarterly",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["healthcare", "accessibility", "geospatial", "s3", "geoparquet"],
) as dag:

    ingest_census = PythonOperator(task_id="ingest_census", python_callable=_task_ingest_census)
    ingest_cms    = PythonOperator(task_id="ingest_cms",    python_callable=_task_ingest_cms)
    validate      = PythonOperator(task_id="validate_silver", python_callable=_task_validate_silver)
    transform     = PythonOperator(task_id="transform_2sfca", python_callable=_task_transform_2sfca)
    analytics     = PythonOperator(task_id="build_analytics", python_callable=_task_build_analytics)

    [ingest_census, ingest_cms] >> validate >> transform >> analytics
