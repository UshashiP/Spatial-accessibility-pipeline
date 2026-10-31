"""
Build the official 2020 Census block population reference for DC.

The DC scoring input ("Bl_totalpo") equals the official 2020 block count except
that the 1,512 zero-population blocks were set to the median (62), which makes
the block total 783,289 instead of the official 689,545. The dashboard shows the
official counts for residents; the published scores are not recomputed.

Source: Census Bureau 2020 Redistricting Data (P.L. 94-171), table P1 (total
population), summary level 750 (census block). No API key is needed.

Run from the repository root:
    python scripts/data_preparation/official_block_population.py

Writes case_studies/reference/dc_block_population_2020.csv (GEOID, population_2020),
the population_reference used by case_studies/dc.yaml.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd
import requests

REPO = Path(__file__).resolve().parents[2]
URL = (
    "https://www2.census.gov/programs-surveys/decennial/2020/data/"
    "01-Redistricting_File--PL_94-171/District_of_Columbia/dc2020.pl.zip"
)
OUTPUT = REPO / "case_studies" / "reference" / "dc_block_population_2020.csv"
BLOCK_SUMLEV = "750"
EXPECTED_BLOCKS = 6012


def main() -> None:
    response = requests.get(URL, timeout=180)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        # Geographic header: SUMLEV, LOGRECNO and GEOID are pipe-delimited columns 3, 8 and 9.
        geo = pd.read_csv(archive.open("dcgeo2020.pl"), sep="|", header=None, dtype=str,
                          encoding="latin-1", usecols=[2, 7, 8], names=["sumlev", "logrecno", "geoid"])
        # Segment 1: LOGRECNO and P0010001 (total population) are columns 5 and 6.
        totals = pd.read_csv(archive.open("dc000012020.pl"), sep="|", header=None, dtype=str,
                             encoding="latin-1", usecols=[4, 5], names=["logrecno", "population_2020"])

    blocks = geo[geo["sumlev"] == BLOCK_SUMLEV].merge(totals, on="logrecno", validate="one_to_one")
    blocks["GEOID"] = blocks["geoid"].str.split("US").str[1]
    blocks["population_2020"] = blocks["population_2020"].astype(int)
    blocks = blocks[["GEOID", "population_2020"]].sort_values("GEOID")

    if len(blocks) != EXPECTED_BLOCKS or not blocks["GEOID"].str.len().eq(15).all():
        raise ValueError(f"Unexpected block table: {len(blocks)} rows")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    blocks.to_csv(OUTPUT, index=False)
    print(f"Wrote {OUTPUT.relative_to(REPO)}: {len(blocks):,} blocks, "
          f"{blocks['population_2020'].sum():,} residents, "
          f"{(blocks['population_2020'] == 0).sum():,} empty blocks")


if __name__ == "__main__":
    main()
