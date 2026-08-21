"""フェーズ③ 実装A: PayPay GOLD連携 / au通信料CASH / docomo dカード割の誤判定修正。"""

import pytest

from services.calculator import (
    build_profile,
    build_qr_context,
    calculate_carrier_price,
)


# --- SoftBank ---


@pytest.mark.parametrize(
    "gold_linked,expected_rate,expected_reward",
    [
        (False, 5, 2000),
        (True, 10, 4000),
    ],
)
def test_softbank_paytoku2_gold_linked_controls_rate_not_card_tier(gold_linked, expected_rate, expected_reward):
    result = calculate_carrier_price(
        "softbank",
        "10",
        ["paypay_card_gold"],
        build_profile(),
        plan_id="paytoku2",
        qr=build_qr_context(
            qr_paypay="40000",
            paypay_card_tier="gold",
            paypay_gold_linked="1" if gold_linked else None,
        ),
    )

    assert result["qr_rate"]["percent"] == expected_rate
    assert result["qr_points"] == expected_reward
    assert result["reward_total"] == expected_reward
    assert result["billing_total"] == 9988


def test_softbank_paytoku2_standard_card_without_gold_linked_5_percent():
    result = calculate_carrier_price(
        "softbank",
        "10",
        ["paypay_card"],
        build_profile(),
        plan_id="paytoku2",
        qr=build_qr_context(qr_paypay="40000", paypay_card_tier="standard"),
    )

    assert result["qr_rate"]["percent"] == 5
    assert result["qr_points"] == 2000


def test_softbank_paytoku2_gold_linked_caps_at_4000():
    result = calculate_carrier_price(
        "softbank",
        "10",
        ["paypay_card_gold"],
        build_profile(),
        plan_id="paytoku2",
        qr=build_qr_context(
            qr_paypay="50000",
            paypay_card_tier="gold",
            paypay_gold_linked="1",
        ),
    )

    assert result["qr_points"] == 4000
    assert result["reward_total"] == 4000


def test_softbank_teigaku_ignores_gold_linked_for_billing_only():
    without_link = calculate_carrier_price(
        "softbank",
        "10",
        ["paypay_card_gold"],
        build_profile(),
        plan_id="teigaku_unlimited",
        qr=build_qr_context(paypay_gold_linked="1"),
    )
    without_any = calculate_carrier_price(
        "softbank",
        "10",
        ["paypay_card_gold"],
        build_profile(),
        plan_id="teigaku_unlimited",
    )

    assert without_link["billing_total"] == without_any["billing_total"] == 7458
    assert without_link["reward_total"] == 0


# --- au ---


def test_au_bill_payment_cash_card_other_bank():
    result = calculate_carrier_price(
        "au",
        "1",
        [],
        build_profile(),
        plan_id="unlimited_max_moneyact2",
        qr=build_qr_context(au_bill_payment_mode="au_pay_card"),
    )

    assert result["cash_rewards"] == 1100
    assert result["reward_total"] == 1100
    assert result["qr_points"] == 0
    cash = [item for item in result["rewards"] if item["type"] == "CASH"]
    assert len(cash) == 1
    assert cash[0]["id"] == "au_bill_payment_cash"


def test_au_bill_payment_cash_jibun_direct_debit():
    result = calculate_carrier_price(
        "au",
        "1",
        [],
        build_profile(),
        plan_id="unlimited_max_moneyact2",
        qr=build_qr_context(au_bill_payment_mode="au_jibun_bank_direct_debit"),
    )

    assert result["cash_rewards"] == 1100
    assert result["reward_total"] == 1100


def test_au_bill_payment_cash_card_with_jibun_withdrawal():
    result = calculate_carrier_price(
        "au",
        "1",
        [],
        build_profile(),
        plan_id="unlimited_max_moneyact2",
        qr=build_qr_context(
            au_bill_payment_mode="au_pay_card",
            au_pay_card_bank_is_jibun="1",
        ),
    )

    assert result["cash_rewards"] == 1650
    assert result["reward_total"] == 1650
    assert result["effective_total"] == result["billing_total"] - 1650


def test_au_bill_payment_cash_not_double_counted():
    result = calculate_carrier_price(
        "au",
        "1",
        [],
        build_profile(),
        plan_id="unlimited_max_moneyact2",
        qr=build_qr_context(
            au_bill_payment_mode="au_pay_card",
            au_pay_card_bank_is_jibun="1",
        ),
    )

    assert result["reward_total"] == 1650
    assert result["reward_total"] != 2750


def test_au_bill_payment_cash_none_when_no_condition():
    result = calculate_carrier_price(
        "au",
        "1",
        [],
        build_profile(),
        plan_id="unlimited_max_moneyact2",
        qr=build_qr_context(au_bill_payment_mode="other"),
    )

    assert result["cash_rewards"] == 0
    assert result["reward_total"] == 0


def test_au_valuelink_no_cash_bonus():
    result = calculate_carrier_price(
        "au",
        "10",
        [],
        build_profile(),
        plan_id="au_valuelink",
        qr=build_qr_context(au_bill_payment_mode="au_pay_card", au_pay_card_bank_is_jibun="1"),
    )

    assert result["cash_rewards"] == 0
    assert result["reward_total"] == 0


# --- docomo ---


def test_docomo_dbarai_spend_does_not_apply_d_card_discount():
    result = calculate_carrier_price(
        "docomo",
        "10",
        [],
        build_profile(),
        plan_id="docomo_max_unlimited",
        qr=build_qr_context(qr_dbarai="30000", dcard_tier="gold"),
    )

    assert not any(item["id"] == "d_card" for item in result["applied_discounts"])
    assert result["resolved_discount_amounts"]["d_card"] == 550


def test_docomo_bill_dcard_applies_discount_without_dbarai_spend():
    result = calculate_carrier_price(
        "docomo",
        "10",
        ["d_card"],
        build_profile(),
        plan_id="docomo_max_unlimited",
        qr=build_qr_context(dcard_tier="gold", docomo_bill_dcard="1"),
    )

    assert any(item["id"] == "d_card" and item["amount"] == 550 for item in result["applied_discounts"])


def test_docomo_bill_dcard_applied_once_with_dbarai_spend():
    result = calculate_carrier_price(
        "docomo",
        "10",
        ["d_card"],
        build_profile(),
        plan_id="docomo_poikatsu_max",
        qr=build_qr_context(qr_dbarai="30000", dcard_tier="gold", docomo_bill_dcard="1"),
    )

    d_card_discounts = [item for item in result["applied_discounts"] if item["id"] == "d_card"]
    assert len(d_card_discounts) == 1
    assert d_card_discounts[0]["amount"] == 550


def test_docomo_gold_tier_without_bill_dcard_no_discount():
    result = calculate_carrier_price(
        "docomo",
        "10",
        [],
        build_profile(),
        plan_id="docomo_max_unlimited",
        qr=build_qr_context(dcard_tier="gold"),
    )

    assert not any(item["id"] == "d_card" for item in result["applied_discounts"])


# --- 7ブランド回帰 ---


@pytest.mark.parametrize(
    "carrier_id,plan_id,data_usage,discounts",
    [
        ("softbank", "teigaku_unlimited", "10", []),
        ("ymobile", "simple3_m", "10", []),
        ("au", "unlimited_max_plus", "10", []),
        ("uqmobile", "tokutoku_30gb", "10", []),
        ("docomo", "docomo_max_unlimited", "10", []),
        ("ahamo", "ahamo_30gb", "10", []),
        ("rakuten", "saikyo_unlimited", "10", []),
    ],
)
def test_seven_carrier_baseline_billing_unchanged(carrier_id, plan_id, data_usage, discounts):
    result = calculate_carrier_price(
        carrier_id,
        data_usage,
        discounts,
        build_profile(),
        plan_id=plan_id,
    )

    assert result["billing_total"] == result["total"]
    if result["carrier_id"] != "rakuten":
        assert result["reward_total"] == 0
        assert result["effective_total"] == result["billing_total"]
