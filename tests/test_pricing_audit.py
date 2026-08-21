"""2026-08-21 公式料金監査に基づく代表ケース（手計算期待値）。"""

from services.calculator import calculate_multi_carrier_lines


def _line(carrier, plan, discounts=None, **kwargs):
    payload = {
        "carrier": carrier,
        "plan": plan,
        "discounts": discounts or [],
    }
    payload.update(kwargs)
    return payload


def test_audit_softbank_teigaku_family_card():
    result = calculate_multi_carrier_lines(
        [
            _line("softbank", "teigaku_unlimited", ["family_discount", "paypay_card"]),
            _line("softbank", "teigaku_unlimited", ["family_discount", "paypay_card"]),
        ]
    )
    line = result["lines"][0]
    assert line["base_price"] == 8008
    assert line["total"] == 7018  # 8008 - 660 - 330


def test_audit_ymobile_simple3_m_family_second_line():
    result = calculate_multi_carrier_lines(
        [
            _line("ymobile", "simple3_m", []),
            _line("ymobile", "simple3_m", ["family_discount"]),
        ]
    )
    discounted = result["lines"][1]
    assert discounted["base_price"] == 4378
    assert discounted["total"] == 3278  # 4378 - 1100


def test_audit_docomo_max_unlimited_family_three_lines():
    result = calculate_multi_carrier_lines(
        [
            _line("docomo", "docomo_max_unlimited", ["everyone_docomo"]),
            _line("docomo", "docomo_max_unlimited", ["everyone_docomo"]),
            _line("docomo", "docomo_max_unlimited", ["everyone_docomo"]),
        ]
    )
    line = result["lines"][0]
    assert line["base_price"] == 8448
    assert line["total"] == 7238  # 8448 - 1210


def test_audit_au_u18_3gb_family_three_lines():
    result = calculate_multi_carrier_lines(
        [
            _line("au", "au_valuelink", ["family_plus"]),
            _line("au", "au_valuelink", ["family_plus"]),
            _line("au", "u18_value_3gb", ["family_plus"], age="17", data_usage="2"),
        ]
    )
    u18 = next(item for item in result["lines"] if item["plan"]["id"] == "u18_value_3gb")
    assert u18["base_price"] == 2398
    assert u18["total"] == 1848  # 2398 - 550
