"""
pipeline.config
---------------
Loads config.yaml and merges environment-variable overrides.
All pipeline modules import settings from here.

Key design principle: no module should hardcode study area, facility type,
or supply column names. All such values are read from config so the pipeline
is portable to any CMS facility type or US metro area.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _REPO_ROOT / "config.yaml"


@lru_cache(maxsize=1)
def load_config(path: str | Path = _CONFIG_PATH) -> dict[str, Any]:
    """Return merged config (YAML file + env-var overrides)."""
    with open(path) as fh:
        cfg: dict[str, Any] = yaml.safe_load(fh)

    # Secrets are never stored in YAML; they live in env vars or .env files.
    _env_overrides = {
        ("census", "api_key"): os.environ.get("CENSUS_API_KEY"),
        ("cms", "api_key"):    os.environ.get("CMS_API_KEY"),
        ("s3", "bucket"):      os.environ.get("S3_BUCKET"),
        ("s3", "region"):      os.environ.get("AWS_DEFAULT_REGION"),
    }
    for (section, key), value in _env_overrides.items():
        if value:
            cfg.setdefault(section, {})[key] = value

    return cfg


def get(section: str, key: str, default: Any = None) -> Any:
    """Convenience accessor: ``get("facility", "type")``."""
    return load_config().get(section, {}).get(key, default)


def facility_type(config: dict | None = None) -> str:
    """Return the short facility type label, e.g. 'ICF'."""
    if config is None:
        config = load_config()
    return config["facility"]["type"]


def supply_column(config: dict | None = None) -> str:
    """
    Return the normalised supply column name used throughout the pipeline.
    Raw CMS data uses the original column name; after ingest it is
    normalised to 'supply' so downstream modules stay facility-agnostic.
    """
    return "supply"
