"""フェーズ⑤B: キャリア強み・注意点説明エンジンの検証。"""

from __future__ import annotations

import copy

import pytest

from services.calculator import compare_all_carriers_for_lines
from services.carrier_explanation import attach_explanations_to_compare_result


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


def _compare(*, lines=None, home_set_flags=None, tenure_years=None):
    if lines is None:
        lines = [_line()]
    flags = home_set_flags or {
        "softbank": False,
        "au": False,
        "docomo": False,
        "docomo_denki": False,
    }
    return compare_all_carriers_for_lines(lines, tenure_years=tenure_years, home_set_flags=flags)


def _entry(result: dict, carrier_id: str) -> dict:
    return next(item for item in result["comparisons"] if item["carrier_id"] == carrier_id)


def _rule_ids(items: list[dict]) -> set[str]:
    return {item["rule_id"] for item in items}


def _ranking_snapshot(result: dict) -> dict:
    return {
        "cheapest_billing": copy.deepcopy(result["cheapest_billing"]),
        "cheapest_effective": copy.deepcopy(result["cheapest_effective"]),
        "cheapest_value_adjusted": copy.deepcopy(result["cheapest_value_adjusted"]),
    }


# --- ランキング不変 ---


def test_ranking_unchanged_after_explanations():
    lines = [_line(data_usage="10gb")]
    before = compare_all_carriers_for_lines(lines)
    snapshot = _ranking_snapshot(before)
    after = compare_all_carriers_for_lines(lines)
    assert _ranking_snapshot(after) == snapshot


def test_attach_does_not_mutate_ranking_fields():
    lines = [_line(data_usage="unlimited", qr_paypay="40000", paypay_card_tier="gold", paypay_gold_linked="1")]
    result = compare_all_carriers_for_lines(lines)
    snapshot = _ranking_snapshot(result)
    attach_explanations_to_compare_result(result, lines, {})
    assert _ranking_snapshot(result) == snapshot


# --- SoftBank ---


def test_softbank_paypay_reward_strength():
    result = _compare(
        lines=[
            _line(
                carrier="softbank",
                data_usage="unlimited",
                qr_paypay="40000",
                paypay_card_tier="gold",
                paypay_gold_linked="1",
            )
        ]
    )
    sb = _entry(result, "softbank")
    assert "sb_paypay_reward" in _rule_ids(sb["strengths"])
    msg = next(item for item in sb["strengths"] if item["rule_id"] == "sb_paypay_reward")
    qr_amount = sum(
        r["amount"]
        for line in sb["lines"]
        for r in line["rewards"]
        if r["id"] == "qr_reward"
    )
    assert str(qr_amount) in msg["message"].replace(",", "")
    assert msg["evidence"]["amount"] == qr_amount


def test_softbank_gold_linked_strength():
    result = _compare(
        lines=[
            _line(
                carrier="softbank",
                data_usage="unlimited",
                qr_paypay="40000",
                paypay_gold_linked="1",
            )
        ]
    )
    sb = _entry(result, "softbank")
    assert sb["axis_quotes"]["effective"]["plan_id"] == "paytoku2"
    assert "sb_gold_linked" in _rule_ids(sb["strengths"])


def test_softbank_family_discount_strength():
    result = _compare(
        lines=[
            _line(carrier="softbank", data_usage="10gb", discounts=["family_discount"]),
            _line(carrier="au", age="40", data_usage="10gb"),
        ]
    )
    sb = _entry(result, "softbank")
    assert "sb_family" in _rule_ids(sb["strengths"])
    fam = next(item for item in sb["strengths"] if item["rule_id"] == "sb_family")
    assert fam["evidence"]["amount"] == fam["evidence"]["amount"]


def test_softbank_home_set_strength():
    result = compare_all_carriers_for_lines(
        [_line(carrier="softbank", data_usage="10gb")],
        home_set_flags={"softbank": True, "au": False, "docomo": False, "docomo_denki": False},
    )
    sb = _entry(result, "softbank")
    assert "sb_home" in _rule_ids(sb["strengths"])


def test_softbank_no_paypay_strength_without_reward():
    result = _compare(lines=[_line(carrier="softbank", data_usage="10gb")])
    sb = _entry(result, "softbank")
    assert "sb_paypay_reward" not in _rule_ids(sb["strengths"])


# --- au ---


def test_au_point_cash_separate_messages():
    result = _compare(
        lines=[
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
    au = _entry(result, "au")
    ids = _rule_ids(au["strengths"])
    assert "au_qr_reward" in ids
    assert "au_bill_payment_cash" in ids
    assert "au_deposit_cash" in ids

    bill = next(item for item in au["strengths"] if item["rule_id"] == "au_bill_payment_cash")
    deposit = next(item for item in au["strengths"] if item["rule_id"] == "au_deposit_cash")
    assert bill["evidence"]["type"] == "CASH"
    assert deposit["evidence"]["type"] == "CASH"
    assert "現金還元" in bill["message"]
    assert "P" in next(item["message"] for item in au["strengths"] if item["rule_id"] == "au_qr_reward")


def test_au_family_and_smart_value():
    result = compare_all_carriers_for_lines(
        [
            _line(carrier="au", data_usage="10gb"),
            _line(carrier="softbank", data_usage="10gb"),
        ],
        home_set_flags={"softbank": False, "au": True, "docomo": False, "docomo_denki": False},
    )
    au = _entry(result, "au")
    assert "au_family" in _rule_ids(au["strengths"])
    assert "au_smart_value" in _rule_ids(au["strengths"])


def test_au_no_paypay_strength():
    result = _compare(lines=[_line(carrier="au", data_usage="10gb")])
    au = _entry(result, "au")
    assert "sb_paypay_reward" not in _rule_ids(au["strengths"])
    assert "sb_gold_linked" not in _rule_ids(au["strengths"])


# --- docomo ---


def test_docomo_poikatsu_strength():
    result = _compare(
        lines=[
            _line(
                carrier="docomo",
                data_usage="unlimited",
                qr_dbarai="40000",
                dcard_tier="platinum",
                docomo_bill_dcard="1",
            )
        ]
    )
    docomo = _entry(result, "docomo")
    assert "docomo_poikatsu" in _rule_ids(docomo["strengths"])
    pt = next(item for item in docomo["strengths"] if item["rule_id"] == "docomo_poikatsu")
    reward_amount = sum(
        r["amount"]
        for line in docomo["lines"]
        for r in line["rewards"]
        if r["id"] == "docomo_poikatsu_reward"
    )
    assert pt["evidence"]["amount"] == reward_amount


def test_docomo_d_card_and_family():
    result = _compare(
        lines=[
            _line(carrier="docomo", data_usage="10gb", docomo_bill_dcard="1", discounts=["everyone_docomo"]),
            _line(carrier="softbank", data_usage="10gb"),
        ]
    )
    docomo = _entry(result, "docomo")
    ids = _rule_ids(docomo["strengths"])
    assert "docomo_d_card" in ids or "docomo_everyone_docomo" in ids


def test_docomo_no_poikatsu_without_reward():
    result = _compare(lines=[_line(carrier="docomo", data_usage="10gb")])
    docomo = _entry(result, "docomo")
    assert "docomo_poikatsu" not in _rule_ids(docomo["strengths"])


# --- Rakuten ---


def test_rakuten_billing_cheapest_strength():
    result = _compare(lines=[_line(data_usage="3gb")])
    rakuten = _entry(result, "rakuten")
    assert result["cheapest_billing"]["carrier_id"] == "rakuten"
    assert "cheapest_billing" in _rule_ids(rakuten["strengths"]) or "cheapest_all_three" in _rule_ids(
        rakuten["strengths"]
    )


def test_rakuten_billing_cheapest_effective_not_caution():
    result = _compare(
        lines=[
            _line(
                carrier="softbank",
                data_usage="unlimited",
                qr_paypay="40000",
                paypay_card_tier="gold",
                paypay_gold_linked="1",
            )
        ]
    )
    rakuten = _entry(result, "rakuten")
    if (
        result["cheapest_billing"]["carrier_id"] == "rakuten"
        and result["cheapest_effective"]["carrier_id"] != "rakuten"
    ):
        assert "rakuten_billing_not_effective" in _rule_ids(rakuten["cautions"])


def test_rakuten_usage_point_strength():
    result = _compare(lines=[_line(carrier="rakuten", data_usage="20gb")])
    rakuten = _entry(result, "rakuten")
    assert "rakuten_usage_point" in _rule_ids(rakuten["strengths"])


def test_rakuten_no_foreign_strengths():
    result = _compare(
        lines=[
            _line(
                carrier="softbank",
                data_usage="unlimited",
                qr_paypay="40000",
                paypay_gold_linked="1",
            )
        ]
    )
    rakuten = _entry(result, "rakuten")
    assert "sb_paypay_reward" not in _rule_ids(rakuten["strengths"])
    assert "au_bill_payment_cash" not in _rule_ids(rakuten["strengths"])


# --- Y!mobile / UQ / ahamo ---


def test_ymobile_has_explanation_fields():
    result = _compare(lines=[_line(carrier="ymobile", data_usage="10gb")])
    ym = _entry(result, "ymobile")
    assert "strengths" in ym
    assert "cautions" in ym
    assert len(ym["strengths"]) <= 3


def test_ymobile_two_line_caution():
    result = _compare(
        lines=[
            _line(carrier="softbank", data_usage="10gb"),
            _line(carrier="au", data_usage="10gb"),
        ]
    )
    ym = _entry(result, "ymobile")
    assert "ym_primary_no_family" in _rule_ids(ym["cautions"])


def test_uq_family_home_strengths():
    result = compare_all_carriers_for_lines(
        [
            _line(carrier="uqmobile", data_usage="10gb"),
            _line(carrier="softbank", data_usage="10gb"),
        ],
        home_set_flags={"softbank": False, "au": True, "docomo": False, "docomo_denki": False},
    )
    uq = _entry(result, "uqmobile")
    ids = _rule_ids(uq["strengths"])
    assert "uq_family_set" in ids or "uq_home_set" in ids


def test_uq_komikomi_caution_on_plan():
    result = _compare(lines=[_line(carrier="uqmobile", data_usage="35gb", plan="komikomi_value")])
    uq = _entry(result, "uqmobile")
    assert "uq_komikomi_family_excluded" in _rule_ids(uq["cautions"])


def test_ahamo_simplicity_strength():
    result = _compare(lines=[_line(carrier="ahamo", data_usage="30gb")])
    ahamo = _entry(result, "ahamo")
    assert "ahamo_simplicity" in _rule_ids(ahamo["strengths"])


def test_ahamo_caution_no_family_self():
    result = _compare(lines=[_line(carrier="ahamo", data_usage="30gb")])
    ahamo = _entry(result, "ahamo")
    assert "ahamo_no_family_self" in _rule_ids(ahamo["cautions"])


# --- ブランド汚染 ---


def test_softbank_no_dbarai_strength():
    result = _compare(
        lines=[
            _line(
                carrier="docomo",
                data_usage="unlimited",
                qr_dbarai="40000",
                docomo_bill_dcard="1",
            )
        ]
    )
    sb = _entry(result, "softbank")
    assert "docomo_poikatsu" not in _rule_ids(sb["strengths"])


def test_softbank_no_au_cash_strength():
    result = _compare(
        lines=[
            _line(
                carrier="au",
                data_usage="unlimited",
                au_bill_payment_mode="au_pay_card",
                au_jibun_bank_balance="500000",
            )
        ]
    )
    sb = _entry(result, "softbank")
    assert "au_bill_payment_cash" not in _rule_ids(sb["strengths"])


# --- API / 構造 ---


def test_comparisons_include_strengths_and_cautions(client):
    response = client.get("/api/compare?lines[0][carrier]=softbank&lines[0][data_usage]=10gb")
    assert response.status_code == 200
    payload = response.get_json()
    for item in payload["comparisons"]:
        assert "strengths" in item
        assert "cautions" in item
        assert "recommended" not in payload


def test_strength_count_limit():
    result = _compare(
        lines=[
            _line(
                carrier="softbank",
                data_usage="unlimited",
                qr_paypay="40000",
                paypay_gold_linked="1",
                paypay_card_tier="gold",
                discounts=["family_discount", "home_fiber_set"],
            ),
            _line(carrier="au", data_usage="10gb"),
        ],
        home_set_flags={"softbank": True, "au": False, "docomo": False, "docomo_denki": False},
    )
    sb = _entry(result, "softbank")
    assert len(sb["strengths"]) <= 3
    assert len(sb["cautions"]) <= 2


@pytest.fixture
def client():
    from app import app as flask_app

    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client
