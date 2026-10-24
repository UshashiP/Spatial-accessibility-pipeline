import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

from dashboard.official_population import apply_official_population, reference_path


@pytest.fixture
def blocks():
    return gpd.GeoDataFrame(
        {"GEOID": ["110010001011000", "110010001011001", "110010001011002"],
         "population": [62, 282, 62], "accessibility_score": [4.0, 0.0, 9.0]},
        geometry=[Point(0, 0)] * 3, crs="EPSG:26985",
    )


def write_reference(directory, rows):
    pd.DataFrame(rows, columns=["GEOID", "population_2020"]).to_csv(
        reference_path("dc_icf", directory), index=False
    )


def test_official_counts_replace_population_and_keep_model_input(blocks, tmp_path):
    write_reference(tmp_path, [("110010001011000", 0), ("110010001011001", 282), ("110010001011002", 7)])
    result = apply_official_population(blocks, "dc_icf", tmp_path)
    assert result["population"].tolist() == [0, 282, 7]
    assert result["population_model_input"].tolist() == [62, 282, 62]
    assert result["accessibility_score"].tolist() == [4.0, 0.0, 9.0]
    assert isinstance(result, gpd.GeoDataFrame) and result.crs == blocks.crs
    assert "population_2020" not in result and list(blocks["population"]) == [62, 282, 62]


def test_studies_without_a_reference_file_are_unchanged(blocks, tmp_path):
    result = apply_official_population(blocks, "ny_dialysis", tmp_path)
    assert result is blocks


def test_reference_that_misses_blocks_is_rejected(blocks, tmp_path):
    write_reference(tmp_path, [("110010001011000", 0), ("110010001011001", 282)])
    with pytest.raises(ValueError, match="does not cover every census block"):
        apply_official_population(blocks, "dc_icf", tmp_path)


def test_committed_dc_reference_matches_official_total():
    official = pd.read_csv(reference_path("dc_icf"), dtype={"GEOID": str})
    assert len(official) == 6012 and official["GEOID"].is_unique
    assert official["population_2020"].sum() == 689545
    assert (official["population_2020"] == 0).sum() == 1512
