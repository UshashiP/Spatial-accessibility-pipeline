"""
Sensitivity of SDW-2SFCA to the socio-economic weighting scheme.

The published method weights population, income, insurance and age equally:
    w = P + I + HI + Ag
This reruns each study with seven alternatives — dropping each socio-economic
variable, then doubling each — and compares them with equal weighting over
blocks with residents:

    Gini            inequality of scores
    rank corr.      Spearman correlation of block scores with equal weighting
    diluted overlap share of the equal-weighting "diluted" left-behind blocks
                    (dense, facility nearby, supply stretched) that the scheme
                    also flags (Jaccard index)

Zero access, and so the "isolated" left-behind blocks, do not depend on the
weights: a block scores zero only when no facility is within the catchment.

Run from the repository root:
    python scripts/comparison_analysis/weight_sensitivity.py
Writes outputs/results/weight_sensitivity.csv
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd
from scipy.stats import spearmanr

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from dashboard.map_details import DILUTED, classify_bivariate  # noqa: E402
from pipeline.config import load_config  # noqa: E402
from pipeline.ingest.census_api import ingest_census_blocks  # noqa: E402
from pipeline.ingest.cms_api import ingest_facilities  # noqa: E402
from pipeline.transform.sfca_enhanced import compute_enhanced_2sfca  # noqa: E402
from pipeline.validate.quality_gates import run_quality_gates  # noqa: E402
from pipeline.visualize import _gini  # noqa: E402

STUDIES = ["dc.yaml", "nyc.yaml", "la_fqhc.yaml"]
# label: (population, income, insurance, age)
SCHEMES = {
    "Equal (published)": (1, 1, 1, 1),
    "No income": (1, 0, 1, 1),
    "No insurance": (1, 1, 0, 1),
    "No age": (1, 1, 1, 0),
    "Income x2": (1, 2, 1, 1),
    "Insurance x2": (1, 1, 2, 1),
    "Age x2": (1, 1, 1, 2),
    "Population x2": (2, 1, 1, 1),
}


def main() -> None:
    logging.disable(logging.INFO)
    rows = []
    for config_file in STUDIES:
        config = load_config(REPO / "case_studies" / config_file)
        blocks, facilities = run_quality_gates(ingest_census_blocks(config), ingest_facilities(config), config)
        d0 = float(config["analysis"]["distance_threshold_m"])
        crs = config["study_area"]["coordinate_system"]
        print(f"\n{config['study_area']['name']} (d0 = {d0:,.0f} m)")
        print(f"{'Scheme':20s} {'Gini':>7s} {'Rank corr.':>11s} {'Diluted overlap':>16s}")

        base_scores = base_diluted = None
        for label, weights in SCHEMES.items():
            result = compute_enhanced_2sfca(blocks, facilities, d0=d0, pop_col="population",
                                            supply_col="supply", weights=weights)
            classes = classify_bivariate(result, crs)
            scores = result.loc[classes.index, "accessibility_score"]
            diluted = set(result.loc[classes.index[classes["bivariate_class"] == DILUTED], "GEOID"])
            if base_scores is None:
                base_scores, base_diluted = scores, diluted
            rho = spearmanr(scores, base_scores).statistic
            overlap = len(diluted & base_diluted) / len(diluted | base_diluted) if diluted | base_diluted else 1.0
            rows.append({"study": config["study_area"]["name"], "scheme": label,
                         "gini": round(_gini(scores.to_numpy()), 4), "rank_corr": round(rho, 4),
                         "diluted_overlap": round(overlap, 3)})
            print(f"{label:20s} {rows[-1]['gini']:7.4f} {rho:11.4f} {overlap:16.1%}", flush=True)

    out = REPO / "outputs" / "results" / "weight_sensitivity.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"\nsaved {out.relative_to(REPO)}")


if __name__ == "__main__":
    main()
