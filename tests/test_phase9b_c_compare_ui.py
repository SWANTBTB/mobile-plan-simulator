"""フェーズ⑨B-C: axis_quotes 基準の比較UI検証。"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
COMPARE_UI_JS = ROOT / "static" / "js" / "compare-ui.js"


def _run(script: str) -> str:
    if shutil.which("node") is None:
        pytest.skip("Node.js not available")
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
        details = "\n".join(
            part
            for part in (
                f"exit code: {result.returncode}",
                f"stdout:\n{result.stdout.strip()}" if result.stdout.strip() else "",
                f"stderr:\n{result.stderr.strip()}" if result.stderr.strip() else "",
            )
            if part
        )
        pytest.fail(f"Compare UI script failed:\n{details}")
    return result.stdout.strip()


@pytest.fixture
def node_available():
    if shutil.which("node") is None:
        pytest.skip("Node.js not available")


def _axis_entry(**overrides):
    base = {
        "carrier_id": "softbank",
        "carrier_name": "SoftBank",
        "status": "ok",
        "billing_total": 8008,
        "reward_total": 4000,
        "effective_total": 6538,
        "value_adjusted_total": 6538,
        "bundled_value": 0,
        "lines": [
            {
                "plan_id": "paytoku2",
                "plan_name": "ペイトク2",
                "rewards": [{"id": "qr_reward", "type": "POINT", "name": "PayPay還元", "amount": 4000}],
            }
        ],
        "axis_quotes": {
            "billing": {
                "plan_id": "teigaku_unlimited",
                "plan_name": "テイガク（使った分だけ）",
                "plan_ids": ["teigaku_unlimited"],
                "billing_total": 8008,
                "reward_total": 0,
                "effective_total": 8008,
                "value_adjusted_total": 8008,
                "bundled_value": 0,
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
                "bundled_value": 0,
                "lines": [
                    {
                        "plan_id": "paytoku2",
                        "plan_name": "ペイトク2",
                        "rewards": [{"id": "qr_reward", "type": "POINT", "name": "PayPay還元", "amount": 4000}],
                    }
                ],
            },
            "value_adjusted": {
                "plan_id": "paytoku2",
                "plan_name": "ペイトク2",
                "plan_ids": ["paytoku2"],
                "billing_total": 10538,
                "reward_total": 4000,
                "effective_total": 6538,
                "value_adjusted_total": 6538,
                "bundled_value": 0,
                "lines": [{"plan_id": "paytoku2", "plan_name": "ペイトク2", "rewards": []}],
            },
        },
        "strengths": [{"rule_id": "sb_paypay_reward", "message": "PayPay還元", "evidence": {"reward_id": "qr_reward"}}],
        "cautions": [],
    }
    base.update(overrides)
    return base


def test_softbank_divergence_separate_blocks(node_available):
    entry = json.dumps(_axis_entry())
    out = _run(
        f"""
        const html = CompareUI.renderCarrierCard({entry}, {{ billing: {{ carrier_id: 'ymobile', plan_id: 'x' }}, effective: {{ carrier_id: 'softbank', plan_id: 'paytoku2', plan_ids: ['paytoku2'] }}, valueAdjusted: null }}, {{}});
        if (!html.includes('料金だけなら')) process.exit(2);
        if (!html.includes('還元まで含めると')) process.exit(3);
        if (!html.includes('8,008円')) process.exit(4);
        if (!html.includes('10,538円')) process.exit(5);
        if (!html.includes('4,000pt')) process.exit(6);
        if (!html.includes('6,538円相当')) process.exit(7);
        if (!html.includes('テイガク')) process.exit(8);
        if (!html.includes('ペイトク2')) process.exit(9);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_softbank_divergence_no_mixed_billing_on_effective_block(node_available):
    entry = json.dumps(_axis_entry())
    out = _run(
        f"""
        const blocks = CompareUI.buildPlanBlockGroups({entry});
        if (blocks.length !== 2) process.exit(2);
        const html = CompareUI.renderCarrierCard({entry}, {{}}, {{}});
        const billingIdx = html.indexOf('8,008円');
        const paytokuBillingIdx = html.indexOf('10,538円');
        if (billingIdx < 0 || paytokuBillingIdx < 0) process.exit(3);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_unified_same_plan_compact(node_available):
    entry = json.dumps(
        _axis_entry(
            carrier_id="rakuten",
            carrier_name="Rakuten Mobile",
            axis_quotes={
                "billing": {
                    "plan_id": "saikyo_3gb",
                    "plan_name": "Rakuten最強プラン",
                    "plan_ids": ["saikyo_3gb"],
                    "billing_total": 1078,
                    "reward_total": 9,
                    "effective_total": 1069,
                    "value_adjusted_total": 1069,
                    "lines": [{"plan_id": "saikyo_3gb", "plan_name": "Rakuten最強プラン", "rewards": []}],
                },
                "effective": {
                    "plan_id": "saikyo_3gb",
                    "plan_name": "Rakuten最強プラン",
                    "plan_ids": ["saikyo_3gb"],
                    "billing_total": 1078,
                    "reward_total": 9,
                    "effective_total": 1069,
                    "value_adjusted_total": 1069,
                    "lines": [{"plan_id": "saikyo_3gb", "plan_name": "Rakuten最強プラン", "rewards": []}],
                },
                "value_adjusted": {
                    "plan_id": "saikyo_3gb",
                    "plan_name": "Rakuten最強プラン",
                    "plan_ids": ["saikyo_3gb"],
                    "billing_total": 1078,
                    "reward_total": 9,
                    "effective_total": 1069,
                    "value_adjusted_total": 1069,
                    "lines": [{"plan_id": "saikyo_3gb", "plan_name": "Rakuten最強プラン", "rewards": []}],
                },
            },
        )
    )
    out = _run(
        f"""
        const blocks = CompareUI.buildPlanBlockGroups({entry});
        if (blocks.length !== 1 || blocks[0].kind !== 'unified') process.exit(2);
        const html = CompareUI.renderCarrierCard({entry}, {{}}, {{}});
        if (html.includes('料金だけなら')) process.exit(3);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_summary_split_includes_plan_name(node_available):
    out = _run(
        """
        const html = CompareUI.renderSummarySplit({
          billing: { carrier_id: 'softbank', carrier_name: 'SoftBank', plan_id: 'teigaku_unlimited', plan_name: 'テイガク（使った分だけ）', billing_total: 8008, effective_total: 8008, value_adjusted_total: 8008 },
          effective: { carrier_id: 'softbank', carrier_name: 'SoftBank', plan_id: 'paytoku2', plan_name: 'ペイトク2', billing_total: 10538, effective_total: 6538, value_adjusted_total: 6538 },
          valueAdjusted: { carrier_id: 'softbank', carrier_name: 'SoftBank', plan_id: 'paytoku2', plan_name: 'ペイトク2', billing_total: 10538, effective_total: 6538, value_adjusted_total: 6538 },
        }, true);
        if (!html.includes('テイガク')) process.exit(2);
        if (!html.includes('ペイトク2')) process.exit(3);
        if (html.includes('すべて最安')) process.exit(4);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_summary_combined_requires_same_plan_id(node_available):
    out = _run(
        """
        const same = CompareUI.allCheapestSamePlan({
          billing: { carrier_id: 'rakuten', plan_id: 'saikyo_3gb', plan_ids: ['saikyo_3gb'] },
          effective: { carrier_id: 'rakuten', plan_id: 'saikyo_3gb', plan_ids: ['saikyo_3gb'] },
          valueAdjusted: { carrier_id: 'rakuten', plan_id: 'saikyo_3gb', plan_ids: ['saikyo_3gb'] },
        });
        const diff = CompareUI.allCheapestSamePlan({
          billing: { carrier_id: 'softbank', plan_id: 'teigaku_unlimited', plan_ids: ['teigaku_unlimited'] },
          effective: { carrier_id: 'softbank', plan_id: 'paytoku2', plan_ids: ['paytoku2'] },
          valueAdjusted: { carrier_id: 'softbank', plan_id: 'paytoku2', plan_ids: ['paytoku2'] },
        });
        if (!same || diff) process.exit(2);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_cheapest_badge_on_correct_plan_block(node_available):
    entry = json.dumps(_axis_entry())
    out = _run(
        f"""
        const html = CompareUI.renderCarrierCard({entry}, {{
          billing: {{ carrier_id: 'softbank', plan_id: 'teigaku_unlimited', plan_ids: ['teigaku_unlimited'] }},
          effective: {{ carrier_id: 'softbank', plan_id: 'paytoku2', plan_ids: ['paytoku2'] }},
          valueAdjusted: null
        }}, {{}});
        const billingBlock = html.split('compare-plan-block--billing')[1] || '';
        const effectiveBlock = html.split('compare-plan-block--effective')[1] || '';
        if (!billingBlock.includes('請求額 最安')) process.exit(2);
        if (!effectiveBlock.includes('実質負担 最安')) process.exit(3);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_multi_line_plan_ids_use_details(node_available):
    entry = json.dumps(
        _axis_entry(
            axis_quotes={
                "billing": {
                    "plan_ids": ["docomo_mini", "docomo_max_unlimited"],
                    "plan_name": "docomo_mini",
                    "billing_total": 10648,
                    "reward_total": 0,
                    "effective_total": 10648,
                    "value_adjusted_total": 10648,
                    "lines": [
                        {"line_index": 0, "plan_id": "docomo_mini", "plan_name": "docomo mini", "rewards": []},
                        {"line_index": 1, "plan_id": "docomo_max_unlimited", "plan_name": "docomo MAX", "rewards": []},
                    ],
                },
                "effective": {
                    "plan_ids": ["docomo_mini", "docomo_max_unlimited"],
                    "plan_name": "docomo_mini",
                    "billing_total": 10648,
                    "reward_total": 0,
                    "effective_total": 10648,
                    "value_adjusted_total": 10648,
                    "lines": [
                        {"line_index": 0, "plan_id": "docomo_mini", "plan_name": "docomo mini", "rewards": []},
                        {"line_index": 1, "plan_id": "docomo_max_unlimited", "plan_name": "docomo MAX", "rewards": []},
                    ],
                },
                "value_adjusted": {
                    "plan_ids": ["docomo_mini", "docomo_max_unlimited"],
                    "plan_name": "docomo_mini",
                    "billing_total": 10648,
                    "reward_total": 0,
                    "effective_total": 10648,
                    "value_adjusted_total": 10648,
                    "lines": [
                        {"line_index": 0, "plan_id": "docomo_mini", "plan_name": "docomo mini", "rewards": []},
                        {"line_index": 1, "plan_id": "docomo_max_unlimited", "plan_name": "docomo MAX", "rewards": []},
                    ],
                },
            }
        )
    )
    out = _run(
        f"""
        const html = CompareUI.renderCarrierCard({entry}, {{}}, {{}});
        if (!html.includes('回線ごとのプランを見る')) process.exit(2);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_api_compare_axis_quotes_present(client):
    response = client.get(
        "/api/compare?lines[0][carrier]=softbank&lines[0][data_usage]=30gb"
        "&lines[0][qr_paypay]=40000&lines[0][paypay_gold_linked]=1"
    )
    assert response.status_code == 200
    payload = response.get_json()
    sb = next(item for item in payload["comparisons"] if item["carrier_id"] == "softbank")
    assert sb["axis_quotes"]["billing"]["plan_id"] == "teigaku_unlimited"
    assert sb["axis_quotes"]["effective"]["plan_id"] == "paytoku2"
    assert payload["cheapest_billing"].get("plan_id")


def test_savings_shows_plan_name_when_available(node_available):
    payload = json.dumps(
        {
            "current_cost": {"billing_total": 8500, "source": "user_reported"},
            "savings_summary": {
                "carrier_id": "docomo",
                "current_billing_total": 8500,
                "new_billing_total": 2750,
                "monthly_saving": 5750,
                "annual_saving": 69000,
                "source": "user_reported",
            },
            "cheapest_billing": {
                "carrier_id": "docomo",
                "carrier_name": "docomo",
                "plan_id": "docomo_mini",
                "plan_name": "docomo mini",
                "billing_total": 2750,
            },
        }
    )
    out = _run(
        f"""
        const html = CompareUI.renderCurrentSavings({payload}, {{ docomo: {{ name: 'docomo' }} }});
        if (!html.includes('docomo mini')) process.exit(2);
        console.log('ok');
        """
    )
    assert out == "ok"
