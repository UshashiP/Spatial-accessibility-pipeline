"""
How SDW-2SFCA results change with the catchment radius d0.

Reruns each study's SDW-2SFCA on its pipeline inputs at several radii (nothing is
written to the medallion store) and reports, over blocks with residents, the
Gini, the share of blocks with zero access and the share of residents in them.
The study's configured radius is marked with *.

Run from the repository root:
    python scripts/comparison_analysis/catchment_sensitivity.py
    python scripts/comparison_analysis/catchment_sensitivity.py --radii 900 1200 1600 3200 5000

Writes outputs/results/catchment_sensitivity.csv
"""

from __future__ import annotations

import argparse
import copy
import logging
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from pipeline.config import load_config  # noqa: E402
from pipeline.ingest.census_api import ingest_census_blocks  # noqa: E402
from pipeline.ingest.cms_api import ingest_facilities  # noqa: E402
from pipeline.transform.sfca_enhanced import run_enhanced_transform  # noqa: E402
from pipeline.validate.quality_gates import run_quality_gates  # noqa: E402
from pipeline.visualize import _gini  # noqa: E402

STUDIES = ["dc.yaml", "nyc.yaml", "la_fqhc.yaml"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--radii", type=int, nargs="+", default=[900, 1200, 1600])
    args = parser.parse_args()
    logging.disable(logging.INFO)

    rows = []
    for config_file in STUDIES:
        config = load_config(REPO / "case_studies" / config_file)
        blocks, facilities = run_quality_gates(ingest_census_blocks(config), ingest_facilities(config), config)
        configured = config["analysis"]["distance_threshold_m"]
        for radius in args.radii:
            run_config = copy.deepcopy(config)
            run_config["analysis"]["distance_threshold_m"] = radius
            result = run_enhanced_transform(blocks, facilities, run_config)
            reported = result["in_report_area"] if "in_report_area" in result else True
            populated = result[(result["population"] > 0) & reported]
            score = populated["accessibility_score"].to_numpy()
            zero = score == 0
            rows.append({
                "study": config["study_area"]["name"],
                "radius_m": radius,
                "configured": radius == configured,
                "gini": round(_gini(score), 4),
                "zero_access_blocks_pct": round(zero.mean() * 100, 1),
                "zero_access_residents_pct": round(populated.loc[zero, "population"].sum()
                                                   / populated["population"].sum() * 100, 1),
            })
            r = rows[-1]
            print(f"{r['study']:14s} {radius:6,d} m{' *' if r['configured'] else '  '}  Gini {r['gini']:.4f}  "
                  f"zero-access blocks {r['zero_access_blocks_pct']:5.1f}%  residents {r['zero_access_residents_pct']:5.1f}%",
                  flush=True)

    out = REPO / "outputs" / "results" / "catchment_sensitivity.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"saved {out.relative_to(REPO)}")


if __name__ == "__main__":
    main()
