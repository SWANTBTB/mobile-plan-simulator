"""フェーズ③ 実装B: au銀行あずけて / Rakuten料金ポイント / docomo計算単位。"""

import pytest

from services.calculator import (
    build_profile,
    build_qr_context,
    calculate_carrier_price,
)


# --- au 銀行あずけて ---


@pytest.mark.parametrize(
    "balance,expected",
    [
        (99_999, 0),
        (100_000, 110),
        (299_999, 110),
        (300_000, 330),
        (499_999, 330),
        (500_000, 550),
    ],
)
def test_au_deposit_cash_tiers(balance, expected):
    result = calculate_carrier_price(
        "au",
        "1",
        [],
        build_profile(),
        plan_id="unlimited_max_moneyact2",
        qr=build_qr_context(au_jibun_bank_balance=str(balance)),
    )

    assert result["deposit_cash"] == expected
    if expected:
        deposit = [item for item in result["rewards"] if item["id"] == "au_deposit_cash"]
        assert len(deposit) == 1
        assert deposit[0]["type"] == "CASH"
        assert deposit[0]["amount"] == expected


def test_au_deposit_and_bill_payment_combined():
    result = calculate_carrier_price(
        "au",
        "1",
        [],
        build_profile(),
        plan_id="unlimited_max_moneyact2",
        qr=build_qr_context(
            au_bill_payment_mode="au_pay_card",
            au_pay_card_bank_is_jibun="1",
            au_jibun_bank_balance="500000",
        ),
    )

    assert result["bill_payment_cash"] == 1650
    assert result["deposit_cash"] == 550
    assert result["reward_total"] == 2200
    assert result["qr_points"] == 0


def test_au_deposit_not_applied_outside_moneyact2():
    result = calculate_carrier_price(
        "au",
        "10",
        [],
        build_profile(),
        plan_id="au_valuelink",
        qr=build_qr_context(au_jibun_bank_balance="500000"),
    )

    assert result["deposit_cash"] == 0


def test_au_legacy_jibun_bank_flag_does_not_trigger_deposit():
    result = calculate_carrier_price(
        "au",
        "1",
        [],
        build_profile(),
        plan_id="unlimited_max_moneyact2",
        qr={"au_jibun_bank": True},
    )

    assert result["deposit_cash"] == 0


# --- Rakuten ---


def test_rakuten_points_saikyo_3gb():
    result = calculate_carrier_price(
        "rakuten",
        "3",
        [],
        build_profile(),
        plan_id="saikyo_3gb",
    )

    assert result["billing_total"] == 1078
    assert result["rakuten_points"] == 9
    assert result["reward_total"] == 9
    assert result["effective_total"] == 1069


def test_rakuten_points_saikyo_20gb():
    result = calculate_carrier_price(
        "rakuten",
        "15",
        [],
        build_profile(),
        plan_id="saikyo_20gb",
    )

    assert result["billing_total"] == 2178
    assert result["rakuten_points"] == 19


def test_rakuten_points_saikyo_unlimited():
    result = calculate_carrier_price(
        "rakuten",
        "30",
        [],
        build_profile(),
        plan_id="saikyo_unlimited",
    )

    assert result["billing_total"] == 3278
    assert result["rakuten_points"] == 29


def test_rakuten_points_use_discounted_billing_total():
    result = calculate_carrier_price(
        "rakuten",
        "30",
        ["family_discount"],
        build_profile(line_count="2"),
        plan_id="saikyo_unlimited",
    )

    assert result["billing_total"] == 3168
    assert result["rakuten_points"] == 28
    assert result["billing_total"] == 3278 - 110


def test_rakuten_billing_total_unchanged_reward_only_increases():
    without = calculate_carrier_price(
        "rakuten",
        "30",
        [],
        build_profile(),
        plan_id="saikyo_unlimited",
    )
    assert without["billing_total"] == 3278
    assert without["reward_total"] == 29


# --- docomo ポイ活MAX 200円単位 ---


def test_docomo_poikatsu_under_200_yen_zero():
    result = calculate_carrier_price(
        "docomo",
        "10",
        [],
        build_profile(),
        plan_id="docomo_poikatsu_max",
        qr=build_qr_context(qr_dbarai="199"),
    )

    assert result["qr_points"] == 0


def test_docomo_poikatsu_exactly_200_yen():
    result = calculate_carrier_price(
        "docomo",
        "10",
        [],
        build_profile(),
        plan_id="docomo_poikatsu_max",
        qr=build_qr_context(qr_dbarai="200", dcard_tier="standard"),
    )

    assert result["qr_points"] == 6


def test_docomo_poikatsu_201_same_as_200():
    at_200 = calculate_carrier_price(
        "docomo",
        "10",
        [],
        build_profile(),
        plan_id="docomo_poikatsu_max",
        qr=build_qr_context(qr_dbarai="200"),
    )
    at_201 = calculate_carrier_price(
        "docomo",
        "10",
        [],
        build_profile(),
        plan_id="docomo_poikatsu_max",
        qr=build_qr_context(qr_dbarai="201"),
    )

    assert at_201["qr_points"] == at_200["qr_points"] == 6


def test_docomo_poikatsu_399_one_unit():
    result = calculate_carrier_price(
        "docomo",
        "10",
        [],
        build_profile(),
        plan_id="docomo_poikatsu_max",
        qr=build_qr_context(qr_dbarai="399", dcard_tier="standard"),
    )

    assert result["qr_points"] == 6


def test_docomo_poikatsu_400_two_units():
    result = calculate_carrier_price(
        "docomo",
        "10",
        [],
        build_profile(),
        plan_id="docomo_poikatsu_max",
        qr=build_qr_context(qr_dbarai="400", dcard_tier="standard"),
    )

    assert result["qr_points"] == 12


def test_docomo_poikatsu_cap_5000():
    result = calculate_carrier_price(
        "docomo",
        "10",
        [],
        build_profile(),
        plan_id="docomo_poikatsu_max",
        qr=build_qr_context(qr_dbarai="500000", dcard_tier="platinum"),
    )

    assert result["qr_points"] == 5000


def test_docomo_poikatsu_card_tier_rates_maintained():
    standard = calculate_carrier_price(
        "docomo",
        "10",
        [],
        build_profile(),
        plan_id="docomo_poikatsu_max",
        qr=build_qr_context(qr_dbarai="10000", dcard_tier="standard"),
    )
    gold = calculate_carrier_price(
        "docomo",
        "10",
        [],
        build_profile(),
        plan_id="docomo_poikatsu_max",
        qr=build_qr_context(qr_dbarai="10000", dcard_tier="gold"),
    )
    platinum = calculate_carrier_price(
        "docomo",
        "10",
        [],
        build_profile(),
        plan_id="docomo_poikatsu_max",
        qr=build_qr_context(qr_dbarai="10000", dcard_tier="platinum"),
    )

    assert standard["qr_points"] == 300
    assert gold["qr_points"] == 500
    assert platinum["qr_points"] == 1000
    poikatsu = [item for item in platinum["rewards"] if item["id"] == "docomo_poikatsu_reward"]
    assert len(poikatsu) == 1


# --- 7ブランド回帰 ---


@pytest.mark.parametrize(
    "carrier_id,plan_id,data_usage,discounts,expected_billing",
    [
        ("softbank", "teigaku_unlimited", "10", [], 8008),
        ("ymobile", "simple3_m", "10", [], 4378),
        ("au", "unlimited_max_plus", "10", [], 7788),
        ("uqmobile", "tokutoku_30gb", "10", [], 4048),
        ("docomo", "docomo_max_unlimited", "10", [], 8448),
        ("ahamo", "ahamo_30gb", "10", [], 2970),
        ("rakuten", "saikyo_unlimited", "10", [], 3278),
    ],
)
def test_seven_carrier_billing_unchanged(carrier_id, plan_id, data_usage, discounts, expected_billing):
    result = calculate_carrier_price(
        carrier_id,
        data_usage,
        discounts,
        build_profile(),
        plan_id=plan_id,
    )

    assert result["billing_total"] == expected_billing
