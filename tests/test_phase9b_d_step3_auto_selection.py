"""Phase 9B-D: STEP3 (/api/calculate) auto plan selection aligns with billing axis."""

from __future__ import annotations

import pytest

from services.calculator import (
    build_qr_context,
    calculate_carrier_price,
    calculate_multi_carrier_lines,
    compare_all_carriers_for_lines,
)
from tests.test_calculator import build_profile


def _line(**overrides):
    base = {"carrier": "au", "data_usage": "3gb"}
    base.update(overrides)
    return base


def _compare_billing_plan(lines, carrier_id):
    comparison = compare_all_carriers_for_lines(lines)
    entry = next(item for item in comparison["comparisons"] if item["carrier_id"] == carrier_id)
    return entry["axis_quotes"]["billing"]


def _calc_primary(lines):
    return calculate_multi_carrier_lines(lines)["lines"][0]


def _assert_step3_matches_billing_axis(lines, carrier_id):
    calc = calculate_multi_carrier_lines(lines)
    billing = _compare_billing_plan(lines, carrier_id)
    calc_line = next(line for line in calc["lines"] if line["carrier_id"] == carrier_id)
    assert calc_line["plan"]["id"] == billing["plan_id"]
    assert calc_line["billing_total"] == billing["billing_total"]


# --- required cases ---


def test_docomo_3gb_auto_selects_mini():
    result = calculate_carrier_price("docomo", "3", [], build_profile())
    assert result["plan"]["id"] == "docomo_mini"
    assert result["billing_total"] == 2750
    assert result["plan"]["id"] != "docomo_max_3gb"


def test_au_65_3gb_auto_selects_senior_value():
    result = calculate_carrier_price("au", "3", [], build_profile(age="65"))
    assert result["plan"]["id"] == "senior_value"
    assert result["billing_total"] == 4048


def test_au_17_1gb_auto_selects_u18_value_3gb():
    result = calculate_carrier_price("au", "1", [], build_profile(age="17"))
    assert result["plan"]["id"] == "u18_value_3gb"
    assert result["billing_total"] == 2398


def test_au_17_5gb_auto_selects_u18_value_20gb():
    result = calculate_carrier_price("au", "5", [], build_profile(age="17"))
    assert result["plan"]["id"] == "u18_value_20gb"
    assert result["billing_total"] == 4048


def test_uq_10gb_auto_selects_komikomi_value():
    result = calculate_carrier_price("uqmobile", "10", [], build_profile())
    assert result["plan"]["id"] == "komikomi_value"
    assert result["billing_total"] == 3828


def test_softbank_30gb_paypay_divergence_step3_billing_vs_compare_effective():
    result = calculate_carrier_price(
        "softbank",
        "30",
        [],
        build_profile(),
        qr=build_qr_context(qr_paypay="40000", paypay_card_tier="gold", paypay_gold_linked="1"),
    )
    assert result["plan"]["id"] == "teigaku_unlimited"
    assert result["billing_total"] == 8008

    line = {
        "carrier": "softbank",
        "data_usage": "30gb",
        "qr_paypay": "40000",
        "paypay_gold_linked": "1",
    }
    comparison = compare_all_carriers_for_lines([line])
    sb = next(item for item in comparison["comparisons"] if item["carrier_id"] == "softbank")
    assert sb["axis_quotes"]["billing"]["plan_id"] == "teigaku_unlimited"
    assert sb["axis_quotes"]["effective"]["plan_id"] == "paytoku2"
    assert result["plan"]["id"] == sb["axis_quotes"]["billing"]["plan_id"]
    assert result["plan"]["id"] != sb["axis_quotes"]["effective"]["plan_id"]


def test_rakuten_auto_regression():
    result = calculate_carrier_price("rakuten", "3", [], build_profile())
    assert result["plan"]["id"] == "saikyo_3gb"
    assert result["billing_total"] == 1078


def test_ahamo_auto_regression():
    result = calculate_carrier_price("ahamo", "20", [], build_profile())
    billing = _compare_billing_plan([{"carrier": "ahamo", "data_usage": "20gb"}], "ahamo")
    assert result["plan"]["id"] == billing["plan_id"]


def test_manual_plan_not_overridden():
    result = calculate_carrier_price(
        "docomo",
        "3",
        [],
        build_profile(),
        plan_id="docomo_max_3gb",
    )
    assert result["plan_manual"] is True
    assert result["plan"]["id"] == "docomo_max_3gb"
    assert result["billing_total"] == 6798


def test_multi_line_docomo_two_lines_billing_axis_plans():
    lines = [
        {"carrier": "docomo", "data_usage": "3gb"},
        {"carrier": "docomo", "data_usage": "3gb"},
    ]
    calc = calculate_multi_carrier_lines(lines)
    billing = _compare_billing_plan(lines, "docomo")
    assert billing["plan_ids"] == ["docomo_mini", "docomo_mini"]
    assert [line["plan"]["id"] for line in calc["lines"]] == billing["plan_ids"]
    assert sum(line["billing_total"] for line in calc["lines"]) == billing["billing_total"]


def test_multi_line_au_two_senior_lines():
    lines = [
        _line(age="65", data_usage="3gb"),
        _line(age="65", data_usage="5gb"),
    ]
    calc = calculate_multi_carrier_lines(lines)
    billing = _compare_billing_plan(lines, "au")
    assert billing["plan_ids"] == ["senior_value", "senior_value"]
    assert [line["plan"]["id"] for line in calc["lines"]] == billing["plan_ids"]


# --- 7 brands single-line vs billing axis ---


@pytest.mark.parametrize(
    "line,carrier_id",
    [
        ({"carrier": "softbank", "data_usage": "10gb"}, "softbank"),
        ({"carrier": "ymobile", "data_usage": "5gb"}, "ymobile"),
        ({"carrier": "au", "data_usage": "3gb", "age": "30"}, "au"),
        ({"carrier": "uqmobile", "data_usage": "10gb"}, "uqmobile"),
        ({"carrier": "docomo", "data_usage": "3gb"}, "docomo"),
        ({"carrier": "ahamo", "data_usage": "20gb"}, "ahamo"),
        ({"carrier": "rakuten", "data_usage": "3gb"}, "rakuten"),
    ],
)
def test_step3_auto_matches_compare_billing_axis(line, carrier_id):
    _assert_step3_matches_billing_axis([line], carrier_id)
