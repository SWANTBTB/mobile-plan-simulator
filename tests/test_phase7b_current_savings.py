"""フェーズ⑦B: 現在契約との billing 差額 API の検証。"""

from __future__ import annotations

import pytest

from app import app as flask_app
from services.calculator import compare_all_carriers_for_lines, resolve_current_plan
from services.current_savings import (
    attach_current_savings_to_compare_result,
    build_current_cost,
    compute_vs_current,
)


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as test_client:
        yield test_client


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


def _compare_api(client, **query):
    return client.get("/api/compare", query_string=query)


def _entry(comparison: dict, carrier_id: str) -> dict:
    return next(item for item in comparison["comparisons"] if item["carrier_id"] == carrier_id)


# --- Unit: compute_vs_current ---


def test_billing_monthly_diff_positive_when_candidate_cheaper():
    vs = compute_vs_current(8500, 3168)
    assert vs == {"billing_monthly_diff": 5332, "billing_annual_diff": 63984}


def test_billing_monthly_diff_negative_when_candidate_higher():
    vs = compute_vs_current(3000, 4000)
    assert vs == {"billing_monthly_diff": -1000, "billing_annual_diff": -12000}


def test_billing_monthly_diff_zero_when_equal():
    vs = compute_vs_current(5000, 5000)
    assert vs == {"billing_monthly_diff": 0, "billing_annual_diff": 0}


def test_vs_current_null_when_current_missing():
    assert compute_vs_current(None, 3168) is None


def test_vs_current_null_when_candidate_missing():
    assert compute_vs_current(8500, None) is None


# --- resolve_current_plan source ---


def test_resolve_current_plan_user_reported_source():
    current = resolve_current_plan("au", "unlimited_max_plus", "8500")
    assert current["billing_total"] == 8500
    assert current["monthly"] == 8500
    assert current["source"] == "user_reported"


def test_resolve_current_plan_estimated_plan_base_source():
    current = resolve_current_plan("uqmobile", "komikomi")
    assert current["source"] == "estimated_plan_base"
    assert current["billing_total"] == current["monthly"] == 3278


def test_resolve_current_plan_unavailable_returns_none():
    assert resolve_current_plan() is None
    assert build_current_cost(None) == {"billing_total": None, "source": "unavailable"}


# --- /api/compare integration ---


def test_api_compare_includes_current_cost_user_reported(client):
    response = _compare_api(
        client,
        **{
            "lines[0][data_usage]": "10gb",
            "current_price": "8500",
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["current_cost"] == {"billing_total": 8500, "source": "user_reported"}


def test_api_compare_vs_current_on_all_comparisons(client):
    response = _compare_api(
        client,
        **{
            "lines[0][data_usage]": "10gb",
            "current_price": "8500",
        },
    )
    payload = response.get_json()
    assert len(payload["comparisons"]) == 7
    for entry in payload["comparisons"]:
        assert "vs_current" in entry
        if entry["status"] == "ok":
            assert entry["vs_current"] is not None
            assert entry["vs_current"]["billing_monthly_diff"] == 8500 - entry["billing_total"]
        else:
            assert entry["vs_current"] is None


def test_api_compare_savings_summary_matches_cheapest_billing(client):
    response = _compare_api(
        client,
        **{
            "lines[0][data_usage]": "10gb",
            "current_price": "8500",
        },
    )
    payload = response.get_json()
    cheapest = payload["cheapest_billing"]
    summary = payload["savings_summary"]

    assert summary is not None
    assert summary["carrier_id"] == cheapest["carrier_id"]
    assert summary["new_billing_total"] == cheapest["billing_total"]
    assert summary["current_billing_total"] == 8500
    assert summary["monthly_saving"] == 8500 - cheapest["billing_total"]
    assert summary["annual_saving"] == summary["monthly_saving"] * 12
    assert summary["source"] == "user_reported"
    assert cheapest["vs_current"]["billing_monthly_diff"] == summary["monthly_saving"]


def test_api_compare_no_savings_when_current_unavailable(client):
    response = _compare_api(client, **{"lines[0][data_usage]": "10gb"})
    payload = response.get_json()

    assert payload["current_cost"] == {"billing_total": None, "source": "unavailable"}
    assert payload["savings_summary"] is None
    assert all(entry["vs_current"] is None for entry in payload["comparisons"])


def test_api_compare_estimated_plan_base_source(client):
    response = _compare_api(
        client,
        **{
            "lines[0][data_usage]": "10gb",
            "current_carrier": "uqmobile",
            "current_plan": "komikomi",
        },
    )
    payload = response.get_json()
    assert payload["current_cost"]["source"] == "estimated_plan_base"
    assert payload["current_cost"]["billing_total"] == 3278
    assert payload["savings_summary"]["source"] == "estimated_plan_base"


def test_api_compare_user_reported_overrides_plan_base_price(client):
    response = _compare_api(
        client,
        **{
            "lines[0][data_usage]": "10gb",
            "current_carrier": "au",
            "current_plan": "unlimited_max_plus",
            "current_price": "8500",
        },
    )
    payload = response.get_json()
    assert payload["current_cost"] == {"billing_total": 8500, "source": "user_reported"}


def test_api_compare_multi_line_household_current_total(client):
    response = _compare_api(
        client,
        **{
            "lines[0][carrier]": "softbank",
            "lines[0][data_usage]": "10gb",
            "lines[1][carrier]": "au",
            "lines[1][data_usage]": "10gb",
            "current_price": "8500",
        },
    )
    payload = response.get_json()
    rakuten = _entry(payload, "rakuten")
    assert payload["current_cost"]["billing_total"] == 8500
    assert rakuten["vs_current"]["billing_monthly_diff"] == 8500 - rakuten["billing_total"]


def test_api_compare_cheapest_axes_unchanged_by_current_savings(client):
    without = _compare_api(client, **{"lines[0][data_usage]": "10gb"}).get_json()
    with_current = _compare_api(
        client,
        **{"lines[0][data_usage]": "10gb", "current_price": "8500"},
    ).get_json()

    for key in ("cheapest_billing", "cheapest_effective", "cheapest_value_adjusted"):
        assert without[key]["carrier_id"] == with_current[key]["carrier_id"]
        assert without[key]["billing_total"] == with_current[key]["billing_total"]
        assert without[key]["effective_total"] == with_current[key]["effective_total"]
        assert without[key]["value_adjusted_total"] == with_current[key]["value_adjusted_total"]


def test_api_compare_does_not_add_effective_or_value_adjusted_savings(client):
    response = _compare_api(
        client,
        **{"lines[0][data_usage]": "10gb", "current_price": "8500"},
    )
    payload = response.get_json()
    summary = payload["savings_summary"]

    assert "effective_saving" not in summary
    assert "value_adjusted_saving" not in payload
    for entry in payload["comparisons"]:
        if entry["vs_current"]:
            assert set(entry["vs_current"]) == {"billing_monthly_diff", "billing_annual_diff"}


def test_api_calculate_best_saving_unchanged(client):
    query = {
        "lines[0][carrier]": "softbank",
        "lines[0][data_usage]": "30",
        "lines[0][plan]": "teigaku_unlimited",
        "current_carrier": "au",
        "current_price": "10000",
    }
    response = client.get("/api/calculate", query_string=query)
    payload = response.get_json()
    totals = payload["totals"]

    assert payload["best_saving"] == 10000 - totals["value_adjusted_total"]
    assert totals["diff"] == totals["value_adjusted_total"] - 10000


def test_attach_does_not_recalculate_billing_totals():
    comparison = compare_all_carriers_for_lines([_line(data_usage="10gb")])
    before = {
        entry["carrier_id"]: entry["billing_total"]
        for entry in comparison["comparisons"]
        if entry["status"] == "ok"
    }
    attach_current_savings_to_compare_result(
        comparison,
        resolve_current_plan(None, None, "8500"),
    )
    after = {
        entry["carrier_id"]: entry["billing_total"]
        for entry in comparison["comparisons"]
        if entry["status"] == "ok"
    }
    assert before == after
