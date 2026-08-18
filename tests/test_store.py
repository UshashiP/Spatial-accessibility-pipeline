"""
tests/test_store.py
--------------------
Unit tests for pipeline.store.s3_store.

All S3 / boto3 calls are mocked so tests run fully offline.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import geopandas as gpd
import pytest

from pipeline.store.s3_store import (
    build_key,
    _gdf_to_parquet_bytes,
    write_layer,
)


# ── build_key ─────────────────────────────────────────────────────────────────

class TestBuildKey:

    def test_key_structure(self):
        key = build_key("spatial-accessibility", "bronze", "dc_icf_population", "2026-04-09")
        assert key == "spatial-accessibility/bronze/dc_icf_population/run_date=2026-04-09/data.parquet"

    def test_key_gold_layer(self):
        key = build_key("prefix", "gold", "dc_icf_scores", "2026-01-01")
        assert "gold" in key
        assert "dc_icf_scores" in key
        assert key.endswith(".parquet")

    def test_key_contains_run_date_partition(self):
        date_str = "2026-04-09"
        key = build_key("p", "silver", "dc_icf_facilities", date_str)
        assert f"run_date={date_str}" in key


# ── _gdf_to_parquet_bytes ─────────────────────────────────────────────────────

class TestGdfToParquetBytes:

    def test_returns_bytes(self, facility_gdf):
        data = _gdf_to_parquet_bytes(facility_gdf)
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_roundtrip(self, facility_gdf):
        import io
        data = _gdf_to_parquet_bytes(facility_gdf)
        recovered = gpd.read_parquet(io.BytesIO(data))
        assert len(recovered) == len(facility_gdf)
        assert list(recovered.columns) == list(facility_gdf.columns)

    def test_snappy_compression(self, population_gdf):
        data_snappy = _gdf_to_parquet_bytes(population_gdf, compression="snappy")
        data_none = _gdf_to_parquet_bytes(population_gdf, compression=None)
        assert isinstance(data_snappy, bytes)
        assert isinstance(data_none, bytes)


# ── write_layer ───────────────────────────────────────────────────────────────

class TestWriteLayer:

    def test_local_fallback_writes_file(self, population_gdf, pipeline_config, tmp_path, monkeypatch):
        monkeypatch.delenv("S3_BUCKET", raising=False)
        import pipeline.store.s3_store as store_mod
        monkeypatch.setattr(store_mod, "_REPO_ROOT", tmp_path)

        cfg = {**pipeline_config, "s3": {**pipeline_config["s3"]}}
        cfg["s3"].pop("bucket", None)

        result_path = write_layer(
            population_gdf, "bronze", "population",
            run_date="2026-04-09", config=cfg,
        )
        assert Path(result_path).exists()
        assert result_path.endswith(".parquet")

    def test_local_fallback_readable(self, population_gdf, pipeline_config, tmp_path, monkeypatch):
        monkeypatch.delenv("S3_BUCKET", raising=False)
        import pipeline.store.s3_store as store_mod
        monkeypatch.setattr(store_mod, "_REPO_ROOT", tmp_path)

        cfg = {**pipeline_config, "s3": {**pipeline_config["s3"]}}
        cfg["s3"].pop("bucket", None)

        result_path = write_layer(
            population_gdf, "silver", "population",
            run_date="2026-04-09", config=cfg,
        )
        recovered = gpd.read_parquet(result_path)
        assert len(recovered) == len(population_gdf)

    @patch("pipeline.store.s3_store._get_s3_client")
    def test_s3_upload_called_when_bucket_set(
        self, mock_s3_client, population_gdf, pipeline_config, monkeypatch
    ):
        monkeypatch.setenv("S3_BUCKET", "test-bucket")
        mock_client = MagicMock()
        mock_s3_client.return_value = mock_client

        cfg = {**pipeline_config, "s3": {**pipeline_config["s3"]}}
        cfg["s3"].pop("bucket", None)

        result = write_layer(
            population_gdf, "bronze", "population",
            run_date="2026-04-09", config=cfg,
        )

        mock_client.put_object.assert_called_once()
        call_kwargs = mock_client.put_object.call_args.kwargs
        assert call_kwargs["Bucket"] == "test-bucket"
        assert "population" in call_kwargs["Key"]
        assert result.startswith("s3://test-bucket/")

    @patch("pipeline.store.s3_store._get_s3_client")
    def test_s3_key_contains_correct_layer(
        self, mock_s3_client, facility_gdf, pipeline_config, monkeypatch
    ):
        monkeypatch.setenv("S3_BUCKET", "my-bucket")
        mock_client = MagicMock()
        mock_s3_client.return_value = mock_client

        cfg = {**pipeline_config, "s3": {**pipeline_config["s3"]}}
        cfg["s3"].pop("bucket", None)

        write_layer(
            facility_gdf, "gold", "scores",
            run_date="2026-01-15", config=cfg,
        )
        key = mock_client.put_object.call_args.kwargs["Key"]
        assert "gold" in key
        assert "scores" in key
        assert "run_date=2026-01-15" in key

    def test_run_date_defaults_to_today(self, population_gdf, pipeline_config, tmp_path, monkeypatch):
        from datetime import date
        monkeypatch.delenv("S3_BUCKET", raising=False)
        import pipeline.store.s3_store as store_mod
        monkeypatch.setattr(store_mod, "_REPO_ROOT", tmp_path)

        cfg = {**pipeline_config, "s3": {**pipeline_config["s3"]}}
        cfg["s3"].pop("bucket", None)

        result_path = write_layer(population_gdf, "bronze", "population", config=cfg)
        assert date.today().isoformat() in result_path
