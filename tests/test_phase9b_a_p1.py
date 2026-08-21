"""フェーズ⑨B-A: P1 料金・プラン選択修正の検証。"""

from __future__ import annotations

import pytest

from services.calculator import (
    calculate_carrier_price,
    calculate_multi_carrier_lines,
    compare_all_carriers_for_lines,
    resolve_selected_plan,
)
from tests.test_calculator import build_profile


def _au_line(**kwargs):
    payload = {"carrier": "au", "data_usage": "3"}
    payload.update(kwargs)
    return payload


def _rakuten_line(**kwargs):
    payload = {"carrier": "rakuten", "data_usage": "3"}
    payload.update(kwargs)
    return payload


# --- au 自動プラン選択 ---


def test_au_p1_1_age_17_3gb_selects_u18_plan():
    result = calculate_carrier_price("au", "3", [], build_profile(age="17"))
    assert result["plan"]["id"] == "u18_value_3gb"
    assert result["base_price"] == 2398
    assert result["billing_total"] == 2398


def test_au_p1_2_age_17_10gb_selects_u18_20gb_plan():
    result = calculate_carrier_price("au", "10", [], build_profile(age="17"))
    assert result["plan"]["id"] == "u18_value_20gb"
    assert result["billing_total"] == 4048


def test_au_p1_3_age_17_21gb_uses_regular_plan():
    result = calculate_carrier_price("au", "21", [], build_profile(age="17"))
    assert result["plan"]["id"] not in {"u18_value_3gb", "u18_value_20gb", "u12_value"}
    assert result["plan"]["data_gb_max"] is None  # 無制限系へ


def test_au_p1_4_age_18_boundary_still_u18():
    result = calculate_carrier_price("au", "3", [], build_profile(age="18"))
    assert result["plan"]["id"] == "u18_value_3gb"


def test_au_p1_4_age_19_outside_u18():
    result = calculate_carrier_price("au", "3", [], build_profile(age="19"))
    assert result["plan"]["id"] == "smart_mini_plus_3gb"
    assert result["billing_total"] == 6578


def test_au_p1_5_age_12_u12_for_1gb():
    result = calculate_carrier_price("au", "1", [], build_profile(age="12"))
    assert result["plan"]["id"] == "u12_value"
    assert result["billing_total"] == 1870


def test_au_p1_5_age_11_u12():
    result = calculate_carrier_price("au", "1", [], build_profile(age="11"))
    assert result["plan"]["id"] == "u12_value"


def test_au_p1_6_age_65_senior_for_5gb():
    """シニアは5GBプラン。3GB利用時はより小容量のミニ+が選ばれる（既存 min-capacity 思想）。"""
    result = calculate_carrier_price("au", "5", [], build_profile(age="65"))
    assert result["plan"]["id"] == "senior_value"
    assert result["billing_total"] == 4048


def test_au_p1_6_age_65_3gb_uses_senior_billing_cheapest():
    result = calculate_carrier_price("au", "3", [], build_profile(age="65"))
    assert result["plan"]["id"] == "senior_value"
    assert result["billing_total"] == 4048
    result = calculate_carrier_price("au", "3", [], build_profile(age="59"))
    assert result["plan"]["id"] == "smart_mini_plus_3gb"


def test_au_p1_7_age_23_3gb_regression():
    result = calculate_carrier_price("au", "3", [], build_profile(age="23"))
    assert result["plan"]["id"] == "smart_mini_plus_3gb"
    assert result["billing_total"] == 6578


def test_au_compare_matches_calculate_age_17_3gb():
    line = _au_line(age="17", data_usage="3")
    calc = calculate_multi_carrier_lines([line])["lines"][0]
    compare = next(
        item
        for item in compare_all_carriers_for_lines([line])["comparisons"]
        if item["carrier_id"] == "au"
    )
    assert calc["plan"]["id"] == compare["lines"][0]["plan_id"] == "u18_value_3gb"
    assert calc["billing_total"] == compare["billing_total"] == 2398


def test_au_manual_plan_not_overridden():
    result = calculate_carrier_price(
        "au",
        "3",
        [],
        build_profile(age="23"),
        plan_id="unlimited_max_plus",
    )
    assert result["plan_manual"] is True
    assert result["plan"]["id"] == "unlimited_max_plus"


# --- Rakuten 年齢割（エントリー必須 → 自動適用しない） ---


def test_rakuten_no_auto_child_discount_on_calculate():
    result = calculate_carrier_price("rakuten", "3", [], build_profile(age="12"))
    assert result["billing_total"] == 1078
    assert "child_discount" not in [d["id"] for d in result["applied_discounts"]]


def test_rakuten_no_auto_child_discount_on_compare_same_carrier():
    line = _rakuten_line(age="12")
    compare = next(
        item
        for item in compare_all_carriers_for_lines([line])["comparisons"]
        if item["carrier_id"] == "rakuten"
    )
    assert compare["billing_total"] == 1078


def test_rakuten_no_auto_child_discount_on_compare_cross_carrier():
    line = {"carrier": "softbank", "age": "12", "data_usage": "3"}
    compare = next(
        item
        for item in compare_all_carriers_for_lines([line])["comparisons"]
        if item["carrier_id"] == "rakuten"
    )
    assert compare["billing_total"] == 1078


def test_rakuten_calculate_compare_consistent_age_12():
    line = _rakuten_line(age="12")
    calc = calculate_multi_carrier_lines([line])["lines"][0]
    compare = next(
        item
        for item in compare_all_carriers_for_lines([line])["comparisons"]
        if item["carrier_id"] == "rakuten"
    )
    for key in (
        "billing_total",
        "reward_total",
        "effective_total",
        "value_adjusted_total",
    ):
        assert calc[key] == compare[key]


def test_rakuten_manual_child_discount_still_works():
    result = calculate_carrier_price(
        "rakuten",
        "2",
        ["child_discount"],
        build_profile(age="10"),
    )
    assert result["billing_total"] == 968


def test_rakuten_family_discount_with_age_12():
    result = calculate_multi_carrier_lines(
        [
            _rakuten_line(age="12"),
            _rakuten_line(age="40", discounts=["family_discount"]),
        ]
    )
    rakuten_lines = [line for line in result["lines"] if line["carrier_id"] == "rakuten"]
    assert len(rakuten_lines) == 2
    assert sum(line["billing_total"] for line in rakuten_lines) == 1078 + (1078 - 110)


def test_rakuten_usage_points_unchanged_after_fix():
    result = calculate_carrier_price("rakuten", "3", [], build_profile(age="12"))
    assert result["reward_total"] == 9
    assert result["effective_total"] == 1069
