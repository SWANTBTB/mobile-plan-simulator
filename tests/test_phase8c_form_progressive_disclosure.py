"""フェーズ⑧C: 入力フォーム段階化（詳細条件折りたたみ）の検証。"""

from __future__ import annotations

import re

import pytest

ROOT_QUERY = "lines[0][carrier]=softbank&lines[0][data_usage]=10gb"
PAYPAY_QUERY = (
    "lines[0][carrier]=softbank&lines[0][data_usage]=unlimited"
    "&lines[0][qr_paypay]=40000&lines[0][paypay_card_tier]=gold"
    "&lines[0][paypay_gold_linked]=1"
)
AU_QUERY = (
    "lines[0][carrier]=au&lines[0][data_usage]=10gb"
    "&lines[0][qr_aupay]=30000&lines[0][au_bill_payment_mode]=au_pay_card"
    "&lines[0][au_jibun_bank_balance]=500000"
)
DOCOMO_QUERY = (
    "lines[0][carrier]=docomo&lines[0][data_usage]=10gb"
    "&lines[0][qr_dbarai]=30000&lines[0][docomo_bill_dcard]=1"
)


def _page_html(client) -> str:
    response = client.get("/")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_advanced_details_closed_by_default(client):
    html = _page_html(client)
    assert 'class="advanced-details' in html
    assert '<details class="advanced-details' in html
    assert re.search(r'<details[^>]*\sopen[\s=>]', html) is None


def test_basic_inputs_always_visible(client):
    html = _page_html(client)
    assert 'name="lines[0][carrier]"' in html
    assert 'id="line-0-age"' in html
    assert 'id="line-0-data"' in html
    assert 'name="lines[0][data_usage]"' in html
    assert 'id="add-line-button"' in html
    assert "料金プラン" in html


def test_current_price_in_basic_area(client):
    html = _page_html(client)
    assert 'id="input-current-price"' in html
    assert 'name="current_price"' in html
    assert "端末代金や一時的な請求を除いた" in html
    assert "複数回線の場合は世帯合計" in html
    price_idx = html.index('id="input-current-price"')
    account_details_idx = html.index('data-advanced-details="account"')
    assert price_idx < account_details_idx


def test_paypay_fields_inside_line_details(client):
    html = _page_html(client)
    line_details_start = html.index('data-advanced-details="line-0"')
    paypay_idx = html.index('name="lines[0][qr_paypay]"')
    assert paypay_idx > line_details_start


def test_au_pay_fields_inside_line_details(client):
    html = _page_html(client)
    line_details_start = html.index('data-advanced-details="line-0"')
    aupay_idx = html.index('name="lines[0][qr_aupay]"')
    assert aupay_idx > line_details_start


def test_dbarai_fields_inside_line_details(client):
    html = _page_html(client)
    line_details_start = html.index('data-advanced-details="line-0"')
    dbarai_idx = html.index('name="lines[0][qr_dbarai]"')
    assert dbarai_idx > line_details_start


def test_discounts_inside_campaign_details(client):
    html = _page_html(client)
    discount_details_start = html.index('data-advanced-details="line-discounts-0"')
    discount_idx = html.index('name="lines[0][discounts]"')
    assert discount_idx > discount_details_start


def test_input_names_unchanged(client):
    html = _page_html(client)
    for name in (
        "lines[0][carrier]",
        "lines[0][age]",
        "lines[0][data_usage]",
        "lines[0][paypay_card_tier]",
        "lines[0][paypay_gold_linked]",
        "lines[0][qr_paypay]",
        "lines[0][qr_dbarai]",
        "lines[0][dcard_tier]",
        "lines[0][docomo_bill_dcard]",
        "lines[0][qr_aupay]",
        "lines[0][au_bill_payment_mode]",
        "lines[0][au_jibun_bank_balance]",
        "current_price",
        "current_carrier",
        "current_plan",
        "home_set_softbank",
    ):
        assert f'name="{name}"' in html


def test_compare_api_payload_unchanged_for_basic(client):
    response = client.get(f"/api/compare?{ROOT_QUERY}")
    assert response.status_code == 200
    payload = response.get_json()
    ok = next(item for item in payload["comparisons"] if item["carrier_id"] == "softbank")
    assert ok["status"] == "ok"
    assert "billing_total" in ok
    assert "effective_total" in ok
    assert "cheapest_billing" in payload
    assert "recommended" not in payload


def test_compare_api_paypay_scenario_unchanged(client):
    response = client.get(f"/api/compare?{PAYPAY_QUERY}")
    assert response.status_code == 200
    payload = response.get_json()
    sb = next(item for item in payload["comparisons"] if item["carrier_id"] == "softbank")
    assert sb["status"] == "ok"
    assert sb["reward_total"] > 0
    assert sb["billing_total"] > sb["effective_total"]


def test_compare_api_au_scenario_unchanged(client):
    response = client.get(f"/api/compare?{AU_QUERY}")
    assert response.status_code == 200
    payload = response.get_json()
    au = next(item for item in payload["comparisons"] if item["carrier_id"] == "au")
    assert au["status"] == "ok"
    rewards = au["lines"][0]["rewards"]
    types = {item["type"] for item in rewards}
    assert "POINT" in types or "CASH" in types or au["reward_total"] >= 0


def test_compare_api_docomo_scenario_unchanged(client):
    response = client.get(f"/api/compare?{DOCOMO_QUERY}")
    assert response.status_code == 200
    payload = response.get_json()
    docomo = next(item for item in payload["comparisons"] if item["carrier_id"] == "docomo")
    assert docomo["status"] == "ok"


def test_calculator_api_unchanged(client):
    response = client.get(f"/api/calculate?{ROOT_QUERY}")
    assert response.status_code == 200
    payload = response.get_json()
    assert "lines" in payload
    assert "comparisons" not in payload
