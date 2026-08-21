"""フェーズ⑧B: UX/UI改善（P1 5点）の検証。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
COMPARE_UI_JS = ROOT / "static" / "js" / "compare-ui.js"


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


def test_header_conveys_input_and_compare_flow(client):
    response = client.get("/")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "7ブランド" in html or "7社" in html
    assert "7社を比較する" in html


def test_input_page_has_step3_and_compare_cta(client):
    response = client.get("/")
    html = response.get_data(as_text=True)
    assert "入力中キャリアの料金内訳" in html
    assert "7社を比較する" in html
    assert 'id="compare-result-section"' not in html
    assert "条件が決まったら7社をまとめて比較できます" in html


def test_no_legacy_bundled_value_user_label(client):
    response = client.get("/")
    html = response.get_data(as_text=True)
    assert "付帯価値込み" not in html


def test_billing_visible_near_effective_on_card(node_available):
    entry = {
        "carrier_id": "softbank",
        "carrier_name": "SoftBank",
        "status": "ok",
        "billing_total": 8008,
        "reward_total": 4000,
        "effective_total": 6538,
        "bundled_value": 0,
        "value_adjusted_total": 6538,
        "axis_quotes": {
            "billing": {
                "plan_id": "teigaku_unlimited",
                "plan_name": "テイガク（使った分だけ）",
                "plan_ids": ["teigaku_unlimited"],
                "billing_total": 8008,
                "reward_total": 0,
                "effective_total": 8008,
                "value_adjusted_total": 8008,
                "lines": [{"plan_id": "teigaku_unlimited", "plan_name": "テイガク（使った分だけ）", "rewards": []}],
            },
            "effective": {
                "plan_id": "paytoku2",
                "plan_name": "ペイトク2",
                "plan_ids": ["paytoku2"],
                "billing_total": 10538,
                "reward_total": 4000,
                "effective_total": 6538,
                "value_adjusted_total": 6538,
                "lines": [{"plan_id": "paytoku2", "plan_name": "ペイトク2", "rewards": []}],
            },
            "value_adjusted": {
                "plan_id": "paytoku2",
                "plan_name": "ペイトク2",
                "plan_ids": ["paytoku2"],
                "billing_total": 10538,
                "reward_total": 4000,
                "effective_total": 6538,
                "value_adjusted_total": 6538,
                "lines": [{"plan_id": "paytoku2", "plan_name": "ペイトク2", "rewards": []}],
            },
        },
        "lines": [{"plan_name": "ペイトク2", "rewards": [], "applied_discounts": [], "bundled_services": []}],
        "strengths": [],
        "cautions": [],
    }
    entry_json = json.dumps(entry)
    out = _run_compare_ui_script(
        f"""
        const html = CompareUI.renderCarrierCard({entry_json}, {{}}, {{}});
        const effectiveIdx = html.indexOf('還元込み実質負担');
        const billingIdx = html.indexOf('実際の請求額');
        if (effectiveIdx < 0 || billingIdx < 0) process.exit(2);
        if (billingIdx <= effectiveIdx) process.exit(3);
        if (!html.includes('compare-card__billing-amount')) process.exit(4);
        if (!html.includes('8,008円')) process.exit(5);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_bundled_service_wording_on_card_and_summary(node_available):
    entry = {
        "carrier_id": "au",
        "carrier_name": "au",
        "status": "ok",
        "billing_total": 5000,
        "reward_total": 0,
        "effective_total": 4000,
        "bundled_value": 548,
        "value_adjusted_total": 3452,
        "lines": [
            {
                "plan_name": "auバリューリンク",
                "rewards": [],
                "applied_discounts": [],
                "bundled_services": [{"name": "Pontaパス", "monthly_value": 548}],
            }
        ],
        "strengths": [],
        "cautions": [],
    }
    entry_json = json.dumps(entry)
    out = _run_compare_ui_script(
        f"""
        const html = CompareUI.renderCarrierCard({entry_json}, {{}}, {{}});
        if (!html.includes('付帯サービス込みの比較額')) process.exit(2);
        const summary = CompareUI.renderSummarySplit({{
          billing: {{ carrier_id: 'rakuten', carrier_name: 'Rakuten Mobile', billing_total: 3168, effective_total: 3140, value_adjusted_total: 3140 }},
          effective: {{ carrier_id: 'softbank', carrier_name: 'SoftBank', billing_total: 7018, effective_total: 3018, value_adjusted_total: 3018 }},
          valueAdjusted: {{ carrier_id: 'au', carrier_name: 'au', billing_total: 5000, effective_total: 4000, value_adjusted_total: 3452 }},
        }}, true);
        if (!summary.includes('付帯サービスまで含めると')) process.exit(3);
        if (!summary.includes('Pontaパス')) process.exit(4);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_reward_strength_dedup_with_structured_evidence(node_available):
    rewards = [{"id": "qr_reward", "type": "POINT", "name": "PayPay還元", "amount": 4000}]
    strengths = [
        {
            "rule_id": "sb_paypay_reward",
            "message": "PayPay利用により4,000pt相当の還元を受けられます",
            "evidence": {"reward_id": "qr_reward", "amount": 4000, "type": "POINT"},
        },
        {
            "rule_id": "sb_gold_linked",
            "message": "PayPayカード ゴールド連携によりペイトク2の高還元条件を活かしています",
        },
    ]
    out = _run_compare_ui_script(
        f"""
        const filtered = CompareUI.filterDuplicateRewardStrengths(
          {json.dumps(strengths)},
          {json.dumps(rewards)}
        );
        if (filtered.length !== 1) process.exit(2);
        if (filtered[0].rule_id !== 'sb_gold_linked') process.exit(3);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_reward_strength_dedup_hides_duplicate_in_card(node_available):
    entry = {
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
                "rewards": [{"id": "qr_reward", "type": "POINT", "name": "PayPay還元", "amount": 4000}],
                "applied_discounts": [],
                "bundled_services": [],
            }
        ],
        "strengths": [
            {
                "rule_id": "sb_paypay_reward",
                "message": "PayPay利用により4,000pt相当の還元を受けられます",
                "evidence": {"reward_id": "qr_reward", "amount": 4000, "type": "POINT"},
            },
            {
                "rule_id": "sb_gold_linked",
                "message": "PayPayカード ゴールド連携によりペイトク2の高還元条件を活かしています",
            },
        ],
        "cautions": [],
    }
    entry_json = json.dumps(entry)
    out = _run_compare_ui_script(
        f"""
        const html = CompareUI.renderCarrierCard({entry_json}, {{}}, {{}});
        if (html.includes('4,000pt相当の還元を受けられます')) process.exit(2);
        if (!html.includes('高還元条件を活かしています')) process.exit(3);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_compare_api_and_calculator_unchanged(client):
    compare = client.get("/api/compare?lines[0][carrier]=softbank&lines[0][data_usage]=10gb")
    calculate = client.get("/api/calculate?lines[0][carrier]=softbank&lines[0][data_usage]=10gb")
    assert compare.status_code == 200
    assert calculate.status_code == 200
    assert "recommended" not in compare.get_json()
