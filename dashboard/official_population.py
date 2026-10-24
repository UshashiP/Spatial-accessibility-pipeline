"""Official census block counts for display, applied when a reference file exists."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

REFERENCE_DIR = Path(__file__).resolve().parent / "reference"


def reference_path(prefix: str, directory: Path = REFERENCE_DIR) -> Path:
    return directory / f"{prefix}_block_population_2020.csv"


def apply_official_population(blocks: pd.DataFrame, prefix: str, directory: Path = REFERENCE_DIR):
    """Show official block counts as ``population`` and keep the model input.

    The scores are not recomputed: the value used by the model moves to
    ``population_model_input`` so exports stay transparent. Returns the blocks
    unchanged when the study has no reference file.
    """
    path = reference_path(prefix, directory)
    if blocks.empty or not path.exists():
        return blocks
    official = pd.read_csv(path, dtype={"GEOID": str})
    merged = blocks.merge(official, on="GEOID", how="left", validate="one_to_one")
    if merged["population_2020"].isna().any():
        raise ValueError(
            f"{path.name} does not cover every census block "
            f"({int(merged['population_2020'].isna().sum())} missing)."
        )
    merged["population_model_input"] = merged["population"]
    merged["population"] = merged["population_2020"].astype(int)
    return merged.drop(columns="population_2020")
