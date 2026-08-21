"""フェーズ⑤A: 全キャリア横断比較エンジンの検証。"""

from __future__ import annotations

import pytest

from app import app as flask_app
from services.calculator import (
    COMPARISON_CARRIER_IDS,
    calculate_multi_carrier_lines,
    compare_all_carriers_for_lines,
)


def _line(**kwargs):
    base = {
        "carrier": "softbank",
        "age": None,
        "data_usage": "10gb",
        "plan": None,
        "discounts": [],
        "qr_paypay": None,
        "qr_dbarai": None,
        "qr_aupay": None,
        "paypay_card_tier": None,
        "paypay_gold_linked": None,
        "aupay_gold": None,
        "dcard_tier": "standard",
        "au_bill_payment_mode": "other",
        "docomo_bill_dcard": None,
        "au_jibun_bank_balance": None,
    }
    base.update(kwargs)
    return base


def _softbank_entry(comparison: dict) -> dict:
    return next(item for item in comparison["comparisons"] if item["carrier_id"] == "softbank")


def _au_entry(comparison: dict) -> dict:
    return next(item for item in comparison["comparisons"] if item["carrier_id"] == "au")


def _rakuten_entry(comparison: dict) -> dict:
    return next(item for item in comparison["comparisons"] if item["carrier_id"] == "rakuten")


def _docomo_entry(comparison: dict) -> dict:
    return next(item for item in comparison["comparisons"] if item["carrier_id"] == "docomo")


# --- A: 1回線・10GB・割引なし ---


def test_compare_all_carriers_returns_seven_brands():
    comparison = compare_all_carriers_for_lines([_line(data_usage="10gb")])

    assert len(comparison["comparisons"]) == 7
    assert comparison["comparison_complete"] is True
    assert {item["carrier_id"] for item in comparison["comparisons"]} == set(COMPARISON_CARRIER_IDS)


def test_compare_all_carriers_exposes_three_cheapest_keys():
    comparison = compare_all_carriers_for_lines([_line(data_usage="10gb")])

    assert comparison["cheapest_billing"] is not None
    assert comparison["cheapest_effective"] is not None
    assert comparison["cheapest_value_adjusted"] is not None
    assert "recommended" not in comparison


def test_compare_all_carriers_no_recommended_field():
    comparison = compare_all_carriers_for_lines([_line(data_usage="10gb")])

    assert "recommended" not in comparison
    assert "strengths" not in comparison
    assert "cautions" not in comparison


# --- 回帰: 単独計算と横断比較内 SoftBank が一致 ---


def test_softbank_cross_compare_matches_axis_billing_quote():
    lines = [
        _line(
            carrier="softbank",
            age="23",
            data_usage="30gb",
            qr_paypay="40000",
            paypay_card_tier="gold",
            paypay_gold_linked="1",
            discounts=["family_discount"],
        )
    ]
    cross = compare_all_carriers_for_lines(lines)
    entry = _softbank_entry(cross)
    billing_quote = entry["axis_quotes"]["billing"]
    effective_quote = entry["axis_quotes"]["effective"]

    assert entry["status"] == "ok"
    assert entry["billing_total"] == billing_quote["billing_total"]
    assert entry["effective_total"] == effective_quote["effective_total"]
    assert entry["value_adjusted_total"] == entry["axis_quotes"]["value_adjusted"]["value_adjusted_total"]
    assert billing_quote["plan_id"] == "teigaku_unlimited"
    assert effective_quote["plan_id"] == "paytoku2"


def test_two_line_softbank_cross_compare_matches_direct_calculation():
    lines = [
        _line(carrier="softbank", age="23", data_usage="10gb", discounts=["family_discount"]),
        _line(carrier="softbank", age="40", data_usage="10gb", discounts=["family_discount"]),
    ]
    direct = calculate_multi_carrier_lines(lines)
    cross = compare_all_carriers_for_lines(lines)
    entry = _softbank_entry(cross)

    assert entry["billing_total"] == direct["totals"]["billing_total"]
    assert entry["effective_total"] == direct["totals"]["effective_total"]
    assert entry["value_adjusted_total"] == direct["totals"]["value_adjusted_total"]


# --- B: PayPay ありで billing / effective が分離 ---


def test_paytoku_can_change_effective_ranking_without_failing():
    comparison = compare_all_carriers_for_lines(
        [
            _line(
                carrier="softbank",
                data_usage="unlimited",
                qr_paypay="40000",
                paypay_card_tier="gold",
                paypay_gold_linked="1",
            )
        ]
    )
    softbank = _softbank_entry(comparison)
    rakuten = _rakuten_entry(comparison)
    billing_quote = softbank["axis_quotes"]["billing"]
    effective_quote = softbank["axis_quotes"]["effective"]

    assert billing_quote["billing_total"] > rakuten["billing_total"]
    assert effective_quote["reward_total"] > 0
    assert softbank["reward_total"] == effective_quote["reward_total"]
    assert softbank["effective_total"] == effective_quote["effective_total"]
    assert billing_quote["plan_id"] != effective_quote["plan_id"]
    assert comparison["cheapest_billing"]["carrier_id"] in {"rakuten", "ymobile", "uqmobile"}
    # effective 順位が billing と異なっても正常（固定しない）


# --- C: 2回線・家族割 ---


def test_family_discount_applied_per_brand_on_two_lines():
    """混在回線入力時は各ブランド比較で家族割が再計算される。"""
    from services.calculator import find_best_plans_by_axis, _lines_for_brand_comparison
    from services.data_loader import load_all_carriers

    comparison = compare_all_carriers_for_lines(
        [
            _line(carrier="softbank", age="30", data_usage="10gb"),
            _line(carrier="au", age="35", data_usage="10gb"),
        ],
        home_set_flags={group: False for group in ("softbank", "au", "docomo", "docomo_denki")},
    )
    softbank = _softbank_entry(comparison)
    au = _au_entry(comparison)

    carrier_map = {carrier["id"]: carrier for carrier in load_all_carriers()}
    family_discount_ids = {
        carrier["id"]: [
            discount["id"]
            for discount in carrier.get("discounts") or []
            if discount.get("line_tiers")
        ]
        for carrier in load_all_carriers()
    }
    softbank_lines = _lines_for_brand_comparison(
        [
            _line(carrier="softbank", age="30", data_usage="10gb"),
            _line(carrier="au", age="35", data_usage="10gb"),
        ],
        "softbank",
        {group: False for group in ("softbank", "au", "docomo", "docomo_denki")},
        carrier_map,
        family_discount_ids,
    )
    au_lines = _lines_for_brand_comparison(
        [
            _line(carrier="softbank", age="30", data_usage="10gb"),
            _line(carrier="au", age="35", data_usage="10gb"),
        ],
        "au",
        {group: False for group in ("softbank", "au", "docomo", "docomo_denki")},
        carrier_map,
        family_discount_ids,
    )
    expected_softbank = find_best_plans_by_axis("softbank", softbank_lines)["billing"]["billing_total"]
    expected_au = find_best_plans_by_axis("au", au_lines)["billing"]["billing_total"]

    assert softbank["billing_total"] == expected_softbank
    assert au["billing_total"] == expected_au
    assert softbank["status"] == "ok"
    assert au["status"] == "ok"


# --- D: 固定回線条件は該当ブランドのみ ---


def test_home_set_applies_only_to_matching_brand():
    from services.calculator import find_best_plans_by_axis, _lines_for_brand_comparison
    from services.data_loader import load_all_carriers

    home_set_flags = {
        "softbank": True,
        "au": False,
        "docomo": False,
        "docomo_denki": False,
    }
    source_lines = [_line(carrier="softbank", data_usage="10gb")]
    comparison = compare_all_carriers_for_lines(
        source_lines,
        home_set_flags=home_set_flags,
    )
    softbank = _softbank_entry(comparison)
    au = _au_entry(comparison)

    carrier_map = {carrier["id"]: carrier for carrier in load_all_carriers()}
    family_discount_ids = {
        carrier["id"]: [
            discount["id"]
            for discount in carrier.get("discounts") or []
            if discount.get("line_tiers")
        ]
        for carrier in load_all_carriers()
    }
    softbank_lines = _lines_for_brand_comparison(
        source_lines, "softbank", home_set_flags, carrier_map, family_discount_ids
    )
    au_lines = _lines_for_brand_comparison(
        source_lines, "au", home_set_flags, carrier_map, family_discount_ids
    )
    expected_softbank = find_best_plans_by_axis(
        "softbank", softbank_lines, home_set_flags=home_set_flags
    )["billing"]["billing_total"]
    expected_au = find_best_plans_by_axis("au", au_lines, home_set_flags=home_set_flags)[
        "billing"
    ]["billing_total"]

    assert softbank["billing_total"] == expected_softbank
    assert au["billing_total"] == expected_au
    assert softbank["billing_total"] != au["billing_total"]


# --- E: au PAY は au のみ ---


def test_au_pay_rewards_only_on_au_brand():
    comparison = compare_all_carriers_for_lines(
        [
            _line(
                carrier="au",
                data_usage="unlimited",
                qr_aupay="50000",
                aupay_gold="1",
                au_bill_payment_mode="au_pay_card",
                au_pay_card_bank_is_jibun="1",
                au_jibun_bank_balance="500000",
            )
        ]
    )
    au = _au_entry(comparison)
    softbank = _softbank_entry(comparison)

    assert au["reward_total"] > 0
    assert softbank["reward_total"] == 0


# --- F: d払いは docomo のみ ---


def test_dbarai_rewards_only_on_docomo_brand():
    comparison = compare_all_carriers_for_lines(
        [
            _line(
                carrier="docomo",
                data_usage="unlimited",
                qr_dbarai="40000",
                dcard_tier="platinum",
                docomo_bill_dcard="1",
            )
        ]
    )
    docomo = _docomo_entry(comparison)
    rakuten = _rakuten_entry(comparison)
    softbank = _softbank_entry(comparison)

    assert docomo["reward_total"] > 0
    assert softbank["reward_total"] == 0
    assert rakuten["reward_total"] > 0
    assert rakuten["reward_total"] < docomo["reward_total"]


def test_dbarai_not_applied_to_softbank():
    comparison = compare_all_carriers_for_lines(
        [
            _line(
                carrier="docomo",
                data_usage="unlimited",
                qr_dbarai="40000",
                dcard_tier="platinum",
                docomo_bill_dcard="1",
            )
        ]
    )
    softbank = _softbank_entry(comparison)
    assert softbank["reward_total"] == 0


# --- G: 楽天利用料金ポイント ---


def test_rakuten_usage_points_only_on_rakuten():
    comparison = compare_all_carriers_for_lines(
        [_line(carrier="rakuten", data_usage="20gb", discounts=["family_discount"])]
    )
    rakuten = _rakuten_entry(comparison)
    au = _au_entry(comparison)

    assert rakuten["reward_total"] > 0
    assert au["reward_total"] == 0


# --- 3種類が同一 / 異なるケース ---


def test_three_cheapest_can_be_same_carrier():
    comparison = compare_all_carriers_for_lines([_line(data_usage="3gb")])
    billing = comparison["cheapest_billing"]["carrier_id"]
    effective = comparison["cheapest_effective"]["carrier_id"]
    adjusted = comparison["cheapest_value_adjusted"]["carrier_id"]

    assert billing == effective == adjusted == "rakuten"


def test_three_cheapest_are_independent_results():
    """3種類の最安は別キーとして返る（同一キャリアになる場合も正常）。"""
    comparison = compare_all_carriers_for_lines([_line(data_usage="3gb")])

    billing = comparison["cheapest_billing"]
    effective = comparison["cheapest_effective"]
    adjusted = comparison["cheapest_value_adjusted"]

    assert billing is not None
    assert effective is not None
    assert adjusted is not None
    assert billing["carrier_id"] == effective["carrier_id"] == adjusted["carrier_id"] == "rakuten"
    assert "recommended" not in comparison


def test_billing_and_effective_use_different_sort_keys():
    """billing 最安と effective 最安は別 tie-break を持つ（結果が同じでも構造は独立）。"""
    comparison = compare_all_carriers_for_lines(
        [
            _line(
                carrier="softbank",
                data_usage="unlimited",
                qr_paypay="40000",
                paypay_card_tier="gold",
                paypay_gold_linked="1",
            )
        ]
    )
    assert comparison["cheapest_billing"]["carrier_id"] in {"rakuten", "ymobile", "uqmobile"}
    assert comparison["cheapest_billing"]["billing_total"] <= comparison["cheapest_effective"]["billing_total"]
    assert comparison["cheapest_effective"]["effective_total"] <= comparison["cheapest_billing"]["effective_total"]


# --- API ---


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client


def test_api_compare_returns_cross_carrier_result(client):
    response = client.get("/api/compare?lines[0][carrier]=softbank&lines[0][data_usage]=10gb")
    assert response.status_code == 200
    payload = response.get_json()
    assert len(payload["comparisons"]) == 7
    assert payload["cheapest_billing"] is not None
    assert "recommended" not in payload


def test_api_calculate_unchanged(client):
    response = client.get("/api/calculate?lines[0][carrier]=softbank&lines[0][data_usage]=10gb")
    assert response.status_code == 200
    payload = response.get_json()
    assert "lines" in payload
    assert "totals" in payload
    assert "comparisons" not in payload
