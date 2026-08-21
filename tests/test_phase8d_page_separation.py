"""フェーズ⑧D: 入力ページ / 7社比較ページ分離の検証。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SIMULATOR_JS = ROOT / "static" / "js" / "simulator.js"
COMPARE_PAGE_JS = ROOT / "static" / "js" / "compare-page.js"
SIMULATOR_STATE_JS = ROOT / "static" / "js" / "simulator-state.js"

BASIC_QUERY = "lines[0][carrier]=softbank&lines[0][data_usage]=3gb"
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
MULTI_LINE_QUERY = (
    "lines[0][carrier]=softbank&lines[0][age]=23&lines[0][data_usage]=30"
    "&lines[1][carrier]=au&lines[1][age]=40&lines[1][data_usage]=10"
    "&current_price=8500"
)


def test_compare_route_exists(client):
    response = client.get("/compare")
    assert response.status_code == 200
    assert "7社比較結果" in response.get_data(as_text=True)


def test_input_page_has_compare_cta_without_compare_dom(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="compare-navigate-button"' in html
    assert "7社を比較する" in html
    assert 'id="compare-result-section"' not in html
    assert "compare-ui.js" not in html
    assert "simulator-state.js" in html


def test_compare_page_has_result_dom_and_edit_button(client):
    html = client.get("/compare").get_data(as_text=True)
    assert 'id="compare-result-section"' in html
    assert 'id="compare-conditions-summary"' in html
    assert 'id="compare-edit-button"' in html
    assert 'id="compare-empty-state"' in html
    assert "条件を変更する" in html


def test_compare_page_direct_access_shows_empty_state(client):
    html = client.get("/compare").get_data(as_text=True)
    assert "比較条件がありません" in html
    assert "条件を入力する" in html


def test_simulator_js_does_not_auto_fetch_compare():
    content = SIMULATOR_JS.read_text(encoding="utf-8")
    assert "/api/compare" not in content
    assert "bootstrapCompare" not in content
    assert "CompareUI" not in content
    assert "navigateToComparePage" in content


def test_simulator_state_module_exports():
    content = SIMULATOR_STATE_JS.read_text(encoding="utf-8")
    assert "mobile_simulator_compare_input" in content
    assert "saveCompareInput" in content
    assert "loadCompareInput" in content
    assert "buildSimulatorUrlFromStored" in content


def test_compare_page_js_fetches_compare_api():
    content = COMPARE_PAGE_JS.read_text(encoding="utf-8")
    assert "/api/compare?" in content
    assert "compare-conditions-summary" in content
    assert "SimulatorState" in content


@pytest.mark.parametrize(
    "query",
    [BASIC_QUERY, PAYPAY_QUERY, AU_QUERY, DOCOMO_QUERY, MULTI_LINE_QUERY],
)
def test_compare_api_payload_unchanged(client, query):
    response = client.get(f"/api/compare?{query}")
    assert response.status_code == 200
    payload = response.get_json()
    assert "comparisons" in payload
    assert len(payload["comparisons"]) == 7
    assert "cheapest_billing" in payload
    assert "cheapest_effective" in payload
    assert "cheapest_value_adjusted" in payload
    assert "recommended" not in payload


def test_compare_api_paypay_rewards_preserved(client):
    payload = client.get(f"/api/compare?{PAYPAY_QUERY}").get_json()
    sb = next(item for item in payload["comparisons"] if item["carrier_id"] == "softbank")
    assert sb["reward_total"] > 0


def test_compare_api_au_rewards_preserved(client):
    payload = client.get(f"/api/compare?{AU_QUERY}").get_json()
    au = next(item for item in payload["comparisons"] if item["carrier_id"] == "au")
    assert au["status"] == "ok"


def test_compare_api_multi_line_preserved(client):
    payload = client.get(f"/api/compare?{MULTI_LINE_QUERY}").get_json()
    assert payload["comparison_complete"] is True
    assert len(payload["comparisons"]) == 7


def test_calculate_api_unchanged_on_input_page(client):
    response = client.get(f"/api/calculate?{BASIC_QUERY}")
    assert response.status_code == 200
    assert "lines" in response.get_json()
    assert "comparisons" not in response.get_json()


def test_input_page_restores_via_query_string(client):
    response = client.get(f"/?{PAYPAY_QUERY}&current_price=10000")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'value="40000"' in html or "40000" in html
    assert 'value="10000"' in html


def test_compare_page_title(client):
    html = client.get("/compare").get_data(as_text=True)
    assert "<title>7社比較結果 | 料金シミュレーター</title>" in html
