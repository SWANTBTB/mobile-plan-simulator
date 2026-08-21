"""フェーズ⑥A: 比較結果UIの検証。"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
COMPARE_UI_JS = ROOT / "static" / "js" / "compare-ui.js"


def _sample_entry(**overrides):
    base = {
        "carrier_id": "softbank",
        "carrier_name": "SoftBank",
        "status": "ok",
        "billing_total": 7018,
        "reward_total": 4000,
        "effective_total": 3018,
        "bundled_value": 0,
        "value_adjusted_total": 3018,
        "lines": [
            {
                "plan_name": "ペイトク2",
                "rewards": [
                    {"id": "qr_reward", "type": "POINT", "name": "PayPay還元", "amount": 4000},
                ],
                "applied_discounts": [
                    {"id": "family_discount", "name": "新みんな家族割", "amount": 660},
                ],
                "bundled_services": [],
            }
        ],
        "strengths": [{"rule_id": "sb_paypay_reward", "message": "PayPay利用により4,000pt相当の還元を受けられます"}],
        "cautions": [{"rule_id": "sb_paypay_dependency", "message": "PayPay利用額が減ると実質負担が増える可能性があります"}],
    }
    base.update(overrides)
    return base


def _run_compare_ui_script(script: str) -> str:
    wrapped = f"""
    const fs = require('fs');
    const code = fs.readFileSync({json.dumps(str(COMPARE_UI_JS))}, 'utf8');
    global.window = global;
    eval(code);
    const CompareUI = global.CompareUI;
    {script}
    """
    result = subprocess.run(
        ["node", "-e", wrapped],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"Node.js unavailable or script failed: {result.stderr}")
    return result.stdout.strip()


@pytest.fixture
def node_available():
    try:
        subprocess.run(["node", "-v"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("Node.js not available")


# --- ページ構造 ---


def test_simulator_page_does_not_render_compare_section(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="compare-result-section"' not in html
    assert 'id="compare-carrier-grid"' not in html
    assert 'id="compare-navigate-button"' in html
    assert "compare-ui.js" not in html


def test_compare_page_renders_compare_section(client):
    response = client.get("/compare")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="compare-result-section"' in html
    assert 'id="compare-summary"' in html
    assert 'id="compare-savings"' in html
    assert 'id="compare-carrier-grid"' in html
    assert 'id="compare-conditions-summary"' in html
    assert 'id="compare-edit-button"' in html
    assert "compare-ui.js" in html
    assert "compare-page.js" in html


def test_simulator_page_has_no_recommended_label(client):
    response = client.get("/")
    html = response.get_data(as_text=True)
    assert "おすすめNo.1" not in html
    assert "あなたにおすすめ" not in html


def test_compare_ui_js_declares_amount_fields():
    content = COMPARE_UI_JS.read_text(encoding="utf-8")
    for field in ("billing_total", "reward_total", "effective_total", "value_adjusted_total"):
        assert f'data-compare-field="{field}"' in content


# --- Node: DOM生成 ---


def test_render_carrier_card_includes_four_amount_fields(node_available):
    entry_json = json.dumps(_sample_entry())
    out = _run_compare_ui_script(
        f"""
        const html = CompareUI.renderCarrierCard({entry_json}, {{ billing: null, effective: null, valueAdjusted: null }}, {{}});
        const fields = ['billing_total','reward_total','effective_total'];
        for (const f of fields) {{
          if (!html.includes('data-compare-field="' + f + '"')) process.exit(2);
        }}
        if (!html.includes('7,018円')) process.exit(3);
        if (!html.includes('4,000pt')) process.exit(4);
        if (!html.includes('3,018円相当')) process.exit(5);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_render_carrier_card_point_and_cash_separate(node_available):
    entry = _sample_entry(
        carrier_id="au",
        carrier_name="au",
        lines=[
            {
                "plan_name": "マネ活2",
                "rewards": [
                    {"id": "qr_reward", "type": "POINT", "name": "au PAY還元", "amount": 1500},
                    {"id": "au_bill_payment_cash", "type": "CASH", "name": "通信料お支払い特典", "amount": 1650},
                ],
                "applied_discounts": [],
                "bundled_services": [],
            }
        ],
    )
    entry_json = json.dumps(entry)
    out = _run_compare_ui_script(
        f"""
        const html = CompareUI.renderCarrierCard({entry_json}, {{}}, {{}});
        if (!html.includes('1,500pt')) process.exit(2);
        if (!html.includes('1,650円還元')) process.exit(3);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_render_zero_reward_shows_none(node_available):
    entry_json = json.dumps(_sample_entry(reward_total=0, effective_total=7018, lines=[{"plan_name": "テスト", "rewards": [], "applied_discounts": [], "bundled_services": []}]))
    out = _run_compare_ui_script(
        f"""
        const html = CompareUI.renderCarrierCard({entry_json}, {{}}, {{}});
        if (!html.includes('還元なし')) process.exit(2);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_render_badges_billing_and_effective(node_available):
    entry_json = json.dumps(_sample_entry(carrier_id="rakuten", carrier_name="Rakuten Mobile"))
    out = _run_compare_ui_script(
        f"""
        const html = CompareUI.renderCarrierCard(
          {entry_json},
          {{ billing: {{ carrier_id: 'rakuten' }}, effective: {{ carrier_id: 'softbank' }}, valueAdjusted: null }},
          {{}}
        );
        if (!html.includes('請求額 最安')) process.exit(2);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_render_strengths_and_cautions(node_available):
    entry_json = json.dumps(_sample_entry())
    out = _run_compare_ui_script(
        f"""
        const html = CompareUI.renderCarrierCard({entry_json}, {{}}, {{}});
        if (!html.includes('あなたの条件での強み')) process.exit(2);
        if (!html.includes('注意点')) process.exit(3);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_render_no_cautions_when_empty(node_available):
    entry_json = json.dumps(_sample_entry(cautions=[]))
    out = _run_compare_ui_script(
        f"""
        const html = CompareUI.renderCarrierCard({entry_json}, {{}}, {{}});
        if (html.includes('注意点')) process.exit(2);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_render_error_card_no_eligible_plan(node_available):
    entry_json = json.dumps({"carrier_id": "docomo", "carrier_name": "docomo", "status": "no_eligible_plan"})
    out = _run_compare_ui_script(
        f"""
        const html = CompareUI.renderCarrierCard({entry_json}, {{}}, {{}});
        if (!html.includes('対象プランを算出できませんでした')) process.exit(2);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_summary_combined_when_three_same(node_available):
    payload = {
        "comparison_complete": True,
        "cheapest_billing": {"carrier_id": "rakuten", "carrier_name": "Rakuten Mobile", "plan_id": "saikyo_3gb", "plan_ids": ["saikyo_3gb"], "plan_name": "Rakuten最強プラン", "billing_total": 1078, "effective_total": 1069, "value_adjusted_total": 1069},
        "cheapest_effective": {"carrier_id": "rakuten", "carrier_name": "Rakuten Mobile", "plan_id": "saikyo_3gb", "plan_ids": ["saikyo_3gb"], "plan_name": "Rakuten最強プラン", "billing_total": 1078, "effective_total": 1069, "value_adjusted_total": 1069},
        "cheapest_value_adjusted": {"carrier_id": "rakuten", "carrier_name": "Rakuten Mobile", "plan_id": "saikyo_3gb", "plan_ids": ["saikyo_3gb"], "plan_name": "Rakuten最強プラン", "billing_total": 1078, "effective_total": 1069, "value_adjusted_total": 1069},
    }
    payload_json = json.dumps(payload)
    out = _run_compare_ui_script(
        f"""
        const html = CompareUI.renderSummarySplit(
          {{
            billing: {json.dumps(payload['cheapest_billing'])},
            effective: {json.dumps(payload['cheapest_effective'])},
            valueAdjusted: {json.dumps(payload['cheapest_value_adjusted'])},
          }},
          true
        );
        if (!html.includes('すべて最安')) process.exit(2);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_summary_split_when_different(node_available):
    out = _run_compare_ui_script(
        """
        const html = CompareUI.renderSummarySplit({
          billing: { carrier_id: 'rakuten', carrier_name: 'Rakuten Mobile', billing_total: 3168, effective_total: 3140, value_adjusted_total: 3140 },
          effective: { carrier_id: 'softbank', carrier_name: 'SoftBank', billing_total: 7018, effective_total: 3018, value_adjusted_total: 3018 },
          valueAdjusted: { carrier_id: 'au', carrier_name: 'au', billing_total: 5000, effective_total: 4000, value_adjusted_total: 3452 },
        }, true);
        if (!html.includes('料金だけなら')) process.exit(2);
        if (!html.includes('還元まで含めると')) process.exit(3);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_summary_hidden_when_incomplete(node_available):
    out = _run_compare_ui_script(
        """
        const html = CompareUI.renderSummarySplit({ billing: null, effective: null, valueAdjusted: null }, false);
        if (html !== '') process.exit(2);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_sort_by_effective_total(node_available):
    out = _run_compare_ui_script(
        """
        const sorted = CompareUI.sortComparisons([
          { carrier_id: 'au', status: 'ok', effective_total: 5000, billing_total: 6000 },
          { carrier_id: 'rakuten', status: 'ok', effective_total: 3000, billing_total: 3100 },
        ]);
        if (sorted[0].carrier_id !== 'rakuten') process.exit(2);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_bundled_value_shown_separately(node_available):
    entry_json = json.dumps(
        _sample_entry(
            bundled_value=548,
            value_adjusted_total=2470,
            effective_total=3018,
            lines=[
                {
                    "plan_name": "auバリューリンク",
                    "rewards": [],
                    "applied_discounts": [],
                    "bundled_services": [{"name": "Pontaパス", "monthly_value": 548}],
                }
            ],
        )
    )
    out = _run_compare_ui_script(
        f"""
        const html = CompareUI.renderCarrierCard({entry_json}, {{}}, {{}});
        if (!html.includes('付帯サービス込みの比較額')) process.exit(2);
        if (!html.includes('Pontaパス')) process.exit(3);
        console.log('ok');
        """
    )
    assert out == "ok"


# --- API契約（UI表示に必要なフィールド） ---


def test_compare_api_has_ui_fields(client):
    response = client.get("/api/compare?lines[0][carrier]=softbank&lines[0][data_usage]=10gb")
    assert response.status_code == 200
    payload = response.get_json()
    assert "comparisons" in payload
    assert len(payload["comparisons"]) == 7
    assert "cheapest_billing" in payload
    assert "cheapest_effective" in payload
    assert "cheapest_value_adjusted" in payload
    assert "comparison_complete" in payload
    assert "recommended" not in payload

    ok = next(item for item in payload["comparisons"] if item["status"] == "ok")
    for key in ("billing_total", "reward_total", "effective_total", "value_adjusted_total", "strengths", "cautions", "lines"):
        assert key in ok


def test_compare_api_rakuten_billing_cheapest_at_3gb(client):
    response = client.get("/api/compare?lines[0][data_usage]=3gb")
    payload = response.get_json()
    assert payload["cheapest_billing"]["carrier_id"] == "rakuten"


def test_calculator_and_api_unchanged(client):
    response = client.get("/api/calculate?lines[0][carrier]=softbank&lines[0][data_usage]=10gb")
    assert response.status_code == 200
    assert "comparisons" not in response.get_json()
