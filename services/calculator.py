from __future__ import annotations

from datetime import date
from typing import Any

from services.data_loader import get_carrier_map, load_all_carriers

MAX_DATA_GB = 10_000
MAX_AGE = 120
MAX_LINES = 10
MAX_TENURE_YEARS = 100
MAX_CURRENT_PRICE = 1_000_000
MAX_QR_SPEND = 1_000_000
DCARD_TIERS = {"standard", "gold", "platinum"}
PAYPAY_CARD_TIERS = {"standard", "gold"}
AU_BILL_PAYMENT_MODES = {"other", "au_pay_card", "au_jibun_bank_direct_debit"}
AU_BILL_PAYMENT_CASH_STANDARD = 1100
AU_BILL_PAYMENT_CASH_JIBUN_CARD = 1650
AU_DEPOSIT_BALANCE_TIERS: tuple[tuple[int, int], ...] = (
    (500_000, 550),
    (300_000, 330),
    (100_000, 110),
)
MAX_AU_JIBUN_BANK_BALANCE = 10_000_000
CONSUMPTION_TAX_NUMERATOR = 10
CONSUMPTION_TAX_DENOMINATOR = 11
DOCOMO_DBARAI_POINT_UNIT_YEN = 200

# au 年齢向けプラン（JSON plan id ベース。監査済み公式境界）
_AU_AGE_PLAN_REQUIREMENTS: dict[str, dict[str, int]] = {
    "u12_value": {"age_max": 12},
    "u18_value_3gb": {"age_min": 5, "age_max": 18},
    "u18_value_20gb": {"age_min": 5, "age_max": 18},
    "senior_value": {"age_min": 60},
}

# Rakuten 最強こども割・青春割・シニアは Rakuten Link / Web エントリー必須（自動適用しない）
RAKUTEN_ENTRY_REQUIRED_AGE_DISCOUNTS: frozenset[str] = frozenset(
    {"child_discount", "youth_discount", "senior_program"}
)

HOME_SET_GROUPS: dict[str, dict[str, str]] = {
    "softbank": {"softbank": "home_fiber_set", "ymobile": "hikari_set"},
    "au": {"au": "smart_value", "uqmobile": "home_set"},
    "docomo": {"docomo": "docomo_hikari_set"},
    "docomo_denki": {"docomo": "docomo_denki_set"},
}

EVERYONE_DOCOMO_DISCOUNT_ID = "everyone_docomo"


def build_docomo_family_discount_carrier_ids(
    carriers: list[dict[str, Any]] | None = None,
) -> set[str]:
    """parent_carrier=docomo を同一ファミリー割引グループの判定材料として使う。"""
    carriers = carriers or load_all_carriers()
    group_ids = {"docomo"}
    for carrier in carriers:
        if carrier.get("parent_carrier") == "docomo":
            group_ids.add(carrier["id"])
    return group_ids


def _plan_family_meta(plan: dict[str, Any], discount_id: str) -> dict[str, Any]:
    return plan.get(discount_id) or {}


def plan_family_counts_toward_lines(plan: dict[str, Any], discount_id: str) -> bool:
    meta = _plan_family_meta(plan, discount_id)
    if "counts_toward_lines" in meta:
        return bool(meta["counts_toward_lines"])
    return True


def plan_family_applies_discount(plan: dict[str, Any], discount_id: str) -> bool:
    meta = _plan_family_meta(plan, discount_id)
    if "applies_discount" in meta:
        return bool(meta["applies_discount"])
    return True


def count_family_group_lines(
    resolved_lines: list[tuple[str, dict[str, Any]]],
    carrier_map: dict[str, dict[str, Any]],
    group_carrier_ids: set[str],
    discount_id: str,
) -> int:
    count = 0
    for carrier_id, line in resolved_lines:
        if carrier_id not in group_carrier_ids:
            continue
        carrier = carrier_map[carrier_id]
        plan, _, _ = resolve_selected_plan(
            carrier,
            line.get("data_usage") or "10gb",
            line.get("plan"),
            age=parse_optional_int(line.get("age"), "age", 0, MAX_AGE),
        )
        if plan_family_counts_toward_lines(plan, discount_id):
            count += 1
    return count


def build_family_line_counts_by_carrier(
    resolved_lines: list[tuple[str, dict[str, Any]]],
    carrier_map: dict[str, dict[str, Any]],
    carriers: list[dict[str, Any]],
) -> dict[str, int]:
    docomo_group = build_docomo_family_discount_carrier_ids(carriers)
    return {
        "softbank": count_family_group_lines(
            resolved_lines, carrier_map, {"softbank"}, "family_discount"
        ),
        "ymobile": count_family_group_lines(
            resolved_lines, carrier_map, {"ymobile"}, "family_discount"
        ),
        "au": count_family_group_lines(resolved_lines, carrier_map, {"au"}, "family_plus"),
        "uqmobile": count_family_group_lines(
            resolved_lines, carrier_map, {"uqmobile"}, "family_set"
        ),
        "rakuten": count_family_group_lines(
            resolved_lines, carrier_map, {"rakuten"}, "family_discount"
        ),
        "docomo": count_family_group_lines(
            resolved_lines, carrier_map, docomo_group, EVERYONE_DOCOMO_DISCOUNT_ID
        ),
    }


def build_family_discount_ids(carriers: list[dict[str, Any]] | None = None) -> dict[str, list[str]]:
    """回線数条件のある割引（家族割等）。"""
    carriers = carriers or load_all_carriers()
    family_ids: dict[str, list[str]] = {}
    for carrier in carriers:
        ids: list[str] = []
        for discount in carrier.get("discounts") or []:
            requirements = discount.get("requirements") or {}
            if requirements.get("min_lines") or discount.get("line_tiers"):
                ids.append(discount["id"])
        if ids:
            family_ids[carrier["id"]] = ids
    return family_ids


def build_family_discount_primary_blocked(
    carriers: list[dict[str, Any]] | None = None,
) -> dict[str, list[str]]:
    """キャリア内1回線目で適用不可の家族割（includes_primary_line 以外）。"""
    carriers = carriers or load_all_carriers()
    family_ids = build_family_discount_ids(carriers)
    blocked: dict[str, list[str]] = {}
    for carrier in carriers:
        carrier_id = carrier["id"]
        discount_map = {discount["id"]: discount for discount in carrier.get("discounts") or []}
        ids = [
            discount_id
            for discount_id in family_ids.get(carrier_id, [])
            if not discount_map.get(discount_id, {}).get("includes_primary_line")
        ]
        if ids:
            blocked[carrier_id] = ids
    return blocked


def primary_blocked_family_discount_ids(
    carrier: dict[str, Any],
    carrier_line_index: int,
    family_discount_ids: dict[str, list[str]],
) -> set[str]:
    if carrier_line_index != 0:
        return set()
    discount_map = {discount["id"]: discount for discount in carrier.get("discounts") or []}
    return {
        discount_id
        for discount_id in family_discount_ids.get(carrier["id"], [])
        if not discount_map.get(discount_id, {}).get("includes_primary_line")
    }


def _discount_ids_for_line(
    selected_discount_ids: list[str],
    blocked_family_discount_ids: set[str],
) -> list[str]:
    if not blocked_family_discount_ids:
        return list(selected_discount_ids)
    return [
        discount_id
        for discount_id in selected_discount_ids
        if discount_id not in blocked_family_discount_ids
    ]


def build_exclusive_discounts(carriers: list[dict[str, Any]]) -> dict[str, dict[str, list[str]]]:
    """キャリアJSONの exclusive_with からUI用の排他ルール表を構築する。"""
    rules: dict[str, dict[str, list[str]]] = {}
    for carrier in carriers:
        carrier_rules: dict[str, list[str]] = {}
        for discount in carrier.get("discounts") or []:
            exclusive_with = discount.get("exclusive_with")
            if exclusive_with:
                carrier_rules[discount["id"]] = list(exclusive_with)
        if carrier_rules:
            rules[carrier["id"]] = carrier_rules
    return rules


def build_home_set_discount_groups() -> dict[str, str]:
    return {
        f"{carrier_id}:{discount_id}": group_id
        for group_id, mapping in HOME_SET_GROUPS.items()
        for carrier_id, discount_id in mapping.items()
    }


def _carrier_qr_wallets(carrier: dict[str, Any]) -> set[str]:
    wallets: set[str] = set()
    for plan in carrier.get("plans") or []:
        reward = plan.get("qr_reward") or {}
        if reward.get("wallet"):
            wallets.add(reward["wallet"])
        if plan.get("fixed_qr_points") and reward.get("wallet"):
            wallets.add(reward["wallet"])
        elif plan.get("fixed_qr_points"):
            wallets.add("paypay")
    return wallets


def _carrier_qr_extras(carrier: dict[str, Any]) -> dict[str, bool]:
    bill_payment = False
    deposit_bonus = False
    for plan in carrier.get("plans") or []:
        reward = plan.get("qr_reward") or {}
        if reward.get("bill_payment_bonus"):
            bill_payment = True
        if reward.get("deposit_bonus"):
            deposit_bonus = True
    return {
        "au_pay_card_bill": bill_payment,
        "au_jibun_bank": deposit_bonus,
        "au_bill_payment_mode": bill_payment,
        "au_pay_card_bank_is_jibun": bill_payment,
        "au_jibun_bank_balance": deposit_bonus,
    }


def build_carrier_ui_visibility(carriers: list[dict[str, Any]] | None = None) -> dict[str, dict[str, bool]]:
    """選択キャリアごとに表示する入力項目。"""
    carriers = carriers or load_all_carriers()
    visibility: dict[str, dict[str, bool]] = {}

    for carrier in carriers:
        carrier_id = carrier["id"]
        wallets = _carrier_qr_wallets(carrier)
        extras = _carrier_qr_extras(carrier)
        discounts = carrier.get("discounts") or []
        has_paypay_card_discount = any(
            discount.get("id") in {"paypay_card", "paypay_card_gold"} for discount in discounts
        )

        fields = {
            "tenure_years": any(
                "min_tenure_years" in (discount.get("requirements") or {})
                for discount in discounts
            ),
            "home_set_softbank": carrier_id in HOME_SET_GROUPS["softbank"],
            "home_set_au": carrier_id in HOME_SET_GROUPS["au"],
            "home_set_docomo": carrier_id in HOME_SET_GROUPS["docomo"],
            "home_set_docomo_denki": carrier_id in HOME_SET_GROUPS["docomo_denki"],
            "qr_paypay": "paypay" in wallets,
            "paypay_card_tier": has_paypay_card_discount,
            "paypay_card_section": has_paypay_card_discount,
            "paypay_gold_linked": "paypay" in wallets,
            "qr_dbarai": "dbarai" in wallets,
            "dcard_tier": any(discount.get("amount_tiers") for discount in discounts),
            "docomo_bill_dcard": carrier_id == "docomo"
            and any(discount.get("id") == "d_card" for discount in discounts),
            "qr_aupay": "aupay" in wallets,
            "aupay_gold": "aupay" in wallets,
            **extras,
        }
        fields["home_set_section"] = any(
            fields[key]
            for key in (
                "home_set_softbank",
                "home_set_au",
                "home_set_docomo",
                "home_set_docomo_denki",
            )
        )
        fields["qr_section"] = any(fields[key] for key in ("qr_paypay", "qr_dbarai", "qr_aupay"))
        visibility[carrier_id] = fields

    return visibility


def build_account_ui_visibility(
    carrier_ids: list[str],
    carrier_ui: dict[str, dict[str, bool]] | None = None,
) -> dict[str, bool]:
    """回線に含まれるキャリアの和集合で、契約共通欄の表示可否を決める。"""
    carrier_ui = carrier_ui or build_carrier_ui_visibility()
    fields = [
        "tenure_years",
        "home_set_section",
        "home_set_softbank",
        "home_set_au",
        "home_set_docomo",
        "home_set_docomo_denki",
    ]
    return {
        field: any(carrier_ui.get(carrier_id, {}).get(field) for carrier_id in carrier_ids)
        for field in fields
    }


def build_manual_opt_in_discount_ids(carriers: list[dict[str, Any]] | None = None) -> list[str]:
    """UIで自動チェックしない割引（セット割マスター連動・カード支払い割）。"""
    manual_ids: set[str] = set()
    for mapping in HOME_SET_GROUPS.values():
        manual_ids.update(mapping.values())
    manual_ids.update({"d_card", "au_pay_card", "paypay_card", "paypay_card_gold"})
    return sorted(manual_ids)


def build_pricing_as_of_label(carriers: list[dict[str, Any]] | None = None) -> str:
    """キャリア JSON の updated_at から料金基準日ラベルを生成する。"""
    carriers = carriers or load_all_carriers()
    dates: list[date] = []
    for carrier in carriers:
        raw = carrier.get("updated_at")
        if not raw:
            continue
        try:
            dates.append(date.fromisoformat(str(raw)))
        except ValueError:
            continue
    if not dates:
        return "現時点の料金"
    latest = max(dates)
    return f"{latest.year}年{latest.month}月{latest.day}日時点の料金"


def build_simulator_ui_config(carriers: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """フロントエンドが参照する割引連動設定。サーバー側が単一情報源。"""
    carriers = carriers or load_all_carriers()
    return {
        "home_set_groups": {
            group_id: {"discounts": mapping}
            for group_id, mapping in HOME_SET_GROUPS.items()
        },
        "exclusive_discounts": build_exclusive_discounts(carriers),
        "home_set_discount_groups": build_home_set_discount_groups(),
        "carrier_ui": build_carrier_ui_visibility(carriers),
        "family_discount_ids": build_family_discount_ids(carriers),
        "family_discount_primary_blocked": build_family_discount_primary_blocked(carriers),
        "tenure_auto_discounts": TENURE_AUTO_DISCOUNTS,
        "manual_opt_in_discount_ids": build_manual_opt_in_discount_ids(carriers),
        "pricing_as_of_label": build_pricing_as_of_label(carriers),
        "carriers": carriers,
    }


def is_checked_flag(raw: str | None) -> bool:
    return raw in ("1", "on", "true")


def infer_home_set_flags(
    discounts_by_carrier: dict[str, list[str]],
    carrier_ids: list[str],
) -> dict[str, bool]:
    flags: dict[str, bool] = {}
    for group_id, mapping in HOME_SET_GROUPS.items():
        scoped = [
            (carrier_id, discount_id)
            for carrier_id, discount_id in mapping.items()
            if carrier_id in carrier_ids
        ]
        if not scoped:
            flags[group_id] = False
            continue
        flags[group_id] = all(
            discount_id in discounts_by_carrier.get(carrier_id, [])
            for carrier_id, discount_id in scoped
        )
    return flags


def merge_home_set_discounts(
    discounts_by_carrier: dict[str, list[str]],
    home_set_flags: dict[str, bool],
    carrier_ids: list[str],
) -> dict[str, list[str]]:
    merged = {carrier_id: list(discounts_by_carrier.get(carrier_id, [])) for carrier_id in carrier_ids}
    for group_id, mapping in HOME_SET_GROUPS.items():
        if not home_set_flags.get(group_id):
            continue
        for carrier_id, discount_id in mapping.items():
            if carrier_id not in carrier_ids:
                continue
            discount_ids = merged.setdefault(carrier_id, [])
            if discount_id not in discount_ids:
                discount_ids.append(discount_id)
    return merged


TENURE_AUTO_DISCOUNTS: dict[str, dict[str, Any]] = {
    "docomo": {"discount_id": "long_term", "min_tenure_years": 10},
}


def merge_tenure_auto_discounts(
    carrier_id: str,
    selected_discount_ids: list[str] | None,
    profile: dict[str, int | None] | None,
) -> list[str]:
    """利用年数条件を満たす割引を選択リストに自動追加する。"""
    merged = list(selected_discount_ids or [])
    rule = TENURE_AUTO_DISCOUNTS.get(carrier_id)
    if not rule:
        return merged

    tenure_years = (profile or {}).get("tenure_years")
    if tenure_years is None or tenure_years < rule["min_tenure_years"]:
        return merged

    discount_id = rule["discount_id"]
    if discount_id not in merged:
        merged.append(discount_id)
    return merged


class InvalidUsageError(ValueError):
    """リクエストパラメータが不正な場合に送出する。呼び出し側で 400 に変換する。"""


def parse_optional_int(raw: str | None, label: str, minimum: int, maximum: int) -> int | None:
    """未入力は None（＝条件を判定しない）として扱う。"""
    if raw is None or str(raw).strip() == "":
        return None

    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        raise InvalidUsageError(f"invalid {label}: {raw!r}") from None

    if not minimum <= value <= maximum:
        raise InvalidUsageError(f"{label} must be between {minimum} and {maximum}: {value}")

    return value


def build_profile(
    age: str | None = None,
    line_count: str | None = None,
    tenure_years: str | None = None,
) -> dict[str, int | None]:
    return {
        "age": parse_optional_int(age, "age", 0, MAX_AGE),
        "line_count": parse_optional_int(line_count, "line_count", 1, MAX_LINES),
        "tenure_years": parse_optional_int(tenure_years, "tenure_years", 0, MAX_TENURE_YEARS),
    }


def _plan_capacity_gb(plan: dict[str, Any]) -> int | None:
    if plan.get("data_gb_max") is None:
        return None
    return plan.get("effective_data_gb_max", plan.get("data_gb_max"))


def _plan_bundled_value(plan: dict[str, Any]) -> int:
    return sum(item.get("monthly_value", 0) for item in plan.get("bundled_services") or [])


def _is_discount_in_period(discount: dict[str, Any], today: date | None = None) -> bool:
    today = today or date.today()
    if discount.get("available_from") and today < date.fromisoformat(discount["available_from"]):
        return False
    if discount.get("available_until") and today > date.fromisoformat(discount["available_until"]):
        return False
    return True


def is_discount_eligible(
    discount: dict[str, Any],
    plan: dict[str, Any],
    profile: dict[str, int | None],
) -> bool:
    """入力されていない条件は判定しない（未入力なら適用可能とみなす）。"""
    if not _is_discount_in_period(discount):
        return False

    requirements = discount.get("requirements") or {}
    age = profile.get("age")
    line_count = profile.get("line_count")
    tenure_years = profile.get("tenure_years")

    if age is not None:
        if "age_min" in requirements and age < requirements["age_min"]:
            return False
        if "age_max" in requirements and age > requirements["age_max"]:
            return False

    if line_count is not None and "min_lines" in requirements:
        if line_count < requirements["min_lines"]:
            return False

    if "min_tenure_years" in requirements:
        if tenure_years is None or tenure_years < requirements["min_tenure_years"]:
            return False

    if "plan_ids" in requirements and plan["id"] not in requirements["plan_ids"]:
        return False

    if "exclude_plan_ids" in requirements and plan["id"] in requirements["exclude_plan_ids"]:
        return False

    if discount.get("line_tiers") or requirements.get("min_lines"):
        if not plan_family_applies_discount(plan, discount["id"]):
            return False

    return True


def resolve_discount_eligibility(
    carrier: dict[str, Any],
    plan: dict[str, Any],
    profile: dict[str, int | None],
    selected_discount_ids: list[str] | None,
    qr: dict[str, Any] | None = None,
) -> dict[str, bool]:
    """割引の適用可否。exclusive_with で併用不可の組み合わせも判定する。"""
    selected = set(selected_discount_ids or [])
    discounts = carrier.get("discounts") or []
    order = [discount["id"] for discount in discounts]
    discount_map = {discount["id"]: discount for discount in discounts}

    eligibility = {
        discount["id"]: is_discount_eligible(discount, plan, profile) for discount in discounts
    }

    blocked = set(profile.get("blocked_discount_ids") or [])
    for discount_id in blocked:
        if discount_id in eligibility:
            eligibility[discount_id] = False

    for discount_id in list(selected):
        discount = discount_map.get(discount_id)
        if not discount or not eligibility.get(discount_id):
            continue
        for other_id in discount.get("exclusive_with") or []:
            if other_id not in selected or other_id not in eligibility:
                continue
            if not eligibility.get(other_id):
                continue
            other = discount_map[other_id]
            discount_amount = _resolve_discount_amount(
                discount, plan, profile.get("line_count"), qr
            )
            other_amount = _resolve_discount_amount(
                other, plan, profile.get("line_count"), qr
            )
            if discount_amount > other_amount:
                eligibility[other_id] = False
            elif discount_amount < other_amount:
                eligibility[discount_id] = False
            elif order.index(discount_id) < order.index(other_id):
                eligibility[other_id] = False
            else:
                eligibility[discount_id] = False

    for discount in discounts:
        discount_id = discount["id"]
        if not eligibility.get(discount_id) or discount_id in selected:
            continue
        for other_id in discount.get("exclusive_with") or []:
            if other_id in selected and eligibility.get(other_id):
                eligibility[discount_id] = False
                break

    return eligibility


def _resolve_discount_amount(
    discount: dict[str, Any],
    plan: dict[str, Any],
    line_count: int | None,
    qr: dict[str, Any] | None = None,
) -> int:
    """プラン別上書き → 回線数段階 → カード種別 → 固定額の順で割引額を決める。"""
    plan_id = plan["id"]
    plan_meta = _plan_family_meta(plan, discount["id"])
    overrides = discount.get("amount_overrides") or {}
    if plan_id in overrides:
        return overrides[plan_id]

    tiers = plan_meta.get("line_tiers") or discount.get("line_tiers")
    if tiers:
        sorted_tiers = sorted(tiers, key=lambda tier: tier["min_lines"], reverse=True)
        if line_count is not None:
            for tier in sorted_tiers:
                if line_count >= tier["min_lines"]:
                    return tier["amount"]
            return 0
        return max(tier["amount"] for tier in sorted_tiers)

    tier_amounts = discount.get("amount_tiers")
    if tier_amounts and qr:
        tier = qr.get("dcard_tier", "standard")
        if tier in tier_amounts:
            return tier_amounts[tier]

    return discount.get("amount", 0)


def _build_resolved_discount_amounts(
    carrier: dict[str, Any],
    plan: dict[str, Any],
    profile: dict[str, int | None],
    qr: dict[str, Any] | None = None,
) -> dict[str, int]:
    """割引一覧の表示用。回線数に応じた適用額（未達時は最大額）を返す。"""
    line_count = profile.get("line_count")
    amounts: dict[str, int] = {}
    for discount in carrier.get("discounts") or []:
        if not is_discount_eligible(discount, plan, profile):
            amounts[discount["id"]] = 0
            continue
        amount = _resolve_discount_amount(discount, plan, line_count, qr)
        if amount == 0 and discount.get("line_tiers"):
            amount = max(tier["amount"] for tier in discount["line_tiers"])
        amounts[discount["id"]] = amount
    return amounts


def _parse_data_gb(data_usage: str) -> int | None:
    if data_usage == "unlimited":
        return None

    try:
        value = int(str(data_usage).replace("gb", ""))
    except (TypeError, ValueError):
        raise InvalidUsageError(f"invalid data_usage: {data_usage!r}") from None

    if value < 0:
        raise InvalidUsageError(f"data_usage must be >= 0: {value}")
    if value > MAX_DATA_GB:
        raise InvalidUsageError(f"data_usage must be <= {MAX_DATA_GB}: {value}")

    return value


def _cheapest_unlimited(plans: list[dict[str, Any]]) -> dict[str, Any] | None:
    unlimited_plans = [plan for plan in plans if plan.get("data_gb_max") is None]
    if not unlimited_plans:
        return None
    return min(unlimited_plans, key=lambda plan: (plan["base_price"], plan.get("priority", 999)))


def _plan_age_requirements(plan: dict[str, Any], carrier_id: str) -> dict[str, int]:
    """プランの年齢要件。JSON requirements があれば優先、なければ au 監査済みマップ。"""
    requirements = plan.get("requirements") or {}
    if requirements:
        return requirements
    if carrier_id == "au":
        return dict(_AU_AGE_PLAN_REQUIREMENTS.get(plan.get("id") or "", {}))
    return {}


def _plan_age_eligible(plan: dict[str, Any], carrier_id: str, age: int | None) -> bool:
    requirements = _plan_age_requirements(plan, carrier_id)
    if not requirements:
        return True
    if age is None:
        return False
    age_min = requirements.get("age_min")
    age_max = requirements.get("age_max")
    if age_min is not None and age < age_min:
        return False
    if age_max is not None and age > age_max:
        return False
    return True


def select_plan_for_usage(
    carrier: dict[str, Any],
    data_gb: int | None,
    age: int | None = None,
) -> dict[str, Any]:
    """通信量に収まる最小容量のプランを選ぶ。priority は表示順専用で選定には使わない。"""
    carrier_id = carrier.get("id") or ""
    plans = [
        plan
        for plan in (carrier.get("plans") or [])
        if _plan_age_eligible(plan, carrier_id, age)
    ]
    if not plans:
        raise ValueError(f"carrier '{carrier_id}' has no eligible plans for age={age!r}")

    cheapest_unlimited = _cheapest_unlimited(plans)

    if data_gb is None:
        if cheapest_unlimited:
            return cheapest_unlimited
        capped = [plan for plan in plans if _plan_capacity_gb(plan) is not None]
        if capped:
            return max(capped, key=lambda plan: _plan_capacity_gb(plan))
        return plans[-1]

    matched = [
        plan
        for plan in plans
        if _plan_capacity_gb(plan) is not None and data_gb <= _plan_capacity_gb(plan)
    ]
    if matched:
        return min(matched, key=lambda plan: (_plan_capacity_gb(plan), plan["base_price"]))

    return cheapest_unlimited or plans[-1]


def resolve_selected_plan(
    carrier: dict[str, Any],
    data_usage: str,
    plan_id: str | None = None,
    age: int | None = None,
) -> tuple[dict[str, Any], bool, dict[str, Any]]:
    """手動指定があればそのプラン、なければ通信量から自動選択。"""
    auto_plan = select_plan_for_usage(carrier, _parse_data_gb(data_usage), age=age)
    if not plan_id:
        return auto_plan, False, auto_plan

    manual = next((plan for plan in carrier.get("plans") or [] if plan["id"] == plan_id), None)
    if manual is None:
        return auto_plan, False, auto_plan
    return manual, True, auto_plan


def is_plan_under_capacity(plan: dict[str, Any], data_gb: int | None) -> bool:
    """指定プランが入力通信量をカバーできないとき True。"""
    max_gb = _plan_capacity_gb(plan)
    if max_gb is None:
        return False
    if data_gb is None:
        return True
    return data_gb > max_gb


def normalize_paypay_card_tier(
    paypay_card_tier: str | None = None,
    paypay_gold: str | None = None,
) -> str:
    """PayPayカード種別。legacy の paypay_gold チェックにも対応。"""
    tier = (paypay_card_tier or "").strip().lower()
    if tier in PAYPAY_CARD_TIERS:
        return tier
    if str(paypay_gold or "").lower() in {"1", "on", "true"}:
        return "gold"
    return ""


def _is_truthy_flag(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").lower() in {"1", "on", "true"}


def _normalize_au_bill_payment_mode(qr: dict[str, Any]) -> str:
    mode = (qr.get("au_bill_payment_mode") or "other").strip().lower()
    if mode in AU_BILL_PAYMENT_MODES and mode != "other":
        return mode
    if _is_truthy_flag(qr.get("au_pay_card_bill")):
        return "au_pay_card"
    if _is_truthy_flag(qr.get("au_jibun_bank")):
        return "au_jibun_bank_direct_debit"
    return "other"


def _au_pay_card_bank_is_jibun(qr: dict[str, Any]) -> bool:
    if _is_truthy_flag(qr.get("au_pay_card_bank_is_jibun")):
        return True
    return _is_truthy_flag(qr.get("au_pay_card_bill")) and _is_truthy_flag(qr.get("au_jibun_bank"))


def _au_bill_payment_cash(qr: dict[str, Any]) -> int:
    mode = _normalize_au_bill_payment_mode(qr)
    if mode == "au_pay_card" and _au_pay_card_bank_is_jibun(qr):
        return AU_BILL_PAYMENT_CASH_JIBUN_CARD
    if mode in {"au_pay_card", "au_jibun_bank_direct_debit"}:
        return AU_BILL_PAYMENT_CASH_STANDARD
    return 0


def _au_deposit_cash(qr: dict[str, Any]) -> int:
    """auじぶん銀行普通預金残高に応じた銀行あずけて特典（CASH）。"""
    balance = qr.get("au_jibun_bank_balance")
    if balance is None:
        return 0
    for threshold, amount in AU_DEPOSIT_BALANCE_TIERS:
        if balance >= threshold:
            return amount
    return 0


def _rakuten_mobile_usage_points(billing_total: int) -> int:
    """対象利用料金（税込・割引後）から税別100円単位で1P。"""
    if billing_total <= 0:
        return 0
    tax_excluded = billing_total * CONSUMPTION_TAX_NUMERATOR // CONSUMPTION_TAX_DENOMINATOR
    return tax_excluded // 100


def _wallet_spend_points(spend: int, percent: int, cap: int, wallet: str) -> int:
    if spend <= 0:
        return 0
    if wallet == "dbarai":
        units = spend // DOCOMO_DBARAI_POINT_UNIT_YEN
        points = units * DOCOMO_DBARAI_POINT_UNIT_YEN * percent // 100
    else:
        points = spend * percent // 100
    return min(points, cap)


def build_qr_context(
    qr_paypay: str | None = None,
    qr_dbarai: str | None = None,
    qr_aupay: str | None = None,
    paypay_card_tier: str | None = None,
    paypay_gold: str | None = None,
    paypay_gold_linked: str | None = None,
    aupay_gold: str | None = None,
    dcard_tier: str | None = None,
    au_pay_card_bill: str | None = None,
    au_jibun_bank: str | None = None,
    au_bill_payment_mode: str | None = None,
    au_pay_card_bank_is_jibun: str | None = None,
    docomo_bill_dcard: str | None = None,
    au_jibun_bank_balance: str | None = None,
) -> dict[str, Any]:
    """QR決済の月間利用額と、還元率を変えるカード種別。"""
    spend = {
        "paypay": parse_optional_int(qr_paypay, "qr_paypay", 0, MAX_QR_SPEND) or 0,
        "dbarai": parse_optional_int(qr_dbarai, "qr_dbarai", 0, MAX_QR_SPEND) or 0,
        "aupay": parse_optional_int(qr_aupay, "qr_aupay", 0, MAX_QR_SPEND) or 0,
    }
    tier = (dcard_tier or "standard").strip().lower()
    if tier not in DCARD_TIERS:
        tier = "standard"
    paypay_tier = normalize_paypay_card_tier(paypay_card_tier, paypay_gold)
    au_pay_card_bill_flag = _is_truthy_flag(au_pay_card_bill)
    au_jibun_bank_flag = _is_truthy_flag(au_jibun_bank)
    return {
        "spend": spend,
        "paypay_card_tier": paypay_tier,
        "paypay_gold_linked": _is_truthy_flag(paypay_gold_linked),
        "aupay_gold": _is_truthy_flag(aupay_gold),
        "au_pay_card_bill": au_pay_card_bill_flag,
        "au_jibun_bank": au_jibun_bank_flag,
        "au_bill_payment_mode": _normalize_au_bill_payment_mode(
            {
                "au_bill_payment_mode": au_bill_payment_mode,
                "au_pay_card_bill": au_pay_card_bill_flag,
                "au_jibun_bank": au_jibun_bank_flag,
            }
        ),
        "au_pay_card_bank_is_jibun": _au_pay_card_bank_is_jibun(
            {
                "au_pay_card_bank_is_jibun": au_pay_card_bank_is_jibun,
                "au_pay_card_bill": au_pay_card_bill_flag,
                "au_jibun_bank": au_jibun_bank_flag,
            }
        ),
        "docomo_bill_dcard": _is_truthy_flag(docomo_bill_dcard),
        "au_jibun_bank_balance": parse_optional_int(
            au_jibun_bank_balance,
            "au_jibun_bank_balance",
            0,
            MAX_AU_JIBUN_BANK_BALANCE,
        ),
        "dcard_tier": tier,
        "has_qr": any(amount > 0 for amount in spend.values()),
    }


def _qr_rate_for_plan(plan: dict[str, Any], qr: dict[str, Any]) -> dict[str, Any] | None:
    reward = plan.get("qr_reward") or {}
    rates = reward.get("rates") or {}
    wallet = reward.get("wallet")
    if not rates or not wallet:
        return None

    if wallet == "paypay":
        key = "gold" if qr.get("paypay_gold_linked") else "standard"
    elif wallet == "aupay":
        key = "gold" if qr.get("aupay_gold") else "standard"
    elif wallet == "dbarai":
        key = qr.get("dcard_tier") or "standard"
    else:
        return None

    rate = rates.get(key) or rates.get("standard")
    if not rate:
        return None
    return {
        "wallet": wallet,
        "wallet_label": reward.get("wallet_label") or wallet,
        "percent": rate["percent"],
        "cap": rate["cap"],
    }


def calculate_qr_points(
    plan: dict[str, Any],
    qr: dict[str, Any] | None,
    billing_total: int = 0,
    carrier_id: str | None = None,
) -> tuple[int, dict[str, Any] | None, int, int, int]:
    """プラン特典還元。戻り値は (POINT, rate, bill_cash, deposit_cash, rakuten_points)。"""
    qr = qr or {}
    reward = plan.get("qr_reward") or {}
    points = plan.get("fixed_qr_points") or 0
    rate = _qr_rate_for_plan(plan, qr)

    if rate:
        spend = (qr.get("spend") or {}).get(rate["wallet"]) or 0
        if spend > 0:
            points += _wallet_spend_points(
                spend,
                rate["percent"],
                rate["cap"],
                rate["wallet"],
            )

    bill_cash = _au_bill_payment_cash(qr) if reward.get("bill_payment_bonus") else 0
    deposit_cash = _au_deposit_cash(qr) if reward.get("deposit_bonus") else 0
    rakuten_points = _rakuten_mobile_usage_points(billing_total) if carrier_id == "rakuten" else 0

    point_total = points + rakuten_points
    if point_total <= 0:
        point_total = 0
    return point_total, rate, bill_cash, deposit_cash, rakuten_points


def _build_reward_entries(
    qr_point_amount: int,
    qr_rate: dict[str, Any] | None,
    bill_cash: int,
    deposit_cash: int,
    rakuten_points: int,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    wallet = (qr_rate or {}).get("wallet")
    if qr_point_amount > 0:
        if wallet == "dbarai":
            entries.append(
                {
                    "id": "docomo_poikatsu_reward",
                    "type": "POINT",
                    "name": "d払い還元（ポイ活MAX）",
                    "amount": qr_point_amount,
                }
            )
        else:
            label = "ポイント・決済還元"
            if qr_rate and qr_rate.get("wallet_label"):
                label = f"{qr_rate['wallet_label']}還元"
            entries.append(
                {
                    "id": "qr_reward",
                    "type": "POINT",
                    "name": label,
                    "amount": qr_point_amount,
                }
            )
    if rakuten_points > 0:
        entries.append(
            {
                "id": "rakuten_mobile_usage_point",
                "type": "POINT",
                "name": "楽天モバイル利用料金ポイント",
                "amount": rakuten_points,
            }
        )
    if bill_cash > 0:
        entries.append(
            {
                "id": "au_bill_payment_cash",
                "type": "CASH",
                "name": "通信料お支払い特典",
                "amount": bill_cash,
            }
        )
    if deposit_cash > 0:
        entries.append(
            {
                "id": "au_deposit_cash",
                "type": "CASH",
                "name": "銀行あずけて特典",
                "amount": deposit_cash,
            }
        )
    return entries


def _build_pricing_separation(
    base_price: int,
    billing_discount_total: int,
    billing_total: int,
    point_rewards: int,
    bill_cash: int,
    deposit_cash: int,
    rakuten_points: int,
    reward_total: int,
    effective_total: int,
    qr_rate: dict[str, Any] | None,
    qr_spend_points: int,
) -> dict[str, Any]:
    """請求額・還元・実質負担の責務分離フィールド（既存 total/qr_points との後方互換を維持）。"""
    cash_rewards = bill_cash + deposit_cash
    return {
        "base_amount": base_price,
        "option_amount": 0,
        "billing_discount_total": billing_discount_total,
        "billing_total": billing_total,
        "reward_total": reward_total,
        "rewards": _build_reward_entries(
            qr_spend_points,
            qr_rate,
            bill_cash,
            deposit_cash,
            rakuten_points,
        ),
        "effective_total": effective_total,
        "cash_rewards": cash_rewards,
        "deposit_cash": deposit_cash,
        "bill_payment_cash": bill_cash,
        "rakuten_points": rakuten_points,
    }


def _plan_auto_discount(plan: dict[str, Any], data_gb: int | None) -> dict[str, Any] | None:
    amount = plan.get("auto_discount")
    if not amount:
        return None

    max_gb = plan.get("auto_discount_max_data_gb")
    if max_gb is not None and (data_gb is None or data_gb > max_gb):
        return None

    return {
        "id": "auto_discount",
        "name": plan.get("auto_discount_label") or "プラン自動割引",
        "amount": amount,
    }


def build_plan_quotes(
    carrier: dict[str, Any],
    selected_discount_ids: list[str] | None,
    profile: dict[str, int | None],
    qr: dict[str, Any] | None,
    data_gb: int | None,
) -> dict[str, dict[str, int]]:
    quotes: dict[str, dict[str, int]] = {}
    for plan in carrier.get("plans") or []:
        priced = _price_for_plan(carrier, plan, selected_discount_ids, profile, qr, data_gb)
        quotes[plan["id"]] = {
            "total": priced["total"],
            "billing_total": priced["billing_total"],
            "effective_total": priced["effective_total"],
            "qr_points": priced["qr_points"],
            "reward_total": priced["reward_total"],
            "value_adjusted_total": priced["value_adjusted_total"],
        }
    return quotes


def _price_for_plan(
    carrier: dict[str, Any],
    plan: dict[str, Any],
    selected_discount_ids: list[str] | None,
    profile: dict[str, int | None],
    qr: dict[str, Any] | None,
    data_gb: int | None = None,
) -> dict[str, Any]:
    base_price = plan["base_price"]
    selected = set(selected_discount_ids or [])
    line_count = profile.get("line_count")
    eligibility = resolve_discount_eligibility(carrier, plan, profile, selected_discount_ids, qr)
    applied_discounts = [
        {
            **discount,
            "amount": _resolve_discount_amount(discount, plan, line_count, qr),
        }
        for discount in carrier.get("discounts", [])
        if discount["id"] in selected and eligibility[discount["id"]]
    ]
    auto_discount = _plan_auto_discount(plan, data_gb)
    if auto_discount:
        applied_discounts.insert(0, auto_discount)
    discount_total = sum(discount["amount"] for discount in applied_discounts)
    capped_discount_total = min(discount_total, base_price)
    total = base_price - capped_discount_total
    point_rewards, qr_rate, bill_cash, deposit_cash, rakuten_points = calculate_qr_points(
        plan,
        qr,
        billing_total=total,
        carrier_id=carrier["id"],
    )
    qr_spend_points = point_rewards - rakuten_points
    cash_rewards = bill_cash + deposit_cash
    reward_total = point_rewards + cash_rewards
    effective_total = max(0, total - reward_total)
    bundled_value = _plan_bundled_value(plan)
    value_adjusted_total = max(0, effective_total - bundled_value)
    separation = _build_pricing_separation(
        base_price,
        capped_discount_total,
        total,
        point_rewards,
        bill_cash,
        deposit_cash,
        rakuten_points,
        reward_total,
        effective_total,
        qr_rate,
        qr_spend_points,
    )
    return {
        "plan": plan,
        "base_price": base_price,
        "discount_total": capped_discount_total,
        "discount_capped": capped_discount_total != discount_total,
        "applied_discounts": applied_discounts,
        "discount_eligibility": eligibility,
        "total": total,
        "qr_points": point_rewards,
        "cash_rewards": cash_rewards,
        "deposit_cash": deposit_cash,
        "bill_payment_cash": bill_cash,
        "rakuten_points": rakuten_points,
        "qr_rate": qr_rate,
        "bundled_value": bundled_value,
        "value_adjusted_total": value_adjusted_total,
        "annual_total": total * 12,
        "effective_annual": effective_total * 12,
        "value_adjusted_annual": value_adjusted_total * 12,
        **separation,
    }


def _unlimited_option(priced: dict[str, Any]) -> dict[str, Any]:
    rate = priced.get("qr_rate")
    return {
        "plan_id": priced["plan"]["id"],
        "plan_name": priced["plan"]["name"],
        "total": priced["total"],
        "billing_total": priced["billing_total"],
        "qr_points": priced["qr_points"],
        "cash_rewards": priced["cash_rewards"],
        "reward_total": priced["reward_total"],
        "qr_percent": rate["percent"] if rate else 0,
        "qr_wallet_label": rate["wallet_label"] if rate else None,
        "effective_total": priced["effective_total"],
        "effective_annual": priced["effective_annual"],
    }


def calculate_carrier_price(
    carrier_id: str,
    data_usage: str = "10gb",
    selected_discount_ids: list[str] | None = None,
    profile: dict[str, int | None] | None = None,
    plan_id: str | None = None,
    qr: dict[str, Any] | None = None,
    *,
    plan_manual: bool | None = None,
) -> dict[str, Any]:
    carrier = get_carrier_map().get(carrier_id)
    if carrier is None:
        raise InvalidUsageError(f"unknown carrier: {carrier_id!r}")

    data_gb = _parse_data_gb(data_usage)
    profile = profile or {"age": None, "line_count": None}
    selected_discount_ids = merge_tenure_auto_discounts(carrier_id, selected_discount_ids, profile)

    billing_auto_plan = _select_plan_for_billing_cheapest(
        carrier, data_usage, profile, selected_discount_ids, qr
    )
    if plan_id:
        manual = next((plan for plan in carrier.get("plans") or [] if plan["id"] == plan_id), None)
        if manual is not None:
            plan = manual
            is_manual = plan_manual if plan_manual is not None else True
        else:
            plan = billing_auto_plan
            is_manual = False
    else:
        plan = billing_auto_plan
        is_manual = False
    usage_auto_plan = billing_auto_plan

    unlimited_plans = [item for item in carrier.get("plans") or [] if item.get("data_gb_max") is None]
    unlimited_priced = [
        _price_for_plan(carrier, item, selected_discount_ids, profile, qr, data_gb)
        for item in unlimited_plans
    ]
    if unlimited_priced:
        best_unlimited = min(
            unlimited_priced,
            key=lambda item: (
                item["value_adjusted_total"],
                item["effective_total"],
                item["total"],
                item["plan"]["base_price"],
            ),
        )
    else:
        best_unlimited = None

    priced = _price_for_plan(carrier, plan, selected_discount_ids, profile, qr, data_gb)

    return {
        "carrier_id": carrier_id,
        "carrier_name": carrier["name"],
        "theme": carrier.get("theme", {"border": "border-gray-300", "bg": "bg-gray-50"}),
        "plan": plan,
        "plan_manual": is_manual,
        "auto_plan_id": usage_auto_plan["id"],
        "plan_under_capacity": is_manual and is_plan_under_capacity(plan, data_gb),
        "base_price": priced["base_price"],
        "discount_total": priced["discount_total"],
        "discount_capped": priced["discount_capped"],
        "applied_discounts": priced["applied_discounts"],
        "discount_eligibility": priced["discount_eligibility"],
        "resolved_discount_amounts": _build_resolved_discount_amounts(carrier, plan, profile, qr),
        "total": priced["total"],
        "annual_total": priced["annual_total"],
        "base_amount": priced["base_amount"],
        "option_amount": priced["option_amount"],
        "billing_discount_total": priced["billing_discount_total"],
        "billing_total": priced["billing_total"],
        "qr_points": priced["qr_points"],
        "cash_rewards": priced["cash_rewards"],
        "deposit_cash": priced.get("deposit_cash", 0),
        "bill_payment_cash": priced.get("bill_payment_cash", 0),
        "rakuten_points": priced.get("rakuten_points", 0),
        "reward_total": priced["reward_total"],
        "rewards": priced["rewards"],
        "qr_rate": priced["qr_rate"],
        "effective_total": priced["effective_total"],
        "effective_annual": priced["effective_annual"],
        "bundled_value": priced["bundled_value"],
        "bundled_services": plan.get("bundled_services") or [],
        "value_adjusted_total": priced["value_adjusted_total"],
        "value_adjusted_annual": priced["value_adjusted_annual"],
        "plan_quotes": build_plan_quotes(carrier, selected_discount_ids, profile, qr, data_gb),
        "unlimited_options": [_unlimited_option(item) for item in unlimited_priced],
        "best_unlimited": _unlimited_option(best_unlimited) if best_unlimited else None,
    }


def calculate_multi_carrier_lines(
    lines: list[dict[str, Any]],
    tenure_years: str | None = None,
    home_set_flags: dict[str, bool] | None = None,
    current: dict[str, Any] | None = None,
    default_carrier: str = "softbank",
) -> dict[str, Any]:
    """回線ごとに異なるキャリアを指定できる複数回線計算。"""
    if not lines:
        raise InvalidUsageError("at least one line is required")

    carriers = load_all_carriers()
    available = {carrier["id"] for carrier in carriers}
    if default_carrier not in available and carriers:
        default_carrier = carriers[0]["id"]

    family_discount_ids = build_family_discount_ids(carriers)
    carrier_map = {carrier["id"]: carrier for carrier in carriers}
    home_set_flags = home_set_flags or {}

    resolved_lines: list[tuple[str, dict[str, Any]]] = []
    for line in lines:
        carrier_id = line.get("carrier") or default_carrier
        if carrier_id not in available:
            raise InvalidUsageError(f"unknown carrier: {carrier_id!r}")
        resolved_lines.append((carrier_id, line))

    resolved_lines, billing_auto_indices = _assign_billing_auto_plans_for_carrier_groups(
        resolved_lines,
        tenure_years=tenure_years,
        home_set_flags=home_set_flags,
        default_carrier=default_carrier,
    )

    carrier_ids = list({carrier_id for carrier_id, _ in resolved_lines})
    carrier_line_counts: dict[str, int] = {}
    for carrier_id, _ in resolved_lines:
        carrier_line_counts[carrier_id] = carrier_line_counts.get(carrier_id, 0) + 1

    family_line_counts = build_family_line_counts_by_carrier(
        resolved_lines,
        carrier_map,
        carriers,
    )

    account_tenure = build_profile(tenure_years=tenure_years)["tenure_years"]
    total_lines = len(resolved_lines)

    line_results = []
    carrier_seen: dict[str, int] = {}
    for index, (carrier_id, line) in enumerate(resolved_lines):
        carrier_line_index = carrier_seen.get(carrier_id, 0)
        carrier_seen[carrier_id] = carrier_line_index + 1

        carrier = carrier_map[carrier_id]
        blocked_family = primary_blocked_family_discount_ids(
            carrier,
            carrier_line_index,
            family_discount_ids,
        )
        line_profile = {
            "tenure_years": account_tenure,
            "line_count": family_line_counts.get(
                carrier_id,
                carrier_line_counts.get(carrier_id, 1),
            ),
            "age": parse_optional_int(line.get("age"), "age", 0, MAX_AGE),
        }
        if blocked_family:
            line_profile["blocked_discount_ids"] = blocked_family

        line_discounts = list(line.get("discounts") or [])
        discounts_by_carrier = merge_home_set_discounts(
            {carrier_id: line_discounts},
            home_set_flags,
            carrier_ids,
        )
        selected_discounts = _discount_ids_for_line(
            discounts_by_carrier.get(carrier_id, []),
            blocked_family,
        )

        qr = build_qr_context(
            line.get("qr_paypay"),
            line.get("qr_dbarai"),
            line.get("qr_aupay"),
            paypay_card_tier=line.get("paypay_card_tier"),
            paypay_gold=line.get("paypay_gold"),
            paypay_gold_linked=line.get("paypay_gold_linked"),
            aupay_gold=line.get("aupay_gold"),
            dcard_tier=line.get("dcard_tier"),
            au_pay_card_bill=line.get("au_pay_card_bill"),
            au_jibun_bank=line.get("au_jibun_bank"),
            au_bill_payment_mode=line.get("au_bill_payment_mode"),
            au_pay_card_bank_is_jibun=line.get("au_pay_card_bank_is_jibun"),
            docomo_bill_dcard=line.get("docomo_bill_dcard"),
            au_jibun_bank_balance=line.get("au_jibun_bank_balance"),
        )

        result = calculate_carrier_price(
            carrier_id,
            data_usage=line.get("data_usage") or "10gb",
            selected_discount_ids=selected_discounts,
            profile=line_profile,
            plan_id=line.get("plan"),
            qr=qr,
            plan_manual=False if index in billing_auto_indices else None,
        )
        result["line_index"] = index
        result["carrier_line_index"] = carrier_line_index
        result["is_main_line"] = index == 0
        result["is_carrier_primary_line"] = carrier_line_index == 0
        result["line_label"] = "主回線" if index == 0 else f"{index + 1}回線目"
        line_results.append(result)

    totals = {
        "total": sum(item["total"] for item in line_results),
        "billing_total": sum(item["billing_total"] for item in line_results),
        "value_adjusted_total": sum(item["value_adjusted_total"] for item in line_results),
        "effective_total": sum(item["effective_total"] for item in line_results),
        "reward_total": sum(item["reward_total"] for item in line_results),
        "annual_total": sum(item["annual_total"] for item in line_results),
        "value_adjusted_annual": sum(item["value_adjusted_annual"] for item in line_results),
        "line_count": total_lines,
    }

    if current:
        totals["diff"] = totals["value_adjusted_total"] - current["monthly"]
        totals["annual_diff"] = totals["diff"] * 12

    has_qr = any(result["qr_points"] > 0 for result in line_results)
    primary_carrier = resolved_lines[0][0]

    return {
        "results": line_results,
        "lines": line_results,
        "totals": totals,
        "current": current,
        "best_saving": current["monthly"] - totals["value_adjusted_total"] if current else None,
        "has_qr": has_qr,
        "selected_carrier": primary_carrier,
        "carrier_ids": carrier_ids,
    }


def calculate_carrier_lines(
    carrier_id: str,
    lines: list[dict[str, Any]],
    tenure_years: str | None = None,
    home_set_flags: dict[str, bool] | None = None,
    carrier_ids: list[str] | None = None,
    current: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """同一キャリアの複数回線を計算する（後方互換ラッパー）。"""
    normalized = [{**line, "carrier": line.get("carrier") or carrier_id} for line in lines]
    result = calculate_multi_carrier_lines(
        normalized,
        tenure_years=tenure_years,
        home_set_flags=home_set_flags,
        current=current,
        default_carrier=carrier_id,
    )
    result["selected_carrier"] = carrier_id
    return result


def resolve_current_plan(
    carrier_id: str | None = None,
    plan_id: str | None = None,
    monthly_price: str | None = None,
) -> dict[str, Any] | None:
    """現在契約中の料金。実際の請求額が入力されていればプラン定価より優先する。"""
    price = parse_optional_int(monthly_price, "current_price", 0, MAX_CURRENT_PRICE)
    carrier = get_carrier_map().get(carrier_id) if carrier_id else None

    if carrier_id and carrier is None:
        raise InvalidUsageError(f"unknown carrier: {carrier_id!r}")

    plan = None
    if carrier and plan_id:
        # 旧プラン（提供終了）も現在の契約として選べる。比較先には使わない。
        selectable = [*carrier["plans"], *carrier.get("legacy_plans", [])]
        plan = next((item for item in selectable if item["id"] == plan_id), None)
        if plan is None:
            raise InvalidUsageError(f"unknown plan: {plan_id!r}")

    if price is None and plan is None:
        return None

    if price is not None:
        monthly = price
        source = "user_reported"
    else:
        monthly = plan["base_price"]
        source = "estimated_plan_base"

    return {
        "carrier_id": carrier["id"] if carrier else None,
        "carrier_name": carrier["name"] if carrier else "現在の契約",
        "plan_name": plan["name"] if plan else "入力した月額",
        "monthly": monthly,
        "billing_total": monthly,
        "annual": monthly * 12,
        "is_manual_price": price is not None,
        "source": source,
    }


def compare_carriers(
    carrier_ids: list[str],
    data_usage: str = "10gb",
    discounts_by_carrier: dict[str, list[str]] | None = None,
    profile: dict[str, int | None] | None = None,
    current: dict[str, Any] | None = None,
    plans_by_carrier: dict[str, str] | None = None,
    qr: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """複数キャリアを同一プロファイルで横並び比較するライブラリ関数。

    Web アプリ（app.py）の料金計算には使わない。`/api/calculate` および画面表示は
    `calculate_multi_carrier_lines`（回線ごとにキャリア・プラン・割引を指定）を使用する。

    同一通信量・同一 profile を各キャリアに適用し、最安キャリアを返す用途向け。
    """
    discounts_by_carrier = discounts_by_carrier or {}
    plans_by_carrier = plans_by_carrier or {}
    results = [
        calculate_carrier_price(
            carrier_id,
            data_usage=data_usage,
            selected_discount_ids=discounts_by_carrier.get(carrier_id, []),
            profile=profile,
            plan_id=plans_by_carrier.get(carrier_id),
            qr=qr,
        )
        for carrier_id in carrier_ids
    ]

    if not results:
        return {
            "results": [],
            "cheapest": None,
            "recommended": None,
            "annual_cheapest": None,
            "current": current,
            "best_saving": None,
            "has_qr": bool(qr and qr.get("has_qr")),
            "unlimited_comparison": [],
        }

    if current:
        for result in results:
            result["diff"] = result["value_adjusted_total"] - current["monthly"]
            result["annual_diff"] = result["diff"] * 12

    results.sort(key=lambda item: (item["value_adjusted_total"], item["effective_total"], item["total"]))
    cheapest = results[0]

    unlimited_comparison = []
    for result in results:
        if not result.get("best_unlimited"):
            continue
        options = sorted(result["unlimited_options"], key=lambda item: item["effective_total"])
        unlimited_comparison.append(
            {
                "carrier_id": result["carrier_id"],
                "carrier_name": result["carrier_name"],
                "theme": result["theme"],
                "options": options,
                "best": result["best_unlimited"],
            }
        )
    unlimited_comparison.sort(key=lambda item: (item["best"]["effective_total"], item["best"]["total"]))

    has_qr = bool(qr and qr.get("has_qr")) or any(result["qr_points"] > 0 for result in results)

    return {
        "results": results,
        "cheapest": cheapest,
        "recommended": cheapest,
        "annual_cheapest": cheapest["value_adjusted_annual"],
        "current": current,
        "best_saving": current["monthly"] - cheapest["value_adjusted_total"] if current else None,
        "has_qr": has_qr,
        "unlimited_comparison": unlimited_comparison,
    }


COMPARISON_CARRIER_IDS: tuple[str, ...] = (
    "softbank",
    "ymobile",
    "au",
    "uqmobile",
    "docomo",
    "ahamo",
    "rakuten",
)

_LINE_COMPARE_PRESERVE_KEYS: tuple[str, ...] = (
    "age",
    "data_usage",
    "qr_paypay",
    "qr_dbarai",
    "qr_aupay",
    "paypay_card_tier",
    "paypay_gold",
    "paypay_gold_linked",
    "aupay_gold",
    "dcard_tier",
    "au_pay_card_bill",
    "au_jibun_bank",
    "au_bill_payment_mode",
    "au_pay_card_bank_is_jibun",
    "docomo_bill_dcard",
    "au_jibun_bank_balance",
)


def _home_set_discount_id_set() -> frozenset[str]:
    return frozenset(
        discount_id
        for mapping in HOME_SET_GROUPS.values()
        for discount_id in mapping.values()
    )


def _carrier_comparison_rank(carrier_id: str) -> int:
    try:
        return COMPARISON_CARRIER_IDS.index(carrier_id)
    except ValueError:
        return len(COMPARISON_CARRIER_IDS)


def _card_discount_ids_for_carrier(line: dict[str, Any], carrier_id: str) -> list[str]:
    """カード保有条件からブランド固有の支払割 ID を導出する（他ブランドへ流用しない）。"""
    ids: list[str] = []
    if carrier_id in {"softbank", "ymobile"}:
        tier = normalize_paypay_card_tier(
            line.get("paypay_card_tier"),
            line.get("paypay_gold"),
        )
        if tier == "standard":
            ids.append("paypay_card")
        elif tier == "gold":
            ids.append("paypay_card_gold")
    if carrier_id == "docomo" and _is_truthy_flag(line.get("docomo_bill_dcard")):
        ids.append("d_card")
    if carrier_id in {"au", "uqmobile"}:
        mode = _normalize_au_bill_payment_mode(
            {
                "au_bill_payment_mode": line.get("au_bill_payment_mode"),
                "au_pay_card_bill": line.get("au_pay_card_bill"),
                "au_jibun_bank": line.get("au_jibun_bank"),
            }
        )
        if mode == "au_pay_card":
            ids.append("au_pay_card")
    return ids


def _age_auto_discount_ids(carrier: dict[str, Any], line: dict[str, Any]) -> list[str]:
    """年齢・期間限定など、カード/セット割以外で自動適用可能な割引。"""
    manual_opt_in = set(build_manual_opt_in_discount_ids())
    age = parse_optional_int(line.get("age"), "age", 0, MAX_AGE)
    ids: list[str] = []
    for discount in carrier.get("discounts") or []:
        discount_id = discount["id"]
        if discount_id in manual_opt_in:
            continue
        requirements = discount.get("requirements") or {}
        if requirements.get("plan_ids") or discount.get("line_tiers") or requirements.get("min_lines"):
            continue
        if requirements.get("min_tenure_years"):
            continue
        if "age_min" in requirements or "age_max" in requirements:
            if age is None:
                continue
            if requirements.get("age_min") is not None and age < requirements["age_min"]:
                continue
            if requirements.get("age_max") is not None and age > requirements["age_max"]:
                continue
            if (
                carrier.get("id") == "rakuten"
                and discount_id in RAKUTEN_ENTRY_REQUIRED_AGE_DISCOUNTS
            ):
                continue
            ids.append(discount_id)
        elif discount_id == "special_discount" and _is_discount_in_period(discount):
            ids.append(discount_id)
    return ids


def _resolve_exclusive_discount_ids(
    carrier: dict[str, Any],
    discount_ids: list[str],
) -> list[str]:
    """排他割引が両方選ばれた場合、固定回線セット割を優先する。"""
    home_set_ids = _home_set_discount_id_set()
    selected = list(dict.fromkeys(discount_ids))
    selected_set = set(selected)
    discount_map = {item["id"]: item for item in carrier.get("discounts") or []}

    changed = True
    while changed:
        changed = False
        for discount_id in list(selected_set):
            discount = discount_map.get(discount_id)
            if not discount:
                continue
            for other_id in discount.get("exclusive_with") or []:
                if other_id not in selected_set:
                    continue
                if discount_id in home_set_ids and other_id not in home_set_ids:
                    selected_set.discard(other_id)
                    changed = True
                elif other_id in home_set_ids and discount_id not in home_set_ids:
                    selected_set.discard(discount_id)
                    changed = True
                else:
                    selected_set.discard(other_id)
                    changed = True

    order = [item["id"] for item in carrier.get("discounts") or []]
    order_index = {discount_id: index for index, discount_id in enumerate(order)}
    return sorted(selected_set, key=lambda item: order_index.get(item, 999))


def _build_comparison_line_discounts(
    line: dict[str, Any],
    target_carrier_id: str,
    home_set_flags: dict[str, bool],
    line_count: int,
    carrier_map: dict[str, dict[str, Any]],
    family_discount_ids: dict[str, list[str]],
) -> list[str]:
    """他ブランド比較用に、入力条件からブランド固有割引のみ組み立てる。"""
    carrier = carrier_map[target_carrier_id]
    discounts: list[str] = []

    merged_home = merge_home_set_discounts(
        {target_carrier_id: []},
        home_set_flags,
        [target_carrier_id],
    )
    discounts.extend(merged_home.get(target_carrier_id, []))
    discounts.extend(_card_discount_ids_for_carrier(line, target_carrier_id))
    discounts.extend(_age_auto_discount_ids(carrier, line))

    if line_count >= 2:
        for family_id in family_discount_ids.get(target_carrier_id, []):
            if family_id not in discounts:
                discounts.append(family_id)

    return _resolve_exclusive_discount_ids(carrier, discounts)


def _preserve_line_for_comparison(line: dict[str, Any], target_carrier_id: str) -> dict[str, Any]:
    preserved = {key: line[key] for key in _LINE_COMPARE_PRESERVE_KEYS if key in line}
    preserved["carrier"] = target_carrier_id
    preserved["discounts"] = list(line.get("discounts") or [])
    if line.get("carrier") == target_carrier_id and line.get("plan"):
        preserved["plan"] = line["plan"]
    return preserved


def _remap_line_for_comparison(
    line: dict[str, Any],
    target_carrier_id: str,
    home_set_flags: dict[str, bool],
    line_count: int,
    carrier_map: dict[str, dict[str, Any]],
    family_discount_ids: dict[str, list[str]],
) -> dict[str, Any]:
    preserved = {key: line[key] for key in _LINE_COMPARE_PRESERVE_KEYS if key in line}
    preserved["carrier"] = target_carrier_id
    preserved["discounts"] = _build_comparison_line_discounts(
        line,
        target_carrier_id,
        home_set_flags,
        line_count,
        carrier_map,
        family_discount_ids,
    )
    return preserved


def _lines_for_brand_comparison(
    source_lines: list[dict[str, Any]],
    target_carrier_id: str,
    home_set_flags: dict[str, bool],
    carrier_map: dict[str, dict[str, Any]],
    family_discount_ids: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """全回線を同一ブランドへ置換。元が既に同一ブランドなら割引・プランを維持する。"""
    if not source_lines:
        raise InvalidUsageError("at least one line is required")

    all_same_carrier = all(
        (line.get("carrier") or target_carrier_id) == target_carrier_id for line in source_lines
    )
    line_count = len(source_lines)

    if all_same_carrier:
        return [_preserve_line_for_comparison(line, target_carrier_id) for line in source_lines]

    return [
        _remap_line_for_comparison(
            line,
            target_carrier_id,
            home_set_flags,
            line_count,
            carrier_map,
            family_discount_ids,
        )
        for line in source_lines
    ]


def _comparison_line_detail(line_result: dict[str, Any]) -> dict[str, Any]:
    plan = line_result.get("plan") or {}
    return {
        "line_index": line_result.get("line_index"),
        "plan_id": plan.get("id"),
        "plan_name": plan.get("name"),
        "billing_total": line_result.get("billing_total"),
        "reward_total": line_result.get("reward_total"),
        "effective_total": line_result.get("effective_total"),
        "applied_discounts": line_result.get("applied_discounts") or [],
        "rewards": line_result.get("rewards") or [],
        "bundled_services": line_result.get("bundled_services") or [],
        "bundled_value": line_result.get("bundled_value", 0),
    }


MAX_AXIS_COMBINATIONS = 4096

_AXIS_SORT_KEYS: dict[str, tuple[str, ...]] = {
    "billing": ("billing_total", "effective_total", "value_adjusted_total"),
    "effective": ("effective_total", "billing_total", "value_adjusted_total"),
    "value_adjusted": ("value_adjusted_total", "effective_total", "billing_total"),
}


def _eligible_plans_for_compare_line(
    carrier: dict[str, Any],
    line: dict[str, Any],
) -> list[dict[str, Any]]:
    """横断比較用。年齢・容量を満たす現行プラン一覧（legacy 除外）。"""
    carrier_id = carrier.get("id") or ""
    data_gb = _parse_data_gb(line.get("data_usage") or "10gb")
    age = parse_optional_int(line.get("age"), "age", 0, MAX_AGE)
    age_eligible: list[dict[str, Any]] = []
    for plan in carrier.get("plans") or []:
        if not _plan_age_eligible(plan, carrier_id, age):
            continue
        age_eligible.append(plan)

    if data_gb is None:
        unlimited = [plan for plan in age_eligible if _plan_capacity_gb(plan) is None]
        if unlimited:
            return unlimited
        capped = [plan for plan in age_eligible if _plan_capacity_gb(plan) is not None]
        return capped if capped else age_eligible

    eligible: list[dict[str, Any]] = []
    for plan in age_eligible:
        capacity = _plan_capacity_gb(plan)
        if capacity is not None and data_gb > capacity:
            continue
        eligible.append(plan)
    return eligible


def _select_plan_for_billing_cheapest(
    carrier: dict[str, Any],
    data_usage: str,
    profile: dict[str, int | None],
    selected_discount_ids: list[str] | None,
    qr: dict[str, Any] | None,
) -> dict[str, Any]:
    """利用条件を満たす eligible プランのうち billing_total 最安を選ぶ（STEP3 自動選択）。"""
    carrier_id = carrier.get("id") or ""
    line_for_eligible: dict[str, Any] = {"data_usage": data_usage}
    age = profile.get("age")
    if age is not None:
        line_for_eligible["age"] = str(age)
    eligible = _eligible_plans_for_compare_line(carrier, line_for_eligible)
    if not eligible:
        raise ValueError(f"carrier '{carrier_id}' has no eligible plans")

    data_gb = _parse_data_gb(data_usage)
    best_plan: dict[str, Any] | None = None
    best_key: tuple[Any, ...] | None = None
    for plan in eligible:
        priced = _price_for_plan(carrier, plan, selected_discount_ids, profile, qr, data_gb)
        key = (
            priced["billing_total"],
            priced["effective_total"],
            priced["value_adjusted_total"],
            plan["id"],
        )
        if best_key is None or key < best_key:
            best_key = key
            best_plan = plan
    assert best_plan is not None
    return best_plan


def _assign_billing_auto_plans_for_carrier_groups(
    resolved_lines: list[tuple[str, dict[str, Any]]],
    *,
    tenure_years: str | None,
    home_set_flags: dict[str, bool] | None,
    default_carrier: str,
) -> tuple[list[tuple[str, dict[str, Any]]], set[int]]:
    """同一キャリア2回線以上かつプラン未指定時、billing 軸最適構成を割り当てる。"""
    prepared: list[tuple[str, dict[str, Any]]] = [
        (carrier_id, dict(line)) for carrier_id, line in resolved_lines
    ]
    auto_indices: set[int] = set()
    groups: dict[str, list[int]] = {}
    for index, (carrier_id, line) in enumerate(prepared):
        if line.get("plan"):
            continue
        groups.setdefault(carrier_id, []).append(index)

    for carrier_id, indices in groups.items():
        if len(indices) < 2:
            continue
        brand_lines = [prepared[index][1] for index in indices]
        try:
            billing = find_best_plans_by_axis(
                carrier_id,
                brand_lines,
                tenure_years=tenure_years,
                home_set_flags=home_set_flags,
            )["billing"]
        except ValueError:
            continue
        plan_ids = list(billing.get("plan_ids") or [])
        if not plan_ids and billing.get("plan_id"):
            plan_ids = [billing["plan_id"]] * len(indices)
        if len(plan_ids) != len(indices):
            continue
        for index, plan_id in zip(indices, plan_ids):
            _, line = prepared[index]
            line["plan"] = plan_id
            auto_indices.add(index)
    return prepared, auto_indices


def _quick_line_plan_totals(
    carrier_id: str,
    line: dict[str, Any],
    plan_id: str,
    *,
    line_count: int,
    tenure_years: str | None,
    home_set_flags: dict[str, bool] | None,
) -> dict[str, int]:
    """組み合わせ枝刈り用の単回線概算（世帯回線数は family 段階の目安に使う）。"""
    profile = {
        "tenure_years": build_profile(tenure_years=tenure_years)["tenure_years"],
        "line_count": line_count,
        "age": parse_optional_int(line.get("age"), "age", 0, MAX_AGE),
    }
    qr = build_qr_context(
        line.get("qr_paypay"),
        line.get("qr_dbarai"),
        line.get("qr_aupay"),
        paypay_card_tier=line.get("paypay_card_tier"),
        paypay_gold=line.get("paypay_gold"),
        paypay_gold_linked=line.get("paypay_gold_linked"),
        aupay_gold=line.get("aupay_gold"),
        dcard_tier=line.get("dcard_tier"),
        au_pay_card_bill=line.get("au_pay_card_bill"),
        au_jibun_bank=line.get("au_jibun_bank"),
        au_bill_payment_mode=line.get("au_bill_payment_mode"),
        au_pay_card_bank_is_jibun=line.get("au_pay_card_bank_is_jibun"),
        docomo_bill_dcard=line.get("docomo_bill_dcard"),
        au_jibun_bank_balance=line.get("au_jibun_bank_balance"),
    )
    selected_discounts = merge_tenure_auto_discounts(
        carrier_id,
        list(line.get("discounts") or []),
        profile,
    )
    priced = calculate_carrier_price(
        carrier_id,
        data_usage=line.get("data_usage") or "10gb",
        selected_discount_ids=selected_discounts,
        profile=profile,
        plan_id=plan_id,
        qr=qr,
    )
    return {
        "billing_total": priced["billing_total"],
        "effective_total": priced["effective_total"],
        "value_adjusted_total": priced["value_adjusted_total"],
    }


def _prune_plan_ids_for_axis_search(
    carrier: dict[str, Any],
    line: dict[str, Any],
    *,
    carrier_id: str,
    line_count: int,
    tenure_years: str | None,
    home_set_flags: dict[str, bool] | None,
    max_per_line: int,
) -> list[str]:
    eligible = _eligible_plans_for_compare_line(carrier, line)
    if len(eligible) <= max_per_line:
        return [plan["id"] for plan in eligible]

    scored: list[dict[str, Any]] = []
    for plan in eligible:
        totals = _quick_line_plan_totals(
            carrier_id,
            line,
            plan["id"],
            line_count=line_count,
            tenure_years=tenure_years,
            home_set_flags=home_set_flags,
        )
        scored.append({"id": plan["id"], **totals})

    keep: set[str] = set()
    for metric in ("billing_total", "effective_total", "value_adjusted_total"):
        keep.add(min(scored, key=lambda item: (item[metric], item["id"]))["id"])
    for item in sorted(scored, key=lambda row: (row["billing_total"], row["id"])):
        keep.add(item["id"])
        if len(keep) >= max_per_line:
            break
    return sorted(keep)


def _intersection_plan_ids_for_all_lines(
    carrier: dict[str, Any],
    brand_lines: list[dict[str, Any]],
) -> list[str]:
    per_line_sets = [
        {plan["id"] for plan in _eligible_plans_for_compare_line(carrier, line)}
        for line in brand_lines
    ]
    if not per_line_sets:
        return []
    shared = set.intersection(*per_line_sets)
    return sorted(shared)


def _plan_combinations_for_axis_search(
    carrier: dict[str, Any],
    brand_lines: list[dict[str, Any]],
    *,
    carrier_id: str,
    tenure_years: str | None,
    home_set_flags: dict[str, bool] | None,
) -> list[tuple[str, ...]]:
    from itertools import product

    line_count = len(brand_lines)
    per_line_ids = [
        [plan["id"] for plan in _eligible_plans_for_compare_line(carrier, line)]
        for line in brand_lines
    ]
    if any(not ids for ids in per_line_ids):
        raise ValueError(f"no eligible plans for carrier '{carrier_id}'")

    product_size = 1
    for ids in per_line_ids:
        product_size *= len(ids)

    if product_size > MAX_AXIS_COMBINATIONS:
        pruned: list[list[str]] | None = None
        for max_per_line in (4, 3, 2, 1):
            candidate = [
                _prune_plan_ids_for_axis_search(
                    carrier,
                    line,
                    carrier_id=carrier_id,
                    line_count=line_count,
                    tenure_years=tenure_years,
                    home_set_flags=home_set_flags,
                    max_per_line=max_per_line,
                )
                for line in brand_lines
            ]
            size = 1
            for ids in candidate:
                size *= len(ids)
            if size <= MAX_AXIS_COMBINATIONS:
                pruned = candidate
                break
        if pruned is not None:
            per_line_ids = pruned
        else:
            shared = _intersection_plan_ids_for_all_lines(carrier, brand_lines)
            if shared:
                return [(plan_id,) * line_count for plan_id in shared]
            per_line_ids = [[ids[0]] for ids in per_line_ids]

    return list(product(*per_line_ids))


def _axis_metric_tuple(totals: dict[str, Any], axis: str) -> tuple[Any, ...]:
    keys = _AXIS_SORT_KEYS[axis]
    values: list[Any] = [totals[key] for key in keys]
    values.append(tuple(line.get("plan_id") or "" for line in totals.get("lines") or []))
    return tuple(values)


def _axis_quote_from_calc(calc_result: dict[str, Any]) -> dict[str, Any]:
    totals = calc_result["totals"]
    line_results = calc_result.get("lines") or []
    bundled_value = sum(item.get("bundled_value", 0) for item in line_results)
    line_details = [_comparison_line_detail(item) for item in line_results]
    plan_ids = [detail["plan_id"] for detail in line_details if detail.get("plan_id")]
    primary_plan = line_results[0]["plan"] if line_results else {}
    return {
        "plan_id": primary_plan.get("id"),
        "plan_name": primary_plan.get("name"),
        "plan_ids": plan_ids,
        "billing_total": totals["billing_total"],
        "reward_total": totals["reward_total"],
        "effective_total": totals["effective_total"],
        "value_adjusted_total": totals["value_adjusted_total"],
        "bundled_value": bundled_value,
        "lines": line_details,
    }


def find_best_plans_by_axis(
    carrier_id: str,
    brand_lines: list[dict[str, Any]],
    *,
    tenure_years: str | None = None,
    home_set_flags: dict[str, bool] | None = None,
) -> dict[str, dict[str, Any]]:
    """ブランド内で billing / effective / value_adjusted 各軸の最安プラン構成を求める。"""
    carrier = get_carrier_map()[carrier_id]
    combinations = _plan_combinations_for_axis_search(
        carrier,
        brand_lines,
        carrier_id=carrier_id,
        tenure_years=tenure_years,
        home_set_flags=home_set_flags,
    )

    best: dict[str, dict[str, Any] | None] = {
        "billing": None,
        "effective": None,
        "value_adjusted": None,
    }
    best_keys: dict[str, tuple[Any, ...] | None] = {
        axis: None for axis in best
    }

    for plan_ids in combinations:
        configured_lines = [
            {**line, "carrier": carrier_id, "plan": plan_id}
            for line, plan_id in zip(brand_lines, plan_ids)
        ]
        calc_result = calculate_multi_carrier_lines(
            configured_lines,
            tenure_years=tenure_years,
            home_set_flags=home_set_flags,
            default_carrier=carrier_id,
        )
        quote = _axis_quote_from_calc(calc_result)
        totals = {
            "billing_total": quote["billing_total"],
            "effective_total": quote["effective_total"],
            "value_adjusted_total": quote["value_adjusted_total"],
            "lines": quote["lines"],
        }
        for axis in best:
            metric_key = _axis_metric_tuple(totals, axis)
            if best_keys[axis] is None or metric_key < best_keys[axis]:
                best_keys[axis] = metric_key
                best[axis] = quote

    if any(quote is None for quote in best.values()):
        raise ValueError(f"no eligible plans for carrier '{carrier_id}'")

    return {
        axis: quote for axis, quote in best.items() if quote is not None
    }


def _comparison_entry_from_axis_quotes(
    carrier_id: str,
    carrier_name: str,
    axis_quotes: dict[str, dict[str, Any]],
    input_lines: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    billing = axis_quotes["billing"]
    effective = axis_quotes["effective"]
    value_adjusted = axis_quotes["value_adjusted"]
    return {
        "carrier_id": carrier_id,
        "carrier_name": carrier_name,
        "status": "ok",
        "error": None,
        "axis_quotes": axis_quotes,
        "billing_total": billing["billing_total"],
        "reward_total": effective["reward_total"],
        "effective_total": effective["effective_total"],
        "bundled_value": value_adjusted["bundled_value"],
        "value_adjusted_total": value_adjusted["value_adjusted_total"],
        "lines": effective["lines"],
        "input_lines": input_lines or [],
    }


def _comparison_entry_from_result(
    carrier_id: str,
    carrier_name: str,
    calc_result: dict[str, Any],
    input_lines: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    totals = calc_result["totals"]
    line_results = calc_result.get("lines") or []
    bundled_value = sum(item.get("bundled_value", 0) for item in line_results)
    return {
        "carrier_id": carrier_id,
        "carrier_name": carrier_name,
        "status": "ok",
        "error": None,
        "billing_total": totals["billing_total"],
        "reward_total": totals["reward_total"],
        "effective_total": totals["effective_total"],
        "bundled_value": bundled_value,
        "value_adjusted_total": totals["value_adjusted_total"],
        "lines": [_comparison_line_detail(item) for item in line_results],
        "input_lines": input_lines or [],
    }


def _comparison_error_entry(
    carrier_id: str,
    carrier_name: str,
    error: str,
    *,
    status: str = "error",
) -> dict[str, Any]:
    return {
        "carrier_id": carrier_id,
        "carrier_name": carrier_name,
        "status": status,
        "error": error,
        "billing_total": None,
        "reward_total": None,
        "effective_total": None,
        "bundled_value": None,
        "value_adjusted_total": None,
    }


def _pick_cheapest_comparison(
    comparisons: list[dict[str, Any]],
    primary_key: str,
    tie_break_keys: list[str],
    *,
    axis: str | None = None,
) -> dict[str, Any] | None:
    successful = [item for item in comparisons if item.get("status") == "ok"]
    if not successful:
        return None

    def sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
        values: list[Any] = [item[primary_key]]
        for key in tie_break_keys:
            if key == "carrier_id":
                values.append(_carrier_comparison_rank(item["carrier_id"]))
            else:
                values.append(item[key])
        return tuple(values)

    winner = min(successful, key=sort_key)
    if axis:
        axis_quote = (winner.get("axis_quotes") or {}).get(axis) or {}
        if axis_quote.get("plan_id"):
            winner["plan_id"] = axis_quote["plan_id"]
        if axis_quote.get("plan_name"):
            winner["plan_name"] = axis_quote["plan_name"]
        if axis_quote.get("plan_ids"):
            winner["plan_ids"] = axis_quote["plan_ids"]
    return winner


def compare_all_carriers_for_lines(
    lines: list[dict[str, Any]],
    tenure_years: str | None = None,
    home_set_flags: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """全ブランド横断比較。各ブランドへ全回線を置換し、3種類の最安を独立判定する。"""
    if not lines:
        raise InvalidUsageError("at least one line is required")

    carriers = load_all_carriers()
    carrier_map = {carrier["id"]: carrier for carrier in carriers}
    family_discount_ids = build_family_discount_ids(carriers)
    home_set_flags = home_set_flags or {}

    comparisons: list[dict[str, Any]] = []
    for carrier_id in COMPARISON_CARRIER_IDS:
        carrier = carrier_map.get(carrier_id)
        if carrier is None:
            comparisons.append(
                _comparison_error_entry(
                    carrier_id,
                    carrier_id,
                    f"unknown carrier: {carrier_id!r}",
                )
            )
            continue

        try:
            brand_lines = _lines_for_brand_comparison(
                lines,
                carrier_id,
                home_set_flags,
                carrier_map,
                family_discount_ids,
            )
            axis_quotes = find_best_plans_by_axis(
                carrier_id,
                brand_lines,
                tenure_years=tenure_years,
                home_set_flags=home_set_flags,
            )
            comparisons.append(
                _comparison_entry_from_axis_quotes(
                    carrier_id,
                    carrier["name"],
                    axis_quotes,
                    brand_lines,
                )
            )
        except InvalidUsageError as error:
            comparisons.append(
                _comparison_error_entry(carrier_id, carrier["name"], str(error))
            )
        except (ValueError, KeyError) as error:
            comparisons.append(
                _comparison_error_entry(
                    carrier_id,
                    carrier["name"],
                    str(error),
                    status="no_eligible_plan",
                )
            )

    comparison_complete = all(item.get("status") == "ok" for item in comparisons)

    result = {
        "comparisons": comparisons,
        "cheapest_billing": _pick_cheapest_comparison(
            comparisons,
            "billing_total",
            ["effective_total", "carrier_id"],
            axis="billing",
        ),
        "cheapest_effective": _pick_cheapest_comparison(
            comparisons,
            "effective_total",
            ["billing_total", "carrier_id"],
            axis="effective",
        ),
        "cheapest_value_adjusted": _pick_cheapest_comparison(
            comparisons,
            "value_adjusted_total",
            ["effective_total", "billing_total", "carrier_id"],
            axis="value_adjusted",
        ),
        "comparison_complete": comparison_complete,
    }

    from services.carrier_explanation import attach_explanations_to_compare_result

    attach_explanations_to_compare_result(result, lines, home_set_flags)
    return result
