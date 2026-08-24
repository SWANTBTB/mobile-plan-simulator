"""フェーズ⑦C: 現在契約との差額UIの検証。"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
COMPARE_UI_JS = ROOT / "static" / "js" / "compare-ui.js"


def _run_compare_ui_script(script: str) -> str:
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


def _savings_payload(**overrides):
    base = {
        "current_cost": {"billing_total": 8500, "source": "user_reported"},
        "savings_summary": {
            "carrier_id": "rakuten",
            "current_billing_total": 8500,
            "new_billing_total": 2178,
            "monthly_saving": 6322,
            "annual_saving": 75864,
            "source": "user_reported",
        },
        "cheapest_billing": {
            "carrier_id": "rakuten",
            "carrier_name": "Rakuten Mobile",
            "billing_total": 2178,
        },
        "comparison_complete": True,
        "comparisons": [],
    }
    base.update(overrides)
    return base


# --- ページ構造 ---


def test_simulator_page_renders_savings_section_on_compare_page(client):
    response = client.get("/compare")
    html = response.get_data(as_text=True)
    assert 'id="compare-savings"' in html
    assert 'id="compare-savings-hint"' in html


def test_simulator_page_renders_account_notes(client):
    response = client.get("/")
    html = response.get_data(as_text=True)
    assert "端末代金や一時的な請求を除いた" in html
    assert "複数回線の場合は世帯合計" in html


def test_compare_ui_js_declares_savings_renderer():
    content = COMPARE_UI_JS.read_text(encoding="utf-8")
    assert "renderCurrentSavings" in content
    assert "data-compare-savings=" in content
    assert "請求額が最も安い" in content


# --- Node: savings UI ---


def test_ui1_user_reported_positive_savings(node_available):
    payload = json.dumps(_savings_payload())
    out = _run_compare_ui_script(
        f"""
        const html = CompareUI.renderCurrentSavings({payload}, {{ rakuten: {{ name: 'Rakuten Mobile' }} }});
        if (!html.includes('8,500円')) process.exit(2);
        if (!html.includes('2,178円')) process.exit(3);
        if (!html.includes('6,322円安い')) process.exit(4);
        if (!html.includes('75,864円安い')) process.exit(5);
        if (!html.includes('年間換算')) process.exit(6);
        if (!html.includes('現在の携帯料金')) process.exit(7);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_ui2_estimated_shows_base_price_wording(node_available):
    payload = json.dumps(
        _savings_payload(
            current_cost={"billing_total": 3278, "source": "estimated_plan_base"},
            savings_summary={
                "carrier_id": "rakuten",
                "current_billing_total": 3278,
                "new_billing_total": 2178,
                "monthly_saving": 1100,
                "annual_saving": 13200,
                "source": "estimated_plan_base",
            },
        )
    )
    out = _run_compare_ui_script(
        f"""
        const html = CompareUI.renderCurrentSavings({payload}, {{}});
        if (!html.includes('現在プランの基本料金')) process.exit(2);
        if (!html.includes('基本料金と比べると')) process.exit(3);
        if (!html.includes('約1,100円安い計算です')) process.exit(4);
        if (!html.includes('13,200円の差')) process.exit(5);
        if (html.includes('節約')) process.exit(6);
        if (html.includes('お得')) process.exit(7);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_ui3_unavailable_renders_empty(node_available):
    payload = json.dumps(
        {
            "current_cost": {"billing_total": None, "source": "unavailable"},
            "savings_summary": None,
            "comparison_complete": True,
        }
    )
    out = _run_compare_ui_script(
        f"""
        const html = CompareUI.renderCurrentSavings({payload}, {{}});
        if (html !== '') process.exit(2);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_ui4_negative_savings_shows_higher(node_available):
    payload = json.dumps(
        _savings_payload(
            savings_summary={
                "carrier_id": "rakuten",
                "current_billing_total": 3000,
                "new_billing_total": 4000,
                "monthly_saving": -1000,
                "annual_saving": -12000,
                "source": "user_reported",
            },
            cheapest_billing={"carrier_id": "rakuten", "carrier_name": "Rakuten Mobile", "billing_total": 4000},
        )
    )
    out = _run_compare_ui_script(
        f"""
        const html = CompareUI.renderCurrentSavings({payload}, {{}});
        if (!html.includes('1,000円高い')) process.exit(2);
        if (html.includes('-1,000')) process.exit(3);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_ui5_zero_savings_shows_same_amount(node_available):
    payload = json.dumps(
        _savings_payload(
            savings_summary={
                "carrier_id": "rakuten",
                "current_billing_total": 5000,
                "new_billing_total": 5000,
                "monthly_saving": 0,
                "annual_saving": 0,
                "source": "user_reported",
            },
            cheapest_billing={"carrier_id": "rakuten", "carrier_name": "Rakuten Mobile", "billing_total": 5000},
        )
    )
    out = _run_compare_ui_script(
        f"""
        const html = CompareUI.renderCurrentSavings({payload}, {{}});
        if (!html.includes('現在と同額')) process.exit(2);
        if (html.includes('年間換算')) process.exit(3);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_ui6_annual_uses_api_value_not_recomputed(node_available):
    out = _run_compare_ui_script(
        """
        const text = CompareUI.formatSavingAnnualText(99999, 'user_reported', 8333);
        if (text !== '約99,999円安い') process.exit(2);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_ui7_no_effective_saving_wording(node_available):
    payload = json.dumps(_savings_payload())
    out = _run_compare_ui_script(
        f"""
        const html = CompareUI.renderCurrentSavings({payload}, {{}});
        if (/実質.*安い/.test(html)) process.exit(2);
        if (html.includes('effective')) process.exit(3);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_ui8_no_recommended_wording(node_available):
    content = COMPARE_UI_JS.read_text(encoding="utf-8")
    assert "おすすめ" not in content
    payload = json.dumps(_savings_payload())
    out = _run_compare_ui_script(
        f"""
        const html = CompareUI.renderCurrentSavings({payload}, {{}});
        if (html.includes('おすすめ')) process.exit(2);
        if (!html.includes('請求額が最も安い')) process.exit(3);
        console.log('ok');
        """
    )
    assert out == "ok"


def test_format_saving_monthly_does_not_recompute_from_totals(node_available):
    out = _run_compare_ui_script(
        """
        const text = CompareUI.formatSavingMonthlyText(6322, 'user_reported');
        if (!text.includes('6,322円安い')) process.exit(2);
        console.log('ok');
        """
    )
    assert out == "ok"
