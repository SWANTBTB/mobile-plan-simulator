import pytest

from services.calculator import (
    InvalidUsageError,
    build_family_discount_ids,
    build_profile,
    build_qr_context,
    build_simulator_ui_config,
    calculate_carrier_lines,
    calculate_carrier_price,
    compare_carriers,
    infer_home_set_flags,
    is_checked_flag,
    merge_home_set_discounts,
    normalize_paypay_card_tier,
    resolve_current_plan,
    resolve_selected_plan,
    select_plan_for_usage,
)
from services.data_loader import get_carrier_map


def test_is_checked_flag():
    assert is_checked_flag("1") is True
    assert is_checked_flag("on") is True
    assert is_checked_flag("true") is True
    assert is_checked_flag("0") is False
    assert is_checked_flag(None) is False


def test_merge_home_set_discounts_adds_mapped_discounts():
    flags = {"softbank": True, "au": False, "docomo": False}
    merged = merge_home_set_discounts({}, flags, ["softbank", "ymobile", "au"])

    assert merged["softbank"] == ["home_fiber_set"]
    assert merged["ymobile"] == ["hikari_set"]
    assert merged["au"] == []


def test_merge_home_set_discounts_preserves_existing_discounts():
    flags = {"softbank": False, "au": True, "docomo": False}
    merged = merge_home_set_discounts(
        {"uqmobile": ["au_pay_card"]},
        flags,
        ["uqmobile", "au"],
    )

    assert merged["uqmobile"] == ["au_pay_card", "home_set"]
    assert merged["au"] == ["smart_value"]


def test_infer_home_set_flags_requires_all_scoped_discounts():
    flags = infer_home_set_flags(
        {"softbank": ["home_fiber_set"], "ymobile": ["hikari_set"]},
        ["softbank", "ymobile", "au"],
    )
    assert flags["softbank"] is True
    assert flags["au"] is False

    partial = infer_home_set_flags(
        {"ymobile": ["hikari_set"]},
        ["softbank", "ymobile"],
    )
    assert partial["softbank"] is False


def test_au_family_plus_uses_660_for_two_lines():
    profile = build_profile(line_count="2")
    result = calculate_carrier_price(
        "au",
        "30",
        ["family_plus"],
        profile,
        plan_id="unlimited_max_plus",
    )

    assert result["total"] == 7128
    assert result["resolved_discount_amounts"]["family_plus"] == 660
    applied = {item["id"]: item["amount"] for item in result["applied_discounts"]}
    assert applied["family_plus"] == 660


def test_au_family_plus_uses_1210_for_three_lines():
    profile = build_profile(line_count="3")
    result = calculate_carrier_price(
        "au",
        "30",
        ["family_plus"],
        profile,
        plan_id="unlimited_max_plus",
    )

    assert result["total"] == 6578
    assert result["resolved_discount_amounts"]["family_plus"] == 1210


def test_docomo_family_discount_uses_line_tiers():
    profile = build_profile(line_count="2")
    result = calculate_carrier_price(
        "docomo",
        "10",
        ["everyone_docomo"],
        profile,
        plan_id="docomo_max_3gb",
    )

    assert result["total"] == 6248
    assert result["resolved_discount_amounts"]["everyone_docomo"] == 550


def _docomo_max_line(**overrides):
    line = {
        "carrier": "docomo",
        "age": "40",
        "data_usage": "30",
        "plan": "docomo_max_unlimited",
        "discounts": ["everyone_docomo"],
    }
    line.update(overrides)
    return line


def _everyone_docomo_amount(result):
    for discount in result["applied_discounts"]:
        if discount["id"] == "everyone_docomo":
            return discount["amount"]
    return 0


def test_docomo_everyone_docomo_one_max_line_no_discount():
    from services.calculator import calculate_multi_carrier_lines

    result = calculate_multi_carrier_lines([_docomo_max_line()])
    line = result["lines"][0]

    assert _everyone_docomo_amount(line) == 0
    assert line["total"] == 8448


def test_docomo_everyone_docomo_two_max_lines_550_each():
    from services.calculator import calculate_multi_carrier_lines

    result = calculate_multi_carrier_lines([_docomo_max_line(), _docomo_max_line()])
    first, second = result["lines"]

    assert _everyone_docomo_amount(first) == 550
    assert _everyone_docomo_amount(second) == 550
    assert first["total"] == 7898
    assert second["total"] == 7898


def test_docomo_everyone_docomo_three_max_lines_1210_each():
    from services.calculator import calculate_multi_carrier_lines

    lines = [_docomo_max_line(), _docomo_max_line(), _docomo_max_line()]
    result = calculate_multi_carrier_lines(lines)

    for line in result["lines"]:
        assert _everyone_docomo_amount(line) == 1210
        assert line["total"] == 7238


def test_docomo_everyone_docomo_two_max_plus_ahamo_1210_on_max_only():
    from services.calculator import calculate_multi_carrier_lines

    ahamo_line = {
        "carrier": "ahamo",
        "age": "40",
        "data_usage": "20",
        "plan": "ahamo_30gb",
    }
    result = calculate_multi_carrier_lines(
        [_docomo_max_line(), _docomo_max_line(), ahamo_line],
    )
    docomo_lines = [line for line in result["lines"] if line["carrier_id"] == "docomo"]
    ahamo = next(line for line in result["lines"] if line["carrier_id"] == "ahamo")

    assert len(docomo_lines) == 2
    for line in docomo_lines:
        assert _everyone_docomo_amount(line) == 1210
        assert line["total"] == 7238
    assert _everyone_docomo_amount(ahamo) == 0
    assert ahamo["total"] == 2970


def test_docomo_everyone_docomo_max_plus_ahamo_550_on_max_only():
    from services.calculator import calculate_multi_carrier_lines

    ahamo_line = {
        "carrier": "ahamo",
        "age": "40",
        "data_usage": "20",
        "plan": "ahamo_30gb",
    }
    result = calculate_multi_carrier_lines([_docomo_max_line(), ahamo_line])
    docomo = next(line for line in result["lines"] if line["carrier_id"] == "docomo")
    ahamo = next(line for line in result["lines"] if line["carrier_id"] == "ahamo")

    assert _everyone_docomo_amount(docomo) == 550
    assert docomo["total"] == 7898
    assert _everyone_docomo_amount(ahamo) == 0
    assert ahamo["total"] == 2970


def test_docomo_everyone_docomo_max_plus_mini_550_on_max_only():
    from services.calculator import calculate_multi_carrier_lines

    mini_line = {
        "carrier": "docomo",
        "age": "40",
        "data_usage": "3",
        "plan": "docomo_mini",
        "discounts": ["everyone_docomo"],
    }
    result = calculate_multi_carrier_lines([_docomo_max_line(), mini_line])
    max_line = next(line for line in result["lines"] if line["plan"]["id"] == "docomo_max_unlimited")
    mini = next(line for line in result["lines"] if line["plan"]["id"] == "docomo_mini")

    assert _everyone_docomo_amount(max_line) == 550
    assert max_line["total"] == 7898
    assert _everyone_docomo_amount(mini) == 0
    assert mini["total"] == 2750


def test_docomo_everyone_docomo_two_ahamo_lines_no_discount():
    from services.calculator import calculate_multi_carrier_lines

    ahamo_line = {
        "carrier": "ahamo",
        "age": "40",
        "data_usage": "20",
        "plan": "ahamo_30gb",
    }
    result = calculate_multi_carrier_lines([ahamo_line, ahamo_line])

    for line in result["lines"]:
        assert _everyone_docomo_amount(line) == 0
        assert line["total"] == 2970


def test_docomo_everyone_docomo_primary_line_order_independent():
    from services.calculator import calculate_multi_carrier_lines

    ahamo_line = {
        "carrier": "ahamo",
        "age": "40",
        "data_usage": "20",
        "plan": "ahamo_30gb",
    }
    max_first = calculate_multi_carrier_lines([_docomo_max_line(), ahamo_line])
    ahamo_first = calculate_multi_carrier_lines([ahamo_line, _docomo_max_line()])

    max_first_docomo = next(line for line in max_first["lines"] if line["carrier_id"] == "docomo")
    ahamo_first_docomo = next(line for line in ahamo_first["lines"] if line["carrier_id"] == "docomo")

    assert max_first_docomo["total"] == ahamo_first_docomo["total"] == 7898
    assert _everyone_docomo_amount(max_first_docomo) == _everyone_docomo_amount(ahamo_first_docomo) == 550


def test_manual_plan_selection_overrides_auto_plan():
    carrier = get_carrier_map()["au"]
    plan, manual, auto_plan = resolve_selected_plan(carrier, "3", "unlimited_max_plus")

    assert manual is True
    assert plan["id"] == "unlimited_max_plus"
    assert auto_plan["id"] == "smart_mini_plus_3gb"


def test_manual_plan_marks_under_capacity():
    result = calculate_carrier_price(
        "docomo",
        "50",
        [],
        build_profile(),
        plan_id="docomo_max_3gb",
    )

    assert result["plan_manual"] is True
    assert result["plan_under_capacity"] is True
    assert result["plan"]["id"] == "docomo_max_3gb"


def test_uqmobile_family_set_applies_to_primary_line_with_two_lines():
    from services.calculator import calculate_multi_carrier_lines

    line = {
        "carrier": "uqmobile",
        "age": "40",
        "data_usage": "10",
        "plan": "tokutoku_30gb",
        "discounts": ["family_set"],
    }
    comparison = calculate_multi_carrier_lines([line, line])
    main, second = comparison["lines"]

    assert main["total"] == 3498
    assert second["total"] == 3498
    assert any(item["id"] == "family_set" for item in main["applied_discounts"])


def test_uqmobile_home_set_applies_discount():
    result = calculate_carrier_price(
        "uqmobile",
        "3",
        ["home_set"],
        build_profile(),
    )

    assert result["total"] == 1848
    assert any(item["id"] == "home_set" for item in result["applied_discounts"])


def test_uqmobile_home_set_and_family_set_are_exclusive():
    result = calculate_carrier_price(
        "uqmobile",
        "3",
        ["home_set", "family_set"],
        build_profile(line_count="2"),
    )

    applied_ids = {item["id"] for item in result["applied_discounts"]}
    assert applied_ids == {"auto_discount", "home_set"}


def test_compare_carriers_with_manual_plans_per_carrier():
    comparison = compare_carriers(
        ["au", "docomo"],
        "10",
        {},
        build_profile(),
        plans_by_carrier={
            "au": "unlimited_max_plus",
            "docomo": "docomo_mini",
        },
    )

    by_id = {item["carrier_id"]: item for item in comparison["results"]}
    assert by_id["au"]["plan_manual"] is True
    assert by_id["au"]["plan"]["id"] == "unlimited_max_plus"
    assert by_id["docomo"]["plan_manual"] is True
    assert by_id["docomo"]["plan"]["id"] == "docomo_mini"


def test_invalid_data_usage_raises():
    with pytest.raises(InvalidUsageError):
        calculate_carrier_price("au", "not-a-number")


def test_au_unlimited_applies_1gb_auto_discount():
    result = calculate_carrier_price(
        "au",
        "1",
        [],
        build_profile(),
        plan_id="unlimited_max_plus",
    )

    assert result["total"] == 6138
    assert any(item["id"] == "auto_discount" and item["amount"] == 1650 for item in result["applied_discounts"])


def test_au_unlimited_skips_1gb_auto_discount_above_threshold():
    result = calculate_carrier_price(
        "au",
        "3",
        [],
        build_profile(),
        plan_id="unlimited_max_plus",
    )

    assert result["total"] == 7788
    assert not any(item["id"] == "auto_discount" for item in result["applied_discounts"])


def test_softbank_teigaku_has_no_fixed_paypay_points():
    result = calculate_carrier_price(
        "softbank",
        "unlimited",
        [],
        build_profile(),
        plan_id="teigaku_unlimited",
    )

    assert result["total"] == 8008
    assert result["qr_points"] == 0
    assert result["effective_total"] == 8008
    assert result["plan_quotes"]["teigaku_unlimited"]["effective_total"] == 8008
    assert result["plan_quotes"]["teigaku_unlimited"]["qr_points"] == 0


def test_plan_quotes_reflect_qr_spend_on_paytoku():
    result = calculate_carrier_price(
        "softbank",
        "unlimited",
        [],
        build_profile(),
        plan_id="teigaku_unlimited",
        qr=build_qr_context(qr_paypay="30000", paypay_card_tier="gold", paypay_gold_linked="1"),
    )

    paytoku = result["plan_quotes"]["paytoku2"]
    assert paytoku["qr_points"] == 3000
    assert paytoku["effective_total"] == paytoku["total"] - 3000


def test_normalize_paypay_card_tier_supports_legacy_gold_flag():
    assert normalize_paypay_card_tier(None, "1") == "gold"
    assert normalize_paypay_card_tier("standard", "1") == "standard"
    assert normalize_paypay_card_tier("", None) == ""


def test_softbank_paypay_card_discounts_apply_by_tier():
    normal = calculate_carrier_price(
        "softbank",
        "10",
        ["paypay_card"],
        build_profile(),
        plan_id="teigaku_unlimited",
    )
    gold = calculate_carrier_price(
        "softbank",
        "10",
        ["paypay_card_gold"],
        build_profile(),
        plan_id="teigaku_unlimited",
    )

    assert any(item["id"] == "paypay_card" and item["amount"] == 330 for item in normal["applied_discounts"])
    assert any(item["id"] == "paypay_card_gold" and item["amount"] == 550 for item in gold["applied_discounts"])
    assert gold["total"] < normal["total"]


def test_docomo_denki_set_applies_to_mini():
    result = calculate_carrier_price(
        "docomo",
        "3",
        ["docomo_denki_set"],
        build_profile(),
        plan_id="docomo_mini",
    )

    assert result["total"] == 2640


def test_au_moneyact2_adds_fixed_bonuses():
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

    assert result["total"] == 7458
    assert result["qr_points"] == 0
    assert result["cash_rewards"] == 1650
    assert result["reward_total"] == 1650
    assert result["effective_total"] == 5808


def test_docomo_d_card_uses_tier_amount():
    result = calculate_carrier_price(
        "docomo",
        "10",
        ["d_card"],
        build_profile(),
        plan_id="docomo_max_3gb",
        qr={"dcard_tier": "gold", "spend": {}},
    )

    assert result["total"] == 6248
    assert result["resolved_discount_amounts"]["d_card"] == 550


def test_docomo_mini_campaign_capacity_selects_mini_at_5gb():
    result = calculate_carrier_price("docomo", "5", [], build_profile())

    assert result["plan"]["id"] == "docomo_mini"
    assert result["plan_under_capacity"] is False


def test_softbank_senior_discount():
    result = calculate_carrier_price(
        "softbank",
        "10",
        ["senior_discount"],
        build_profile(age="70"),
        plan_id="teigaku_unlimited",
    )

    assert result["total"] == 7788


def test_ymobile_senior_discount_on_simple3_s():
    result = calculate_carrier_price(
        "ymobile",
        "3",
        ["senior_discount"],
        build_profile(age="70"),
    )

    assert result["plan"]["id"] == "simple3_s"
    assert result["total"] == 2728


def test_rakuten_child_discount():
    result = calculate_carrier_price(
        "rakuten",
        "2",
        ["child_discount"],
        build_profile(age="10"),
    )

    assert result["total"] == 968


def test_ymobile_special_discount_in_campaign_period():
    result = calculate_carrier_price(
        "ymobile",
        "3",
        ["special_discount"],
        build_profile(),
    )

    assert result["total"] == 3058


def test_au_valuelink_includes_ponta_pass_value():
    result = calculate_carrier_price(
        "au",
        "10",
        [],
        build_profile(),
        plan_id="au_valuelink",
    )

    assert result["bundled_value"] == 548
    assert result["value_adjusted_total"] == result["effective_total"] - 548


def test_build_simulator_ui_config_matches_carrier_json():
    config = build_simulator_ui_config()
    au = next(carrier for carrier in config["carriers"] if carrier["id"] == "au")
    assert au["plan_comparison_notes"]["title"]
    assert len(au["plan_comparison_notes"]["rows"]) >= 2
    assert config["home_set_groups"]["docomo_denki"]["discounts"]["docomo"] == "docomo_denki_set"
    assert "hikari_set" in config["exclusive_discounts"]["ymobile"]
    assert "family_discount" in config["exclusive_discounts"]["ymobile"]["hikari_set"]
    assert config["carrier_ui"]["ahamo"]["qr_section"] is False
    assert config["carrier_ui"]["docomo"]["tenure_years"] is True
    assert config["carrier_ui"]["au"]["qr_aupay"] is True
    assert len(config["carriers"]) >= 7
    assert config["pricing_as_of_label"] == "2026年8月21日時点の料金"
    assert "docomo_hikari_set" in config["manual_opt_in_discount_ids"]
    assert "paypay_card" in config["manual_opt_in_discount_ids"]
    assert "family_plus" not in config["manual_opt_in_discount_ids"]
    assert "family_discount" not in config["family_discount_primary_blocked"].get("softbank", [])
    assert "family_plus" not in config["family_discount_primary_blocked"].get("au", [])
    assert "family_set" not in config["family_discount_primary_blocked"].get("uqmobile", [])
    assert "everyone_docomo" not in config["family_discount_primary_blocked"].get("docomo", [])
    assert "family_discount" in config["family_discount_ids"]["softbank"]
    assert "family_plus" in config["family_discount_ids"]["au"]


def test_build_carrier_ui_visibility_for_softbank():
    config = build_simulator_ui_config()
    ui = config["carrier_ui"]["softbank"]
    assert ui["home_set_softbank"] is True
    assert ui["qr_paypay"] is True
    assert ui["paypay_card_section"] is True
    assert ui["qr_aupay"] is False


def test_build_carrier_ui_visibility_for_ymobile():
    config = build_simulator_ui_config()
    ui = config["carrier_ui"]["ymobile"]
    assert ui["paypay_card_section"] is True
    assert ui["qr_paypay"] is False
    assert ui["qr_section"] is False


def test_ymobile_paypay_card_discounts_apply_by_tier():
    result = calculate_carrier_price(
        "ymobile",
        "10",
        ["paypay_card_gold"],
        build_profile(),
        plan_id="simple3_m",
    )

    assert any(item["id"] == "paypay_card_gold" and item["amount"] == 550 for item in result["applied_discounts"])


def test_select_plan_for_usage_falls_back_to_largest_capped_plan():
    carrier = {
        "id": "sample",
        "plans": [
            {"id": "small", "data_gb_max": 3, "base_price": 1000, "priority": 1},
            {"id": "large", "data_gb_max": 10, "base_price": 2000, "priority": 2},
        ],
    }

    plan = select_plan_for_usage(carrier, None)

    assert plan["id"] == "large"


def test_docomo_long_term_requires_tenure():
    without = calculate_carrier_price(
        "docomo",
        "10",
        ["long_term"],
        build_profile(),
        plan_id="docomo_max_3gb",
    )
    with_tenure = calculate_carrier_price(
        "docomo",
        "10",
        ["long_term"],
        build_profile(tenure_years="10"),
        plan_id="docomo_max_3gb",
    )

    assert without["total"] == 6798
    assert with_tenure["total"] == 6578
    assert with_tenure["resolved_discount_amounts"]["long_term"] == 220


def test_docomo_long_term_auto_applied_when_tenure_met():
    result = calculate_carrier_price(
        "docomo",
        "10",
        [],
        build_profile(tenure_years="12"),
        plan_id="docomo_max_3gb",
    )

    assert result["total"] == 6578
    assert any(item["id"] == "long_term" for item in result["applied_discounts"])


def test_uq_komikomi_value_includes_ponta_pass():
    result = calculate_carrier_price(
        "uqmobile",
        "20",
        [],
        build_profile(),
        plan_id="komikomi_value",
    )

    assert result["bundled_value"] == 548
    assert result["value_adjusted_total"] == result["effective_total"] - 548


def test_resolve_current_plan_prefers_manual_price():
    current = resolve_current_plan("au", "unlimited_max_plus", "5000")

    assert current["monthly"] == 5000
    assert current["billing_total"] == 5000
    assert current["source"] == "user_reported"
    assert current["is_manual_price"] is True
    assert current["plan_name"] == "使い放題MAX＋ 5G/4G"


def test_resolve_current_plan_accepts_legacy_plan():
    current = resolve_current_plan("uqmobile", "komikomi")

    assert current["monthly"] == 3278
    assert current["billing_total"] == 3278
    assert current["source"] == "estimated_plan_base"
    assert current["plan_name"] == "コミコミプラン"


def test_resolve_current_plan_unknown_carrier_raises():
    with pytest.raises(InvalidUsageError, match="unknown carrier"):
        resolve_current_plan("unknown", None, "5000")


def test_calculate_carrier_lines_applies_family_discount_on_main_line_for_au():
    comparison = calculate_carrier_lines(
        "au",
        [
            {
                "age": "40",
                "data_usage": "30",
                "plan": "unlimited_max_plus",
                "discounts": ["family_plus"],
            },
            {
                "age": "40",
                "data_usage": "10",
                "plan": "unlimited_max_plus",
                "discounts": ["family_plus"],
            },
        ],
    )

    main, second = comparison["lines"]
    assert main["total"] == 7128
    assert second["total"] == 7128
    assert comparison["totals"]["value_adjusted_total"] == main["value_adjusted_total"] + second["value_adjusted_total"]
    assert comparison["totals"]["line_count"] == 2


def test_build_family_discount_ids_includes_au_family_plus():
    ids = build_family_discount_ids()
    assert "family_plus" in ids["au"]
    assert "everyone_docomo" in ids["docomo"]


def test_softbank_family_discount_applies_to_primary_line_with_three_lines():
    from services.calculator import calculate_multi_carrier_lines

    line = {
        "carrier": "softbank",
        "age": "40",
        "data_usage": "30",
        "plan": "teigaku_unlimited",
        "discounts": ["family_discount"],
    }
    comparison = calculate_multi_carrier_lines([line, line, line])
    main, second, third = comparison["lines"]

    assert main["total"] == 6798
    assert second["total"] == 6798
    assert third["total"] == 6798
    assert all(
        any(item["id"] == "family_discount" for item in result["applied_discounts"])
        for result in comparison["lines"]
    )


def test_ymobile_family_discount_blocked_on_first_ymobile_line_in_mixed_carriers():
    from services.calculator import calculate_multi_carrier_lines

    comparison = calculate_multi_carrier_lines(
        [
            {
                "carrier": "softbank",
                "age": "40",
                "data_usage": "30",
                "plan": "teigaku_unlimited",
            },
            {
                "carrier": "ymobile",
                "age": "40",
                "data_usage": "30",
                "plan": "simple3_m",
                "discounts": ["family_discount"],
            },
            {
                "carrier": "ymobile",
                "age": "40",
                "data_usage": "30",
                "plan": "simple3_m",
                "discounts": ["family_discount"],
            },
        ],
    )

    _, first_ymobile, second_ymobile = comparison["lines"]
    assert first_ymobile["carrier_line_index"] == 0
    assert second_ymobile["carrier_line_index"] == 1
    assert not any(item["id"] == "family_discount" for item in first_ymobile["applied_discounts"])
    assert first_ymobile["total"] == 4378
    assert any(item["id"] == "family_discount" for item in second_ymobile["applied_discounts"])
    assert second_ymobile["total"] == 3278


def test_calculate_multi_carrier_lines_mixed_carriers():
    from services.calculator import calculate_multi_carrier_lines

    comparison = calculate_multi_carrier_lines(
        [
            {
                "carrier": "au",
                "age": "40",
                "data_usage": "10",
                "plan": "unlimited_max_plus",
            },
            {
                "carrier": "docomo",
                "age": "40",
                "data_usage": "10",
                "plan": "docomo_max_3gb",
            },
        ],
    )

    au_line, docomo_line = comparison["lines"]
    assert au_line["carrier_id"] == "au"
    assert docomo_line["carrier_id"] == "docomo"
    assert comparison["carrier_ids"] == ["au", "docomo"] or set(comparison["carrier_ids"]) == {"au", "docomo"}
    assert comparison["totals"]["value_adjusted_total"] == (
        au_line["value_adjusted_total"] + docomo_line["value_adjusted_total"]
    )
