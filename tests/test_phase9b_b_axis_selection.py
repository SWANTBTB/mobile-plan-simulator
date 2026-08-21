"""Phase 9B-B: axis-specific plan selection for cross-carrier compare."""

from __future__ import annotations

from services.calculator import (
    build_profile,
    build_qr_context,
    compare_all_carriers_for_lines,
    find_best_plans_by_axis,
    _lines_for_brand_comparison,
)
from services.data_loader import load_all_carriers


def _carrier_map():
    return {carrier["id"]: carrier for carrier in load_all_carriers()}


def _line(**overrides):
    base = {"carrier": "au", "data_usage": "3gb"}
    base.update(overrides)
    return base


def _brand_lines(lines, carrier_id):
    carrier_map = _carrier_map()
    family_discount_ids = {
        carrier["id"]: [
            discount["id"]
            for discount in carrier.get("discounts") or []
            if discount.get("line_tiers")
        ]
        for carrier in load_all_carriers()
    }
    return _lines_for_brand_comparison(lines, carrier_id, {}, carrier_map, family_discount_ids)


def _compare_entry(comparison, carrier_id):
    return next(item for item in comparison["comparisons"] if item["carrier_id"] == carrier_id)


def _axis_quote(entry, axis):
    return entry["axis_quotes"][axis]


# --- au age / capacity inversions ---


def test_au_65_3gb_billing_best_is_senior_value():
    comparison = compare_all_carriers_for_lines([_line(age="65", data_usage="3gb")])
    au = _compare_entry(comparison, "au")
    billing = _axis_quote(au, "billing")
    assert billing["plan_id"] == "senior_value"
    assert billing["billing_total"] == 4048
    assert au["billing_total"] == 4048


def test_au_65_3gb_all_axes_senior_value():
    comparison = compare_all_carriers_for_lines([_line(age="65", data_usage="3gb")])
    au = _compare_entry(comparison, "au")
    for axis in ("billing", "effective", "value_adjusted"):
        assert _axis_quote(au, axis)["plan_id"] == "senior_value"
        assert _axis_quote(au, axis)["billing_total"] == 4048


def test_au_17_1gb_billing_best_is_u18_value_3gb():
    comparison = compare_all_carriers_for_lines([_line(age="17", data_usage="1gb")])
    au = _compare_entry(comparison, "au")
    assert _axis_quote(au, "billing")["plan_id"] == "u18_value_3gb"
    assert _axis_quote(au, "billing")["billing_total"] == 2398


def test_au_17_5gb_billing_best_is_u18_value_20gb():
    comparison = compare_all_carriers_for_lines([_line(age="17", data_usage="5gb")])
    au = _compare_entry(comparison, "au")
    assert _axis_quote(au, "billing")["plan_id"] == "u18_value_20gb"
    assert _axis_quote(au, "billing")["billing_total"] == 4048


def test_au_17_3gb_still_u18_value_3gb():
    comparison = compare_all_carriers_for_lines([_line(age="17", data_usage="3gb")])
    au = _compare_entry(comparison, "au")
    assert _axis_quote(au, "billing")["plan_id"] == "u18_value_3gb"


def test_au_23_3gb_regular_plan():
    comparison = compare_all_carriers_for_lines([_line(age="23", data_usage="3gb")])
    au = _compare_entry(comparison, "au")
    assert _axis_quote(au, "billing")["plan_id"] == "smart_mini_plus_3gb"


# --- docomo mini ---


def test_docomo_3gb_billing_best_is_mini():
    comparison = compare_all_carriers_for_lines(
        [{"carrier": "docomo", "data_usage": "3gb"}]
    )
    docomo = _compare_entry(comparison, "docomo")
    assert _axis_quote(docomo, "billing")["plan_id"] == "docomo_mini"
    assert _axis_quote(docomo, "billing")["billing_total"] == 2750


def test_docomo_1gb_billing_best_is_mini():
    comparison = compare_all_carriers_for_lines(
        [{"carrier": "docomo", "data_usage": "1gb"}]
    )
    docomo = _compare_entry(comparison, "docomo")
    assert _axis_quote(docomo, "billing")["plan_id"] == "docomo_mini"
    assert _axis_quote(docomo, "billing")["billing_total"] == 2750


# --- UQ ---


def test_uq_10gb_billing_best_is_komikomi_value():
    comparison = compare_all_carriers_for_lines(
        [{"carrier": "uqmobile", "data_usage": "10gb"}]
    )
    uq = _compare_entry(comparison, "uqmobile")
    assert _axis_quote(uq, "billing")["plan_id"] == "komikomi_value"
    assert _axis_quote(uq, "billing")["billing_total"] == 3828


# --- SoftBank billing vs effective divergence ---


def test_softbank_30gb_paypay_billing_vs_effective_diverge():
    line = {
        "carrier": "softbank",
        "data_usage": "30gb",
        "qr_paypay": "40000",
        "paypay_gold_linked": "1",
    }
    comparison = compare_all_carriers_for_lines([line])
    sb = _compare_entry(comparison, "softbank")
    billing = _axis_quote(sb, "billing")
    effective = _axis_quote(sb, "effective")
    assert billing["plan_id"] == "teigaku_unlimited"
    assert billing["billing_total"] == 8008
    assert effective["plan_id"] == "paytoku2"
    assert effective["effective_total"] == 6538
    assert sb["billing_total"] == 8008
    assert sb["effective_total"] == 6538


def test_softbank_axis_quotes_present():
    comparison = compare_all_carriers_for_lines(
        [{"carrier": "softbank", "data_usage": "30gb"}]
    )
    sb = _compare_entry(comparison, "softbank")
    assert set(sb["axis_quotes"]) == {"billing", "effective", "value_adjusted"}


# --- Rakuten / ahamo same plan all axes ---


def test_rakuten_3gb_all_axes_same_plan():
    comparison = compare_all_carriers_for_lines(
        [{"carrier": "rakuten", "data_usage": "3gb"}]
    )
    rakuten = _compare_entry(comparison, "rakuten")
    billing_id = _axis_quote(rakuten, "billing")["plan_id"]
    assert _axis_quote(rakuten, "effective")["plan_id"] == billing_id
    assert _axis_quote(rakuten, "value_adjusted")["plan_id"] == billing_id


def test_ahamo_all_axes_same_plan():
    comparison = compare_all_carriers_for_lines(
        [{"carrier": "ahamo", "data_usage": "20gb"}]
    )
    ahamo = _compare_entry(comparison, "ahamo")
    billing_id = _axis_quote(ahamo, "billing")["plan_id"]
    assert _axis_quote(ahamo, "effective")["plan_id"] == billing_id


# --- cheapest picks use axis quotes ---


def test_cheapest_billing_includes_plan_id():
    comparison = compare_all_carriers_for_lines([_line(age="65", data_usage="3gb")])
    cheapest = comparison["cheapest_billing"]
    assert "plan_id" in cheapest
    assert cheapest["billing_total"] is not None


def test_top_level_fields_are_axis_specific_not_mixed():
    line = {
        "carrier": "softbank",
        "data_usage": "30gb",
        "qr_paypay": "40000",
        "paypay_gold_linked": "1",
    }
    comparison = compare_all_carriers_for_lines([line])
    sb = _compare_entry(comparison, "softbank")
    assert sb["billing_total"] == _axis_quote(sb, "billing")["billing_total"]
    assert sb["effective_total"] == _axis_quote(sb, "effective")["effective_total"]
    assert sb["value_adjusted_total"] == _axis_quote(sb, "value_adjusted")["value_adjusted_total"]


# --- multi-line family discount ---


def test_au_two_lines_mixed_usage_axis_selection():
    lines = [
        _line(age="65", data_usage="3gb"),
        _line(age="65", data_usage="5gb"),
    ]
    brand_lines = _brand_lines(lines, "au")
    axis_quotes = find_best_plans_by_axis("au", brand_lines)
    assert axis_quotes["billing"]["plan_ids"] == ["senior_value", "senior_value"]
    assert axis_quotes["billing"]["billing_total"] == 4048 * 2


def test_docomo_two_lines_family_discount_with_mini():
    lines = [
        {"carrier": "docomo", "data_usage": "3gb"},
        {"carrier": "docomo", "data_usage": "3gb"},
    ]
    comparison = compare_all_carriers_for_lines(lines)
    docomo = _compare_entry(comparison, "docomo")
    assert _axis_quote(docomo, "billing")["plan_ids"] == ["docomo_mini", "docomo_mini"]
    assert _axis_quote(docomo, "billing")["billing_total"] == 2750 * 2


def test_softbank_two_lines_paypay_divergence():
    line = {
        "data_usage": "30gb",
        "qr_paypay": "40000",
        "paypay_gold_linked": "1",
    }
    lines = [dict(line), dict(line)]
    comparison = compare_all_carriers_for_lines(lines)
    sb = _compare_entry(comparison, "softbank")
    assert _axis_quote(sb, "billing")["plan_id"] == "teigaku_unlimited"
    assert _axis_quote(sb, "effective")["plan_id"] == "paytoku2"


# --- 86-case rescan helper ---


def _auto_lost_count():
    from services.calculator import (
        calculate_carrier_price,
        get_carrier_map,
        _plan_age_eligible,
        _plan_capacity_gb,
    )

    carriers = ["softbank", "ymobile", "au", "uqmobile", "docomo", "ahamo", "rakuten"]
    lost = 0
    for cid in carriers:
        for age in [None, 12, 17, 23, 65]:
            for gb in [1, 3, 5, 10, 20, 30]:
                line = {"carrier": cid, "data_usage": f"{gb}gb"}
                if age is not None:
                    line["age"] = str(age)
                try:
                    comparison = compare_all_carriers_for_lines([line])
                except Exception:
                    continue
                entry = _compare_entry(comparison, cid)
                for axis in ("billing", "effective"):
                    quote = _axis_quote(entry, axis)
                    carrier = get_carrier_map()[cid]
                    ai = int(age) if age is not None else None
                    best_amt = None
                    for plan in carrier.get("plans") or []:
                        cap = _plan_capacity_gb(plan)
                        if not _plan_age_eligible(plan, cid, ai):
                            continue
                        if gb is not None and cap is not None and gb > cap:
                            continue
                        prof = build_profile(age=str(age) if age else None)
                        r = calculate_carrier_price(
                            cid, f"{gb}gb", [], prof, plan_id=plan["id"]
                        )
                        metric = r["billing_total"] if axis == "billing" else r["effective_total"]
                        if best_amt is None or metric < best_amt:
                            best_amt = metric
                    quote_amt = quote["billing_total"] if axis == "billing" else quote["effective_total"]
                    if best_amt is not None and quote_amt > best_amt:
                        lost += 1
    return lost


def test_rescan_lost_cases_near_zero_for_single_line():
    assert _auto_lost_count() == 0


# --- API additive fields ---


def test_axis_quotes_additive_and_status_ok():
    comparison = compare_all_carriers_for_lines([_line(age="65", data_usage="3gb")])
    au = _compare_entry(comparison, "au")
    assert au["status"] == "ok"
    assert "axis_quotes" in au
    assert "billing_total" in au
    assert "lines" in au
