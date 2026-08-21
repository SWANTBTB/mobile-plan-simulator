"""Step 4: billing_total / reward_total / effective_total 責務分離の検証テスト。"""

from unittest.mock import patch

import pytest

from services.calculator import (
    build_profile,
    build_qr_context,
    calculate_carrier_price,
    calculate_multi_carrier_lines,
)


def _line(carrier, plan, discounts=None, **kwargs):
    payload = {
        "carrier": carrier,
        "plan": plan,
        "discounts": discounts or [],
    }
    payload.update(kwargs)
    return payload


def _assert_billing_aliases(result):
    assert result["billing_total"] == result["total"]
    assert result["reward_total"] == result["qr_points"] + result.get("cash_rewards", 0)


def _assert_rewards_consistency(result):
    rewards = result["rewards"]
    if result["reward_total"] == 0:
        assert rewards == []
        return
    assert sum(item["amount"] for item in rewards) == result["reward_total"]


# --- 1. 単回線・還元なし ---


def test_single_line_no_reward_billing_aliases_and_effective():
    result = calculate_carrier_price(
        "softbank",
        "10",
        ["paypay_card"],
        build_profile(),
        plan_id="teigaku_unlimited",
    )

    _assert_billing_aliases(result)
    assert result["billing_total"] == 7678
    assert result["reward_total"] == 0
    assert result["qr_points"] == 0
    assert result["effective_total"] == 7678
    assert result["effective_total"] == result["billing_total"]
    _assert_rewards_consistency(result)


# --- 2. 単回線・還元あり ---


def test_single_line_with_reward_fixed_amounts():
    result = calculate_carrier_price(
        "au",
        "1",
        [],
        build_profile(),
        plan_id="unlimited_max_moneyact2",
        qr={
            "spend": {"aupay": 0},
            "au_pay_card_bill": True,
            "au_jibun_bank": True,
            "aupay_gold": False,
        },
    )

    _assert_billing_aliases(result)
    assert result["billing_total"] == 7458
    assert result["qr_points"] == 0
    assert result["cash_rewards"] == 1650
    assert result["reward_total"] == 1650
    assert result["effective_total"] == 5808
    assert result["effective_total"] == max(0, result["billing_total"] - result["reward_total"])
    _assert_rewards_consistency(result)


def test_single_line_with_qr_spend_reward_fixed_amounts():
    result = calculate_carrier_price(
        "softbank",
        "10",
        ["paypay_card"],
        build_profile(),
        plan_id="paytoku2",
        qr=build_qr_context(qr_paypay="4000"),
    )

    _assert_billing_aliases(result)
    assert result["billing_total"] == 10208
    assert result["reward_total"] == 200
    assert result["effective_total"] == 10008
    assert result["effective_total"] == max(0, result["billing_total"] - result["reward_total"])
    _assert_rewards_consistency(result)
    assert len(result["rewards"]) == 1
    assert result["rewards"][0]["amount"] == 200


# --- 3. bundled_value あり ---


def test_bundled_value_adjusts_value_total_not_reward():
    result = calculate_carrier_price(
        "au",
        "10",
        [],
        build_profile(),
        plan_id="au_valuelink",
    )

    _assert_billing_aliases(result)
    assert result["bundled_value"] == 548
    assert result["reward_total"] == 0
    assert result["effective_total"] == 8008
    assert result["value_adjusted_total"] == max(0, result["effective_total"] - result["bundled_value"])
    assert result["value_adjusted_total"] == 7460
    assert result["bundled_value"] not in {item["amount"] for item in result["rewards"]}


# --- 4. 複数回線 ---


def test_multi_line_household_totals_match_line_sums():
    comparison = calculate_multi_carrier_lines(
        [
            _line(
                "softbank",
                "teigaku_unlimited",
                ["paypay_card"],
                data_usage="10",
            ),
            _line("ymobile", "simple3_m", [], data_usage="3"),
        ]
    )
    lines = comparison["lines"]
    totals = comparison["totals"]

    assert len(lines) == 2
    assert totals["billing_total"] == sum(line["billing_total"] for line in lines)
    assert totals["reward_total"] == sum(line["reward_total"] for line in lines)
    assert totals["effective_total"] == sum(line["effective_total"] for line in lines)
    assert totals["total"] == totals["billing_total"]
    assert lines[0]["billing_total"] == 7678
    assert lines[1]["billing_total"] == 4378
    assert totals["billing_total"] == 7678 + 4378
    assert totals["reward_total"] == 0
    assert totals["effective_total"] == 12056


def test_multi_line_with_reward_household_reward_total():
    comparison = calculate_multi_carrier_lines(
        [
            _line(
                "softbank",
                "paytoku2",
                ["paypay_card"],
                data_usage="10",
                qr_paypay="4000",
            ),
            _line("ymobile", "simple3_m", [], data_usage="3"),
        ]
    )
    lines = comparison["lines"]
    totals = comparison["totals"]

    assert totals["reward_total"] == sum(line["reward_total"] for line in lines)
    assert totals["reward_total"] == 200
    assert totals["billing_total"] == 10208 + 4378
    assert totals["effective_total"] == 10008 + 4378


# --- 5. rewards[] ---


def test_rewards_empty_when_no_reward():
    result = calculate_carrier_price(
        "ahamo",
        "10",
        [],
        build_profile(),
        plan_id="ahamo_30gb",
    )
    assert result["rewards"] == []
    _assert_rewards_consistency(result)


def test_rewards_sum_equals_reward_total():
    result = calculate_carrier_price(
        "au",
        "1",
        [],
        build_profile(),
        plan_id="unlimited_max_moneyact2",
        qr={
            "spend": {"aupay": 0},
            "au_pay_card_bill": True,
            "au_jibun_bank": True,
            "aupay_gold": False,
        },
    )
    _assert_rewards_consistency(result)
    cash_rewards = [item for item in result["rewards"] if item.get("type") == "CASH"]
    assert len(cash_rewards) == 1
    assert cash_rewards[0]["amount"] == 1650


# --- 6. 下限処理 ---


def test_effective_total_floors_at_zero_when_reward_exceeds_billing():
    """既存JSONでは還元>請求を自然再現できないため、還元額のみテスト側で差し替える。"""
    with patch(
        "services.calculator.calculate_qr_points",
        return_value=(9000, {"wallet": "paypay", "wallet_label": "PayPay", "percent": 10, "cap": 9000}, 0, 0, 0),
    ):
        result = calculate_carrier_price(
            "softbank",
            "10",
            ["paypay_card"],
            build_profile(),
            plan_id="teigaku_unlimited",
        )

    assert result["billing_total"] == 7678
    assert result["reward_total"] == 9000
    assert result["effective_total"] == 0
    assert result["effective_total"] == max(0, result["billing_total"] - result["reward_total"])


@pytest.mark.parametrize(
    "carrier_id,plan_id,data_usage",
    [
        ("softbank", "teigaku_unlimited", "10"),
        ("ymobile", "simple3_m", "10"),
        ("au", "unlimited_max_plus", "10"),
        ("uqmobile", "tokutoku_30gb", "10"),
        ("docomo", "docomo_max_unlimited", "10"),
        ("ahamo", "ahamo_30gb", "10"),
        ("rakuten", "saikyo_unlimited", "10"),
    ],
)
def test_all_carriers_billing_reward_invariants_without_qr(carrier_id, plan_id, data_usage):
    result = calculate_carrier_price(
        carrier_id,
        data_usage,
        [],
        build_profile(),
        plan_id=plan_id,
    )
    _assert_billing_aliases(result)
    if carrier_id == "rakuten":
        assert result["rakuten_points"] > 0
        assert result["reward_total"] == result["rakuten_points"]
    else:
        assert result["reward_total"] == 0
        assert result["effective_total"] == result["billing_total"]
