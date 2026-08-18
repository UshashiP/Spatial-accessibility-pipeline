"""
pipeline.store.s3_store
------------------------
Writes GeoDataFrames to AWS S3 as GeoParquet files following the
Bronze / Silver / Gold medallion architecture.

Dataset names in S3 keys are derived from config (study area + facility
type) so the same code works for any destination without modification.

S3 key layout
-------------
s3://<bucket>/
    spatial-accessibility/
        bronze/
            <state>_<facility_type>_population/run_date=YYYY-MM-DD/data.parquet
            <state>_<facility_type>_facilities/run_date=YYYY-MM-DD/data.parquet
        silver/
            ... (same structure)
        gold/
            <state>_<facility_type>_scores/run_date=YYYY-MM-DD/data.parquet

Local fallback
--------------
If S3_BUCKET env var is not set, files are written to outputs/results/
allowing fully offline development.
"""

from __future__ import annotations

import io
import logging
import os
from datetime import date
from pathlib import Path

import geopandas as gpd

from pipeline.config import load_config

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ── Dataset name helpers ──────────────────────────────────────────────────────

def _dataset_prefix(config: dict) -> str:
    """
    Build a config-derived prefix like 'dc_ICF' used in dataset names.
    This ensures S3 keys are meaningful and unique per study+facility.
    """
    state = config["study_area"]["state_abbrev"].lower()
    ftype = config["facility"]["type"].lower()
    return f"{state}_{ftype}"


def _dataset_name(layer_label: str, config: dict) -> str:
    """E.g. 'dc_icf_population', 'dc_icf_facilities', 'dc_icf_scores'."""
    return f"{_dataset_prefix(config)}_{layer_label}"


# ── S3 helpers ────────────────────────────────────────────────────────────────

def _get_s3_client():
    import boto3
    return boto3.client("s3")


def _gdf_to_parquet_bytes(gdf: gpd.GeoDataFrame, compression: str = "snappy") -> bytes:
    buf = io.BytesIO()
    gdf.to_parquet(buf, compression=compression, index=False)
    return buf.getvalue()


def _upload_to_s3(data: bytes, bucket: str, key: str) -> None:
    client = _get_s3_client()
    client.put_object(Body=data, Bucket=bucket, Key=key, ContentType="application/octet-stream")
    log.info("Uploaded s3://%s/%s  (%d bytes)", bucket, key, len(data))


# ── Key construction ──────────────────────────────────────────────────────────

def build_key(prefix: str, layer: str, dataset: str, run_date: str) -> str:
    return f"{prefix}/{layer}/{dataset}/run_date={run_date}/data.parquet"


# ── Core writer ───────────────────────────────────────────────────────────────

def write_layer(
    gdf: gpd.GeoDataFrame,
    layer: str,
    dataset_label: str,
    run_date: str | None = None,
    config: dict | None = None,
) -> str:
    """
    Write a GeoDataFrame to the appropriate medallion layer (S3 or local).

    Parameters
    ----------
    gdf : GeoDataFrame
    layer : str
        'bronze', 'silver', or 'gold'
    dataset_label : str
        Logical label: 'population', 'facilities', or 'scores'.
        Combined with study area + facility type from config to form the
        full dataset name (e.g. 'dc_icf_population').
    run_date : str, optional
        Partition date YYYY-MM-DD. Defaults to today.
    config : dict, optional

    Returns
    -------
    str
        S3 URI or local path written.
    """
    if config is None:
        config = load_config()

    cfg_s3 = config["s3"]
    compression = cfg_s3.get("geoparquet_compression", "snappy")
    prefix = cfg_s3["prefix"]
    run_date = run_date or date.today().isoformat()
    dataset = _dataset_name(dataset_label, config)
    key = build_key(prefix, layer, dataset, run_date)

    bucket = cfg_s3.get("bucket") or os.environ.get("S3_BUCKET")

    if bucket:
        data = _gdf_to_parquet_bytes(gdf, compression)
        _upload_to_s3(data, bucket, key)
        return f"s3://{bucket}/{key}"
    else:
        local_path = (
            _REPO_ROOT / "outputs" / "results"
            / layer / f"run_date={run_date}" / f"{dataset}.parquet"
        )
        local_path.parent.mkdir(parents=True, exist_ok=True)
        gdf.to_parquet(local_path, compression=compression, index=False)
        log.info("Written locally: %s  (%d rows)", local_path, len(gdf))
        return str(local_path)


# ── Convenience writers ───────────────────────────────────────────────────────

def write_bronze_population(gdf, run_date=None, config=None) -> str:
    return write_layer(gdf, "bronze", "population", run_date, config)

def write_bronze_facilities(gdf, run_date=None, config=None) -> str:
    return write_layer(gdf, "bronze", "facilities", run_date, config)

def write_silver_population(gdf, run_date=None, config=None) -> str:
    return write_layer(gdf, "silver", "population", run_date, config)

def write_silver_facilities(gdf, run_date=None, config=None) -> str:
    return write_layer(gdf, "silver", "facilities", run_date, config)

def write_gold_scores(gdf, run_date=None, config=None) -> str:
    return write_layer(gdf, "gold", "scores", run_date, config)


# ── Reader ────────────────────────────────────────────────────────────────────

def read_layer(
    layer: str,
    dataset_label: str,
    run_date: str | None = None,
    config: dict | None = None,
) -> gpd.GeoDataFrame:
    """Read a GeoParquet file from S3 or local fallback."""
    if config is None:
        config = load_config()

    cfg_s3 = config["s3"]
    prefix = cfg_s3["prefix"]
    run_date = run_date or date.today().isoformat()
    dataset = _dataset_name(dataset_label, config)
    key = build_key(prefix, layer, dataset, run_date)

    bucket = cfg_s3.get("bucket") or os.environ.get("S3_BUCKET")

    if bucket:
        client = _get_s3_client()
        obj = client.get_object(Bucket=bucket, Key=key)
        buf = io.BytesIO(obj["Body"].read())
        gdf = gpd.read_parquet(buf)
        log.info("Read s3://%s/%s  (%d rows)", bucket, key, len(gdf))
    else:
        local_path = (
            _REPO_ROOT / "outputs" / "results"
            / layer / f"run_date={run_date}" / f"{dataset}.parquet"
        )
        gdf = gpd.read_parquet(local_path)
        log.info("Read locally: %s  (%d rows)", local_path, len(gdf))

    return gdf
