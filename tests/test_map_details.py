import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point, box

from dashboard.map_details import build_block_details, build_color_scale, populated_mask, search_blocks


@pytest.fixture
def blocks():
    return gpd.GeoDataFrame(
        {"GEOID": ["060370000001001", "060370000001002"],
         "accessibility_score": [0.0012, 0.0], "population": [100, 200]},
        geometry=[box(-10, -10, 10, 10), box(1990, -10, 2010, 10)],
        crs="EPSG:32611", index=[8, 3],
    )


@pytest.fixture
def facilities():
    return gpd.GeoDataFrame(geometry=[Point(0, 0), Point(300, 400)], crs="EPSG:32611")


def test_counts_include_boundary_and_use_centroids(blocks, facilities):
    result = build_block_details(blocks, facilities, "EPSG:32611", 500)
    assert result["nearby_facilities"].tolist() == [2, 0]
    np.testing.assert_allclose(result["nearest_facility_m"], [0, np.hypot(1700, 400)])
    assert result.index.tolist() == [8, 3]
    assert result["GEOID"].tolist() == blocks["GEOID"].tolist()
    pd.testing.assert_series_equal(result["accessibility_score"], blocks["accessibility_score"])
    assert "nearby_facilities" not in blocks


def test_reprojects_both_inputs(blocks, facilities):
    expected = build_block_details(blocks, facilities, "EPSG:32611", 501)
    actual = build_block_details(
        blocks.to_crs(4326), facilities.to_crs(4326), "EPSG:32611", 501
    )
    assert actual["nearby_facilities"].tolist() == expected["nearby_facilities"].tolist()
    np.testing.assert_allclose(actual["nearest_facility_m"], expected["nearest_facility_m"], atol=0.01)


def test_missing_facilities_are_unavailable_not_zero(blocks, facilities):
    result = build_block_details(blocks, facilities.iloc[:0], "EPSG:32611", 500)
    assert result["nearby_facilities"].isna().all()
    assert result["nearest_facility_m"].isna().all()


@pytest.mark.parametrize("radius", [0, -1, np.nan, np.inf])
def test_invalid_radius_is_rejected(blocks, facilities, radius):
    with pytest.raises(ValueError, match="Catchment radius"):
        build_block_details(blocks, facilities, "EPSG:32611", radius)


@pytest.mark.parametrize("crs", ["EPSG:4326", "EPSG:2263"])
def test_non_metric_crs_is_rejected(blocks, facilities, crs):
    with pytest.raises(ValueError, match="projected CRS in metres"):
        build_block_details(blocks, facilities, crs, 500)


def test_missing_geoid_is_rejected(blocks, facilities):
    with pytest.raises(ValueError, match="GEOID"):
        build_block_details(blocks.drop(columns="GEOID"), facilities, "EPSG:32611", 500)


def test_empty_geometry_is_rejected(blocks, facilities):
    blocks.loc[8, "geometry"] = Point()
    with pytest.raises(ValueError, match="non-empty geometries"):
        build_block_details(blocks, facilities, "EPSG:32611", 500)


def test_percentile_scale_resists_extreme_outlier_without_changing_scores():
    scores = np.concatenate([np.arange(100, dtype=float), [363364.71]])
    original = scores.copy()
    scale = build_color_scale(scores)
    assert scale.upper == pytest.approx(np.percentile(scores, 95))
    assert scale.upper == 95
    assert scale.capped
    assert scale.labels[-1] == "95+"
    np.testing.assert_array_equal(scale.values, original)
    np.testing.assert_array_equal(scores, original)
    assert scores[50] / scale.upper > 0.5


def test_logarithmic_scale_includes_zero_and_has_raw_score_labels():
    scores = np.array([0, 0.01, 5, 100, 363364.71])
    original = scores.copy()
    scale = build_color_scale(scores, logarithmic=True)
    np.testing.assert_allclose(scale.values, np.log1p(scores))
    np.testing.assert_array_equal(scores, original)
    assert scale.values[0] == 0
    assert np.diff(scale.values).min() > 0
    assert scale.upper == pytest.approx(np.log1p(scores.max()))
    assert scale.labels[0] == "0"
    np.testing.assert_allclose(
        [float(label.replace(",", "")) for label in scale.labels],
        np.expm1(scale.ticks), rtol=0.0001,
    )
    assert not scale.capped


@pytest.mark.parametrize("logarithmic", [False, True])
@pytest.mark.parametrize("scores", [[0, 0], [5, 5], [0.001, 0.001]])
def test_zero_and_constant_scales_are_valid(scores, logarithmic):
    scale = build_color_scale(np.array(scores), logarithmic)
    assert scale.upper > 0
    assert np.isfinite(scale.values).all()
    assert len(scale.ticks) == len(scale.labels)
    assert all(0 <= tick <= scale.upper for tick in scale.ticks)


def test_zero_percentile_falls_back_to_full_range():
    scale = build_color_scale(np.array([0] * 100 + [10]))
    assert scale.upper == 10
    assert not scale.capped
    assert not scale.labels[-1].endswith("+")


@pytest.mark.parametrize("scores", [[], [-1, 2], [np.nan], [np.inf]])
def test_invalid_map_scores_are_rejected(scores):
    with pytest.raises(ValueError, match="Map scores"):
        build_color_scale(np.array(scores))


GEOIDS = pd.Series(["110010030001001", "110010030001002", "110010030002000", "110010002024005"])


def test_search_exact_geoid_ignores_separators():
    assert search_blocks(GEOIDS, " 11001-003000 1001 ") == ["110010030001001"]


def test_search_prefix_lists_sorted_blocks_with_limit():
    assert search_blocks(GEOIDS, "11001003000") == [
        "110010030001001", "110010030001002", "110010030002000"]
    assert search_blocks(GEOIDS, "11001003000", limit=2) == [
        "110010030001001", "110010030001002"]


def test_search_no_match_or_no_digits():
    assert search_blocks(GEOIDS, "99999") == []
    assert search_blocks(GEOIDS, "Columbia Heights") == []


def test_block_zoom_scales_with_block_size_and_is_clamped():
    from dashboard.map_details import block_zoom

    city_block = block_zoom((-77.032, 38.929, -77.030, 38.931))
    assert 15 < city_block < 16
    assert block_zoom((-77.0320, 38.9290, -77.0316, 38.9294)) > city_block
    assert block_zoom((-119.0, 34.0, -118.0, 35.0)) == 12.0
    assert block_zoom((-77.0, 38.9, -77.0, 38.9)) == 16.5


def test_populated_mask_marks_blocks_with_residents():
    blocks = pd.DataFrame({"population": [0, 5, 0, 3]})
    assert populated_mask(blocks).tolist() == [False, True, False, True]


def test_classify_bivariate_tiers_and_left_behind():
    from dashboard.map_details import ISOLATED, classify_bivariate
    # Six 1-km² blocks plus one empty block; density rises with population.
    blocks = gpd.GeoDataFrame(
        {"GEOID": [str(i) for i in range(7)],
         "population": [10, 20, 30, 400, 500, 600, 0],
         "accessibility_score": [0.0, 0.0, 5.0, 2.0, 9.0, 0.0, 0.0]},
        geometry=[box(i * 2000, 0, i * 2000 + 1000, 1000) for i in range(7)],
        crs="EPSG:32618",
    )
    result = classify_bivariate(blocks, "EPSG:32618")
    assert len(result) == 6  # the empty block is left out
    np.testing.assert_allclose(result["density"], [10, 20, 30, 400, 500, 600])
    # Tiers are population-weighted: the sparse blocks hold few residents, so they
    # share the low tier and the densest block alone is high.
    assert result.loc[[0, 1, 2], "density_tier"].eq("low").all()
    assert result.loc[5, "density_tier"] == "high"
    # Over a third of residents have no access, so the low access tier is the zero scores.
    assert (result["access_tier"] == "low").tolist() == (blocks["accessibility_score"][:6] == 0).tolist()
    assert result.loc[5, "bivariate_class"] == ISOLATED


def test_populated_mask_respects_report_area():
    blocks = pd.DataFrame({"population": [5, 5, 0], "in_report_area": [True, False, True]})
    assert populated_mask(blocks).tolist() == [True, False, False]
