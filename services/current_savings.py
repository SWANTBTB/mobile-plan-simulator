"""現在契約と横断比較候補の請求額差額（billing_total 基準）を付与する。"""

from __future__ import annotations

from typing import Any


def build_current_cost(resolved_current: dict[str, Any] | None) -> dict[str, Any]:
    """resolve_current_plan の結果から current_cost を組み立てる。"""
    if resolved_current is None:
        return {"billing_total": None, "source": "unavailable"}

    return {
        "billing_total": resolved_current["billing_total"],
        "source": resolved_current["source"],
    }


def compute_vs_current(
    current_billing_total: int | None,
    candidate_billing_total: int | None,
) -> dict[str, int] | None:
    """候補1件分の billing 差額。current または候補 billing が無い場合は None。"""
    if current_billing_total is None or candidate_billing_total is None:
        return None

    billing_monthly_diff = current_billing_total - candidate_billing_total
    return {
        "billing_monthly_diff": billing_monthly_diff,
        "billing_annual_diff": billing_monthly_diff * 12,
    }


def build_savings_summary(
    current_cost: dict[str, Any],
    cheapest_billing: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """cheapest_billing 向けの savings_summary。current 未解決時は None。"""
    current_billing_total = current_cost.get("billing_total")
    if current_cost.get("source") == "unavailable" or current_billing_total is None:
        return None
    if cheapest_billing is None or cheapest_billing.get("billing_total") is None:
        return None

    new_billing_total = cheapest_billing["billing_total"]
    monthly_saving = current_billing_total - new_billing_total
    return {
        "carrier_id": cheapest_billing["carrier_id"],
        "current_billing_total": current_billing_total,
        "new_billing_total": new_billing_total,
        "monthly_saving": monthly_saving,
        "annual_saving": monthly_saving * 12,
        "source": current_cost["source"],
    }


def attach_current_savings_to_compare_result(
    result: dict[str, Any],
    resolved_current: dict[str, Any] | None,
) -> dict[str, Any]:
    """compare 結果に current_cost / vs_current / savings_summary を付与する（in-place）。"""
    current_cost = build_current_cost(resolved_current)
    result["current_cost"] = current_cost

    current_billing_total = current_cost["billing_total"]

    for entry in result.get("comparisons") or []:
        entry["vs_current"] = compute_vs_current(
            current_billing_total,
            entry.get("billing_total") if entry.get("status") == "ok" else None,
        )

    result["savings_summary"] = build_savings_summary(
        current_cost,
        result.get("cheapest_billing"),
    )
    return result
