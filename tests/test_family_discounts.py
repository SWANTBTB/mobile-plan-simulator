"""7ブランド家族割ロジックの検証テスト。"""

from services.calculator import calculate_carrier_price, calculate_multi_carrier_lines


def _discount_amount(result, discount_id):
    for discount in result["applied_discounts"]:
        if discount["id"] == discount_id:
            return discount["amount"]
    return 0


def _line(carrier, plan, discounts=None, **kwargs):
    payload = {
        "carrier": carrier,
        "age": "40",
        "data_usage": "30",
        "plan": plan,
    }
    if discounts is not None:
        payload["discounts"] = discounts
    payload.update(kwargs)
    return payload


# --- SoftBank ---


def test_sb1_teigaku_one_line_no_discount():
    result = calculate_multi_carrier_lines(
        [_line("softbank", "teigaku_unlimited", ["family_discount"])]
    )
    line = result["lines"][0]
    assert _discount_amount(line, "family_discount") == 0
    assert line["total"] == 8008


def test_sb2_teigaku_two_lines_660_each():
    lines = [_line("softbank", "teigaku_unlimited", ["family_discount"])] * 2
    result = calculate_multi_carrier_lines(lines)
    for line in result["lines"]:
        assert _discount_amount(line, "family_discount") == 660
        assert line["total"] == 7348


def test_sb3_teigaku_three_lines_1210_each():
    lines = [_line("softbank", "teigaku_unlimited", ["family_discount"])] * 3
    result = calculate_multi_carrier_lines(lines)
    for line in result["lines"]:
        assert _discount_amount(line, "family_discount") == 1210
        assert line["total"] == 6798


def test_sb4_minifit_two_lines_220_each():
    lines = [_line("softbank", "minifit2_2gb", ["family_discount"], data_usage="1")] * 2
    result = calculate_multi_carrier_lines(lines)
    for line in result["lines"]:
        assert _discount_amount(line, "family_discount") == 220
        assert line["total"] == 5038


def test_sb5_minifit_three_lines_550_each():
    lines = [_line("softbank", "minifit2_2gb", ["family_discount"], data_usage="1")] * 3
    result = calculate_multi_carrier_lines(lines)
    for line in result["lines"]:
        assert _discount_amount(line, "family_discount") == 550
        assert line["total"] == 4708


def test_sb_primary_line_order_independent():
    lines = [_line("softbank", "teigaku_unlimited", ["family_discount"])] * 2
    forward = calculate_multi_carrier_lines(lines)
    backward = calculate_multi_carrier_lines(list(reversed(lines)))
    assert forward["lines"][0]["total"] == backward["lines"][1]["total"] == 7348


def test_cross_sb_ymobile_does_not_count_ymobile_for_softbank():
    result = calculate_multi_carrier_lines(
        [
            _line("softbank", "teigaku_unlimited", ["family_discount"]),
            _line("ymobile", "simple3_m", ["family_discount"]),
        ]
    )
    sb = next(line for line in result["lines"] if line["carrier_id"] == "softbank")
    assert _discount_amount(sb, "family_discount") == 0
    assert sb["total"] == 8008


# --- Y!mobile ---


def test_ym1_one_line_no_discount():
    result = calculate_multi_carrier_lines(
        [_line("ymobile", "simple3_m", ["family_discount"], data_usage="10")]
    )
    line = result["lines"][0]
    assert _discount_amount(line, "family_discount") == 0
    assert line["total"] == 4378


def test_ym2_primary_no_discount_secondary_1100():
    result = calculate_multi_carrier_lines(
        [
            _line("ymobile", "simple3_m", ["family_discount"], data_usage="10"),
            _line("ymobile", "simple3_m", ["family_discount"], data_usage="10"),
        ]
    )
    primary, secondary = result["lines"]
    assert primary["carrier_line_index"] == 0
    assert _discount_amount(primary, "family_discount") == 0
    assert primary["total"] == 4378
    assert _discount_amount(secondary, "family_discount") == 1100
    assert secondary["total"] == 3278


def test_ym3_three_lines_primary_zero_secondary_1100():
    lines = [_line("ymobile", "simple3_s", ["family_discount"], data_usage="3")] * 3
    result = calculate_multi_carrier_lines(lines)
    primary, second, third = result["lines"]
    assert _discount_amount(primary, "family_discount") == 0
    assert _discount_amount(second, "family_discount") == 1100
    assert _discount_amount(third, "family_discount") == 1100


# --- au ---


def test_au1_valuelink_two_lines_660_each():
    lines = [_line("au", "au_valuelink", ["family_plus"])] * 2
    result = calculate_multi_carrier_lines(lines)
    for line in result["lines"]:
        assert _discount_amount(line, "family_plus") == 660
        assert line["total"] == 7348


def test_au2_valuelink_three_lines_1210_each():
    lines = [_line("au", "au_valuelink", ["family_plus"])] * 3
    result = calculate_multi_carrier_lines(lines)
    for line in result["lines"]:
        assert _discount_amount(line, "family_plus") == 1210
        assert line["total"] == 6798


def test_au3_moneyact2_counts_only_no_discount():
    result = calculate_multi_carrier_lines(
        [
            _line("au", "au_valuelink", ["family_plus"]),
            _line("au", "au_valuelink", ["family_plus"]),
            _line("au", "au_valuelink_moneyact2", ["family_plus"]),
        ]
    )
    standard = [line for line in result["lines"] if line["plan"]["id"] == "au_valuelink"]
    moneyact = next(line for line in result["lines"] if line["plan"]["id"] == "au_valuelink_moneyact2")
    assert len(standard) == 2
    for line in standard:
        assert _discount_amount(line, "family_plus") == 1210
    assert _discount_amount(moneyact, "family_plus") == 0
    assert moneyact["total"] == 9328


def test_au4_u18_uses_plan_specific_tiers():
    result = calculate_multi_carrier_lines(
        [
            _line("au", "au_valuelink", ["family_plus"]),
            _line("au", "au_valuelink", ["family_plus"]),
            _line("au", "u18_value_3gb", ["family_plus"], age="17", data_usage="2"),
        ]
    )
    standard = [line for line in result["lines"] if line["plan"]["id"] == "au_valuelink"]
    u18 = next(line for line in result["lines"] if line["plan"]["id"] == "u18_value_3gb")
    for line in standard:
        assert _discount_amount(line, "family_plus") == 1210
    assert _discount_amount(u18, "family_plus") == 550
    assert u18["total"] == 1848


def test_au5_u12_excluded_from_family_plus_count():
    result = calculate_multi_carrier_lines(
        [
            _line("au", "au_valuelink", ["family_plus"]),
            _line("au", "au_valuelink", ["family_plus"]),
            _line("au", "u12_value", ["family_plus"], age="10", data_usage="1"),
        ]
    )
    standard = [line for line in result["lines"] if line["plan"]["id"] == "au_valuelink"]
    u12 = next(line for line in result["lines"] if line["plan"]["id"] == "u12_value")
    for line in standard:
        assert _discount_amount(line, "family_plus") == 660
    assert _discount_amount(u12, "family_plus") == 0


def test_cross_au_uq_does_not_auto_count():
    result = calculate_multi_carrier_lines(
        [
            _line("au", "au_valuelink", ["family_plus"]),
            _line("uqmobile", "tokutoku_30gb", ["family_set"], data_usage="10"),
        ]
    )
    au_line = next(line for line in result["lines"] if line["carrier_id"] == "au")
    assert _discount_amount(au_line, "family_plus") == 0
    assert au_line["total"] == 8008


# --- UQ ---


def test_uq1_tokutoku_two_lines_550_each():
    lines = [_line("uqmobile", "tokutoku_30gb", ["family_set"], data_usage="10")] * 2
    result = calculate_multi_carrier_lines(lines)
    for line in result["lines"]:
        assert _discount_amount(line, "family_set") == 550
        assert line["total"] == 3498


def test_uq2_komikomi_counts_only():
    result = calculate_multi_carrier_lines(
        [
            _line("uqmobile", "tokutoku_30gb", ["family_set"], data_usage="10"),
            _line("uqmobile", "komikomi_value", ["family_set"], data_usage="20"),
        ]
    )
    tokutoku = next(line for line in result["lines"] if line["plan"]["id"] == "tokutoku_30gb")
    komikomi = next(line for line in result["lines"] if line["plan"]["id"] == "komikomi_value")
    assert _discount_amount(tokutoku, "family_set") == 550
    assert _discount_amount(komikomi, "family_set") == 0
    assert komikomi["total"] == 3828


def test_uq3_home_set_exclusive_with_family_set():
    result = calculate_multi_carrier_lines(
        [
            _line("uqmobile", "tokutoku_30gb", ["home_set", "family_set"], data_usage="10"),
            _line("uqmobile", "tokutoku_30gb", ["home_set", "family_set"], data_usage="10"),
        ],
        home_set_flags={"au": True},
    )
    for line in result["lines"]:
        assert _discount_amount(line, "home_set") == 1100
        assert _discount_amount(line, "family_set") == 0


# --- Rakuten ---


def test_r1_rakuten_two_lines_110_each():
    lines = [_line("rakuten", "saikyo_unlimited", ["family_discount"], data_usage="30")] * 2
    result = calculate_multi_carrier_lines(lines)
    for line in result["lines"]:
        assert _discount_amount(line, "family_discount") == 110
        assert line["total"] == 3168


def test_r2_rakuten_three_lines_110_each():
    lines = [_line("rakuten", "saikyo_unlimited", ["family_discount"], data_usage="30")] * 3
    result = calculate_multi_carrier_lines(lines)
    for line in result["lines"]:
        assert _discount_amount(line, "family_discount") == 110


def test_rakuten_primary_line_gets_discount():
    lines = [_line("rakuten", "saikyo_unlimited", ["family_discount"], data_usage="30")] * 2
    result = calculate_multi_carrier_lines(lines)
    assert result["lines"][0]["is_main_line"] is True
    assert _discount_amount(result["lines"][0], "family_discount") == 110


# --- Regression ---


def test_no_family_discount_unchanged_totals():
    baseline = calculate_multi_carrier_lines(
        [
            _line("softbank", "teigaku_unlimited"),
            _line("au", "au_valuelink"),
            _line("docomo", "docomo_max_unlimited"),
        ]
    )
    assert baseline["totals"]["total"] == 8008 + 8008 + 8448

    with_card = calculate_carrier_price(
        "softbank",
        "30",
        ["paypay_card"],
        {"age": None, "line_count": None},
        plan_id="teigaku_unlimited",
    )
    assert with_card["total"] == 7678
