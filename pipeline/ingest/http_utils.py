"""
pipeline.ingest.http_utils
---------------------------
Shared HTTP helpers for the ingest stage.
"""

from __future__ import annotations

import requests
from tenacity import retry, stop_after_attempt, wait_exponential


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)
def get_with_retry(url: str, params: dict, timeout: int = 60) -> requests.Response:
    """GET request with automatic exponential-backoff retry."""
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp
