"""キャリアごとの強み・注意点説明（ランキングには影響しない）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from services.calculator import _is_truthy_flag, _parse_data_gb

MAX_STRENGTHS = 3
MAX_CAUTIONS = 2

PARTIAL_CONFIDENCE_REWARD_IDS = frozenset(
    {"qr_reward", "docomo_poikatsu_reward"},
)


@dataclass
class ExplanationContext:
    entry: dict[str, Any]
    source_lines: list[dict[str, Any]]
    home_set_flags: dict[str, bool]
    all_comparisons: list[dict[str, Any]]
    cheapest_billing: dict[str, Any] | None
    cheapest_effective: dict[str, Any] | None
    cheapest_value_adjusted: dict[str, Any] | None
    comparison_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def carrier_id(self) -> str:
        return self.entry["carrier_id"]

    @property
    def lines(self) -> list[dict[str, Any]]:
        return self.entry.get("lines") or []

    @property
    def input_lines(self) -> list[dict[str, Any]]:
        return self.entry.get("input_lines") or self.source_lines


def _format_yen(amount: int) -> str:
    return f"{amount:,}円"


def _format_points(amount: int) -> str:
    return f"{amount:,}pt"


def _discount_totals(lines: list[dict[str, Any]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for line in lines:
        for item in line.get("applied_discounts") or []:
            discount_id = item["id"]
            totals[discount_id] = totals.get(discount_id, 0) + int(item["amount"])
    return totals


def _reward_entries(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line in lines:
        entries.extend(line.get("rewards") or [])
    return entries


def _reward_amount(lines: list[dict[str, Any]], reward_id: str) -> int:
    return sum(int(item["amount"]) for item in _reward_entries(lines) if item.get("id") == reward_id)


def _reward_amount_by_type(lines: list[dict[str, Any]], reward_type: str) -> int:
    return sum(
        int(item["amount"])
        for item in _reward_entries(lines)
        if item.get("type") == reward_type
    )


def _has_discount(lines: list[dict[str, Any]], discount_id: str) -> bool:
    return discount_id in _discount_totals(lines)


def _discount_amount(lines: list[dict[str, Any]], discount_id: str) -> int:
    return _discount_totals(lines).get(discount_id, 0)


def _has_plan(lines: list[dict[str, Any]], plan_id: str) -> bool:
    return any(line.get("plan_id") == plan_id for line in lines)


def _any_input_flag(lines: list[dict[str, Any]], key: str) -> bool:
    return any(_is_truthy_flag(line.get(key)) for line in lines)


def _data_usage_category(source_lines: list[dict[str, Any]]) -> str:
    """少容量/中容量/大容量/無制限志向。"""
    categories: list[str] = []
    for line in source_lines:
        usage = line.get("data_usage") or "10gb"
        if usage == "unlimited":
            categories.append("unlimited")
            continue
        try:
            gb = _parse_data_gb(usage)
        except Exception:
            gb = 10
        if gb is None:
            categories.append("unlimited")
        elif gb <= 3:
            categories.append("low")
        elif gb <= 20:
            categories.append("medium")
        elif gb < 50:
            categories.append("high")
        else:
            categories.append("unlimited")
    if "unlimited" in categories:
        return "unlimited"
    if "high" in categories:
        return "high"
    if "medium" in categories:
        return "medium"
    return "low"


def _strength(
    rule_id: str,
    category: str,
    message: str,
    priority: int,
    evidence: dict[str, Any] | None = None,
    *,
    confidence: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "rule_id": rule_id,
        "category": category,
        "message": message,
        "priority": priority,
    }
    if evidence:
        item["evidence"] = evidence
    if confidence:
        item["confidence"] = confidence
    return item


def _caution(rule_id: str, message: str, priority: int = 10) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "category": "CAUTION",
        "message": message,
        "priority": priority,
    }


def _evidence_amount(amount: int, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"amount": amount}
    payload.update(extra)
    return payload


def _confidence_for_reward(reward_id: str) -> str | None:
    return "partial" if reward_id in PARTIAL_CONFIDENCE_REWARD_IDS else None


# --- 共通: 最安説明 ---


def _cheapest_strengths(ctx: ExplanationContext) -> list[dict[str, Any]]:
    carrier_id = ctx.carrier_id
    strengths: list[dict[str, Any]] = []
    billing = ctx.cheapest_billing
    effective = ctx.cheapest_effective
    adjusted = ctx.cheapest_value_adjusted

    if not billing or not effective or not adjusted:
        return strengths

    same_all = (
        billing["carrier_id"] == effective["carrier_id"] == adjusted["carrier_id"] == carrier_id
    )
    if same_all:
        strengths.append(
            _strength(
                "cheapest_all_three",
                "PRICE",
                (
                    f"今回の条件では請求額・還元込み実質負担・付帯価値込みの"
                    f"いずれも最安（実質 {_format_yen(ctx.entry['effective_total'])}/月）です"
                ),
                100,
                _evidence_amount(
                    ctx.entry["effective_total"],
                    billing_total=ctx.entry["billing_total"],
                    value_adjusted_total=ctx.entry["value_adjusted_total"],
                ),
            )
        )
        return strengths

    if billing.get("carrier_id") == carrier_id:
        strengths.append(
            _strength(
                "cheapest_billing",
                "PRICE",
                f"今回の条件では実際の請求額が最安（{_format_yen(ctx.entry['billing_total'])}/月）です",
                100,
                _evidence_amount(ctx.entry["billing_total"], metric="billing_total"),
            )
        )
    if effective.get("carrier_id") == carrier_id:
        strengths.append(
            _strength(
                "cheapest_effective",
                "PRICE",
                (
                    f"今回の条件では還元込み実質負担が最安"
                    f"（{_format_yen(ctx.entry['effective_total'])}/月）です"
                ),
                100,
                _evidence_amount(ctx.entry["effective_total"], metric="effective_total"),
            )
        )
    if adjusted.get("carrier_id") == carrier_id:
        strengths.append(
            _strength(
                "cheapest_value_adjusted",
                "BUNDLED",
                (
                    f"今回の条件では付帯価値込みで最安"
                    f"（{_format_yen(ctx.entry['value_adjusted_total'])}/月）です"
                ),
                100,
                _evidence_amount(
                    ctx.entry["value_adjusted_total"],
                    metric="value_adjusted_total",
                ),
            )
        )
    return strengths


# --- SoftBank ---


def _softbank_strengths(ctx: ExplanationContext) -> list[dict[str, Any]]:
    lines = ctx.lines
    strengths: list[dict[str, Any]] = []

    qr_amount = _reward_amount(lines, "qr_reward")
    if _has_plan(lines, "paytoku2") and qr_amount > 0:
        strengths.append(
            _strength(
                "sb_paypay_reward",
                "REWARD",
                f"PayPay利用により{_format_points(qr_amount)}相当の還元を受けられます",
                90,
                _evidence_amount(qr_amount, reward_id="qr_reward", type="POINT"),
                confidence=_confidence_for_reward("qr_reward"),
            )
        )

    if _has_plan(lines, "paytoku2") and _any_input_flag(ctx.input_lines, "paypay_gold_linked"):
        strengths.append(
            _strength(
                "sb_gold_linked",
                "REWARD",
                "PayPayカード ゴールド連携によりペイトク2の高還元条件を活かしています",
                85,
                confidence="partial",
            )
        )

    family_amount = _discount_amount(lines, "family_discount")
    if family_amount > 0:
        strengths.append(
            _strength(
                "sb_family",
                "FAMILY",
                f"家族割により月{_format_yen(family_amount)}割引されています",
                80,
                _evidence_amount(family_amount, discount_id="family_discount"),
            )
        )

    home_amount = _discount_amount(lines, "home_fiber_set")
    if home_amount > 0:
        strengths.append(
            _strength(
                "sb_home",
                "HOME",
                f"固定回線とのセット割により月{_format_yen(home_amount)}割引されています",
                80,
                _evidence_amount(home_amount, discount_id="home_fiber_set"),
            )
        )

    for discount_id, label in (
        ("paypay_card", "PayPayカード割"),
        ("paypay_card_gold", "PayPayカード ゴールド割"),
    ):
        amount = _discount_amount(lines, discount_id)
        if amount > 0:
            strengths.append(
                _strength(
                    f"sb_{discount_id}",
                    "CARD",
                    f"{label}により月{_format_yen(amount)}割引されています",
                    75,
                    _evidence_amount(amount, discount_id=discount_id),
                )
            )
    return strengths


def _softbank_cautions(ctx: ExplanationContext) -> list[dict[str, Any]]:
    lines = ctx.lines
    cautions: list[dict[str, Any]] = []

    if _has_plan(lines, "paytoku2"):
        qr_amount = _reward_amount(lines, "qr_reward")
        if qr_amount == 0:
            cautions.append(
                _caution(
                    "sb_paypay_dependency",
                    "PayPay利用額が少ない、または還元条件を満たしていない場合、"
                    "実質負担額が増える可能性があります",
                    90,
                )
            )
        elif qr_amount < 1500:
            cautions.append(
                _caution(
                    "sb_paypay_low_reward",
                    "PayPay還元が上限まで活かされていないため、"
                    "利用額が減ると実質負担額が増える可能性があります",
                    85,
                )
            )

    has_family = _has_discount(lines, "family_discount")
    has_home = _has_discount(lines, "home_fiber_set")
    has_card = _has_discount(lines, "paypay_card") or _has_discount(lines, "paypay_card_gold")
    if not has_family and not has_home and not has_card:
        cautions.append(
            _caution(
                "sb_no_major_discounts",
                "家族割・固定回線セット・カード割引を利用しない場合、"
                "請求額が他プランより高くなる可能性があります",
                70,
            )
        )
    return cautions


# --- Y!mobile ---


def _ymobile_strengths(ctx: ExplanationContext) -> list[dict[str, Any]]:
    lines = ctx.lines
    strengths: list[dict[str, Any]] = []

    family_amount = _discount_amount(lines, "family_discount")
    if family_amount > 0:
        strengths.append(
            _strength(
                "ym_family",
                "FAMILY",
                f"家族割引により月{_format_yen(family_amount)}割引されています",
                80,
                _evidence_amount(family_amount, discount_id="family_discount"),
            )
        )

    home_amount = _discount_amount(lines, "hikari_set")
    if home_amount > 0:
        strengths.append(
            _strength(
                "ym_home",
                "HOME",
                f"おうち割 光セットにより月{_format_yen(home_amount)}割引されています",
                80,
                _evidence_amount(home_amount, discount_id="hikari_set"),
            )
        )

    for discount_id, label in (
        ("paypay_card", "PayPayカード割"),
        ("paypay_card_gold", "PayPayカード ゴールド割"),
    ):
        amount = _discount_amount(lines, discount_id)
        if amount > 0:
            strengths.append(
                _strength(
                    f"ym_{discount_id}",
                    "CARD",
                    f"{label}により月{_format_yen(amount)}割引されています",
                    75,
                    _evidence_amount(amount, discount_id=discount_id),
                )
            )

    softbank = ctx.comparison_by_id.get("softbank")
    if softbank and softbank.get("status") == "ok":
        if ctx.entry["billing_total"] < softbank["billing_total"]:
            diff = softbank["billing_total"] - ctx.entry["billing_total"]
            strengths.append(
                _strength(
                    "ym_lower_billing_than_softbank",
                    "PRICE",
                    f"同条件のSoftBankより請求額が月{_format_yen(diff)}低い結果です",
                    70,
                    _evidence_amount(diff, compared_carrier="softbank"),
                )
            )
    return strengths


def _ymobile_cautions(ctx: ExplanationContext) -> list[dict[str, Any]]:
    lines = ctx.lines
    cautions: list[dict[str, Any]] = []

    if len(ctx.source_lines) >= 2:
        cautions.append(
            _caution(
                "ym_primary_no_family",
                "Y!mobileの家族割引は主回線には適用されず、副回線向けの割引です",
                80,
            )
        )

    if _has_discount(lines, "hikari_set") and _has_discount(lines, "family_discount"):
        cautions.append(
            _caution(
                "ym_exclusive_home_family",
                "光セット割と家族割引は同時に適用できません",
                85,
            )
        )

    if _data_usage_category(ctx.source_lines) == "unlimited":
        cautions.append(
            _caution(
                "ym_unlimited_limited",
                "大容量・無制限利用では対象プランや容量制限を確認してください",
                60,
            )
        )
    return cautions


# --- au ---


def _au_strengths(ctx: ExplanationContext) -> list[dict[str, Any]]:
    lines = ctx.lines
    strengths: list[dict[str, Any]] = []

    qr_amount = _reward_amount(lines, "qr_reward")
    if qr_amount > 0:
        strengths.append(
            _strength(
                "au_qr_reward",
                "REWARD",
                f"au PAY等の利用により{_format_points(qr_amount)}相当の還元を受けられます",
                90,
                _evidence_amount(qr_amount, reward_id="qr_reward", type="POINT"),
                confidence=_confidence_for_reward("qr_reward"),
            )
        )

    bill_cash = _reward_amount(lines, "au_bill_payment_cash")
    if bill_cash > 0:
        strengths.append(
            _strength(
                "au_bill_payment_cash",
                "REWARD",
                f"通信料お支払い条件により{_format_yen(bill_cash)}の現金還元があります",
                88,
                _evidence_amount(bill_cash, reward_id="au_bill_payment_cash", type="CASH"),
            )
        )

    deposit_cash = _reward_amount(lines, "au_deposit_cash")
    if deposit_cash > 0:
        strengths.append(
            _strength(
                "au_deposit_cash",
                "REWARD",
                f"銀行あずけて条件により{_format_yen(deposit_cash)}の現金還元があります",
                86,
                _evidence_amount(deposit_cash, reward_id="au_deposit_cash", type="CASH"),
            )
        )

    family_amount = _discount_amount(lines, "family_plus")
    if family_amount > 0:
        strengths.append(
            _strength(
                "au_family",
                "FAMILY",
                f"家族割プラスにより月{_format_yen(family_amount)}割引されています",
                80,
                _evidence_amount(family_amount, discount_id="family_plus"),
            )
        )

    smart_amount = _discount_amount(lines, "smart_value")
    if smart_amount > 0:
        strengths.append(
            _strength(
                "au_smart_value",
                "HOME",
                f"auスマートバリューにより月{_format_yen(smart_amount)}割引されています",
                80,
                _evidence_amount(smart_amount, discount_id="smart_value"),
            )
        )

    billing_cheapest = ctx.cheapest_billing
    effective_cheapest = ctx.cheapest_effective
    if (
        billing_cheapest
        and effective_cheapest
        and billing_cheapest["carrier_id"] != ctx.carrier_id
        and effective_cheapest["carrier_id"] == ctx.carrier_id
    ):
        strengths.append(
            _strength(
                "au_effective_flip",
                "REWARD",
                (
                    f"請求額は最安ではありませんが、還元込み実質負担"
                    f"（{_format_yen(ctx.entry['effective_total'])}/月）は最安です"
                ),
                95,
                _evidence_amount(ctx.entry["effective_total"], metric="effective_total"),
            )
        )
    return strengths


def _au_cautions(ctx: ExplanationContext) -> list[dict[str, Any]]:
    lines = ctx.lines
    cautions: list[dict[str, Any]] = []

    reward_types = {
        item.get("type")
        for item in _reward_entries(lines)
        if int(item.get("amount") or 0) > 0
    }
    if len(reward_types) > 1 or (
        _reward_amount(lines, "au_bill_payment_cash") > 0
        and _reward_amount(lines, "au_deposit_cash") > 0
    ):
        cautions.append(
            _caution(
                "au_complex_rewards",
                "マネ活2は通信料支払方法・銀行残高など複数条件に依存します",
                85,
            )
        )

    if _reward_amount(lines, "au_bill_payment_cash") > 0:
        cautions.append(
            _caution(
                "au_bill_payment_dependency",
                "通信料の支払方法を変更すると現金還元額が変わる場合があります",
                80,
            )
        )
    elif _reward_amount(lines, "au_deposit_cash") > 0:
        cautions.append(
            _caution(
                "au_deposit_dependency",
                "銀行残高条件を満たさない場合、あずけて特典は適用されません",
                75,
            )
        )
    return cautions


# --- UQ mobile ---


def _uqmobile_strengths(ctx: ExplanationContext) -> list[dict[str, Any]]:
    lines = ctx.lines
    strengths: list[dict[str, Any]] = []

    for discount_id, label in (
        ("family_set", "家族セット割"),
        ("home_set", "自宅セット割"),
        ("au_pay_card", "au PAY カードお支払い割"),
    ):
        amount = _discount_amount(lines, discount_id)
        if amount > 0:
            strengths.append(
                _strength(
                    f"uq_{discount_id}",
                    "FAMILY" if discount_id == "family_set" else "HOME" if discount_id == "home_set" else "CARD",
                    f"{label}により月{_format_yen(amount)}割引されています",
                    80,
                    _evidence_amount(amount, discount_id=discount_id),
                )
            )

    data_cat = _data_usage_category(ctx.source_lines)
    if data_cat in {"medium", "low"}:
        others = [
            item["billing_total"]
            for item in ctx.all_comparisons
            if item.get("status") == "ok" and item["carrier_id"] != ctx.carrier_id
        ]
        if others and ctx.entry["billing_total"] <= min(others):
            strengths.append(
                _strength(
                    "uq_mid_capacity_price",
                    "DATA",
                    "中容量利用で請求額が比較的抑えられる結果です",
                    50,
                    _evidence_amount(ctx.entry["billing_total"], metric="billing_total"),
                )
            )
    return strengths


def _uqmobile_cautions(ctx: ExplanationContext) -> list[dict[str, Any]]:
    lines = ctx.lines
    cautions: list[dict[str, Any]] = []

    if _has_plan(lines, "komikomi_value"):
        cautions.append(
            _caution(
                "uq_komikomi_family_excluded",
                "コミコミプランバリューは家族セット割の自回線割引対象外です",
                85,
            )
        )

    if _has_discount(lines, "home_set") and _has_discount(lines, "family_set"):
        cautions.append(
            _caution(
                "uq_exclusive_home_family",
                "自宅セット割と家族セット割は同時に適用できません",
                85,
            )
        )

    if _data_usage_category(ctx.source_lines) == "unlimited":
        cautions.append(
            _caution(
                "uq_unlimited_check",
                "無制限利用を主目的とする場合、対象プラン条件を確認してください",
                60,
            )
        )
    return cautions


# --- docomo ---


def _docomo_strengths(ctx: ExplanationContext) -> list[dict[str, Any]]:
    lines = ctx.lines
    strengths: list[dict[str, Any]] = []

    poikatsu = _reward_amount(lines, "docomo_poikatsu_reward")
    if poikatsu > 0:
        strengths.append(
            _strength(
                "docomo_poikatsu",
                "REWARD",
                f"d払い利用により{_format_points(poikatsu)}相当の還元を受けられます",
                90,
                _evidence_amount(
                    poikatsu,
                    reward_id="docomo_poikatsu_reward",
                    type="POINT",
                ),
                confidence=_confidence_for_reward("docomo_poikatsu_reward"),
            )
        )

    for discount_id, label in (
        ("everyone_docomo", "みんなドコモ割"),
        ("d_card", "dカードお支払割"),
        ("docomo_hikari_set", "ドコモ光セット割"),
        ("long_term", "長期利用割"),
    ):
        amount = _discount_amount(lines, discount_id)
        if amount > 0:
            cat = "FAMILY" if discount_id == "everyone_docomo" else "HOME" if "hikari" in discount_id else "CARD" if discount_id == "d_card" else "PRICE"
            strengths.append(
                _strength(
                    f"docomo_{discount_id}",
                    cat,
                    f"{label}により月{_format_yen(amount)}割引されています",
                    80,
                    _evidence_amount(amount, discount_id=discount_id),
                )
            )
    return strengths


def _docomo_cautions(ctx: ExplanationContext) -> list[dict[str, Any]]:
    lines = ctx.lines
    cautions: list[dict[str, Any]] = []

    if _has_plan(lines, "docomo_poikatsu_max"):
        if _reward_amount(lines, "docomo_poikatsu_reward") == 0:
            cautions.append(
                _caution(
                    "docomo_poikatsu_low",
                    "d払い利用額が少ない場合、ポイ活MAXの還元メリットは限定的です",
                    85,
                )
            )

    if _has_discount(lines, "d_card") and _any_input_flag(ctx.input_lines, "dcard_tier"):
        tier = next(
            (line.get("dcard_tier") or "standard" for line in ctx.input_lines),
            "standard",
        )
        if tier != "standard":
            cautions.append(
                _caution(
                    "docomo_dcard_tier",
                    "dカード券種によって還元率・割引額が異なります",
                    70,
                )
            )

    plan_ids = {line.get("plan_id") for line in lines}
    if plan_ids & {"docomo_mini", "docomo_mini_10gb"}:
        cautions.append(
            _caution(
                "docomo_mini_family_count_only",
                "ドコモ mini はみんなドコモ割の人数カウントのみで自回線割引はありません",
                75,
            )
        )
    return cautions


# --- ahamo ---


def _ahamo_strengths(ctx: ExplanationContext) -> list[dict[str, Any]]:
    lines = ctx.lines
    strengths: list[dict[str, Any]] = []

    bundled = ctx.entry.get("bundled_value") or 0
    if bundled > 0:
        services = []
        for line in lines:
            services.extend(line.get("bundled_services") or [])
        names = "・".join(dict.fromkeys(item.get("name", "付帯サービス") for item in services))
        strengths.append(
            _strength(
                "ahamo_bundled",
                "BUNDLED",
                f"{names}（{_format_yen(bundled)}相当込み）がプランに含まれています",
                60,
                _evidence_amount(bundled, metric="bundled_value"),
            )
        )

    others = [
        item["billing_total"]
        for item in ctx.all_comparisons
        if item.get("status") == "ok" and item["carrier_id"] != ctx.carrier_id
    ]
    data_cat = _data_usage_category(ctx.source_lines)
    if data_cat in {"medium", "high"} and others and ctx.entry["billing_total"] <= min(others):
        strengths.append(
            _strength(
                "ahamo_capacity_price",
                "DATA",
                f"中～大容量利用で請求額が比較的抑えられる結果です（{_format_yen(ctx.entry['billing_total'])}/月）",
                55,
                _evidence_amount(ctx.entry["billing_total"], metric="billing_total"),
            )
        )

    if not strengths or len(strengths) < MAX_STRENGTHS:
        strengths.append(
            _strength(
                "ahamo_simplicity",
                "SIMPLICITY",
                "割引オプションが少なく、料金構造が比較的シンプルです",
                30,
            )
        )
    return strengths


def _ahamo_cautions(ctx: ExplanationContext) -> list[dict[str, Any]]:
    cautions: list[dict[str, Any]] = []

    cautions.append(
        _caution(
            "ahamo_no_family_self",
            "みんなドコモ割の人数カウントには加わりますが、自回線割引はありません",
            80,
        )
    )

    if not _discount_totals(ctx.lines):
        cautions.append(
            _caution(
                "ahamo_no_home_discount",
                "光セット等の直接値引きはahamoにはありません",
                70,
            )
        )

    effective_cheapest = ctx.cheapest_effective
    if effective_cheapest and effective_cheapest["carrier_id"] != ctx.carrier_id:
        if _reward_amount_by_type(ctx.lines, "POINT") == 0:
            cautions.append(
                _caution(
                    "ahamo_no_point_rewards",
                    "ポイント還元型プランと比較すると、実質負担額に差が出る場合があります",
                    65,
                )
            )
    return cautions


# --- Rakuten ---


def _rakuten_strengths(ctx: ExplanationContext) -> list[dict[str, Any]]:
    lines = ctx.lines
    strengths: list[dict[str, Any]] = []

    usage_points = _reward_amount(lines, "rakuten_mobile_usage_point")
    if usage_points > 0:
        strengths.append(
            _strength(
                "rakuten_usage_point",
                "REWARD",
                f"楽天モバイル利用料金から{_format_points(usage_points)}が還元されます",
                85,
                _evidence_amount(
                    usage_points,
                    reward_id="rakuten_mobile_usage_point",
                    type="POINT",
                ),
            )
        )

    data_cat = _data_usage_category(ctx.source_lines)
    if data_cat == "unlimited":
        others = [
            item["billing_total"]
            for item in ctx.all_comparisons
            if item.get("status") == "ok" and item["carrier_id"] != ctx.carrier_id
        ]
        if others and ctx.entry["billing_total"] <= min(others):
            strengths.append(
                _strength(
                    "rakuten_unlimited_billing",
                    "DATA",
                    "大容量利用でも請求額を抑えやすい結果です",
                    70,
                    _evidence_amount(ctx.entry["billing_total"], metric="billing_total"),
                )
            )
    return strengths


def _rakuten_cautions(ctx: ExplanationContext) -> list[dict[str, Any]]:
    cautions: list[dict[str, Any]] = []

    billing = ctx.cheapest_billing
    effective = ctx.cheapest_effective
    if (
        billing
        and effective
        and billing.get("carrier_id") == ctx.carrier_id
        and effective.get("carrier_id") != ctx.carrier_id
    ):
        other = effective
        cautions.append(
            _caution(
                "rakuten_billing_not_effective",
                (
                    f"請求額は最安ですが、ポイント・現金還元まで含めると"
                    f"{other['carrier_name']}の方が実質負担は低くなります"
                    f"（{_format_yen(other['effective_total'])}/月）"
                ),
                95,
            )
        )
    return cautions


CARRIER_STRENGTH_BUILDERS: dict[str, Callable[[ExplanationContext], list[dict[str, Any]]]] = {
    "softbank": _softbank_strengths,
    "ymobile": _ymobile_strengths,
    "au": _au_strengths,
    "uqmobile": _uqmobile_strengths,
    "docomo": _docomo_strengths,
    "ahamo": _ahamo_strengths,
    "rakuten": _rakuten_strengths,
}

CARRIER_CAUTION_BUILDERS: dict[str, Callable[[ExplanationContext], list[dict[str, Any]]]] = {
    "softbank": _softbank_cautions,
    "ymobile": _ymobile_cautions,
    "au": _au_cautions,
    "uqmobile": _uqmobile_cautions,
    "docomo": _docomo_cautions,
    "ahamo": _ahamo_cautions,
    "rakuten": _rakuten_cautions,
}


def _impact_score(item: dict[str, Any]) -> int:
    evidence = item.get("evidence") or {}
    return int(evidence.get("amount") or 0)


def _sort_explanations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (-int(item.get("priority") or 0), -_impact_score(item), item.get("rule_id") or ""),
    )


def _limit(items: list[dict[str, Any]], maximum: int) -> list[dict[str, Any]]:
    trimmed = _sort_explanations(items)[:maximum]
    for item in trimmed:
        item.pop("priority", None)
    return trimmed


def build_carrier_explanations(
    entry: dict[str, Any],
    source_lines: list[dict[str, Any]],
    home_set_flags: dict[str, bool],
    compare_result: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if entry.get("status") != "ok":
        return [], []

    ctx = ExplanationContext(
        entry=entry,
        source_lines=source_lines,
        home_set_flags=home_set_flags,
        all_comparisons=compare_result.get("comparisons") or [],
        cheapest_billing=compare_result.get("cheapest_billing"),
        cheapest_effective=compare_result.get("cheapest_effective"),
        cheapest_value_adjusted=compare_result.get("cheapest_value_adjusted"),
        comparison_by_id={
            item["carrier_id"]: item for item in compare_result.get("comparisons") or []
        },
    )

    strengths: list[dict[str, Any]] = []
    strengths.extend(_cheapest_strengths(ctx))
    builder = CARRIER_STRENGTH_BUILDERS.get(ctx.carrier_id)
    if builder:
        strengths.extend(builder(ctx))

    caution_builder = CARRIER_CAUTION_BUILDERS.get(ctx.carrier_id)
    cautions = caution_builder(ctx) if caution_builder else []

    return _limit(strengths, MAX_STRENGTHS), _limit(cautions, MAX_CAUTIONS)


def attach_explanations_to_compare_result(
    compare_result: dict[str, Any],
    source_lines: list[dict[str, Any]],
    home_set_flags: dict[str, bool] | None = None,
) -> None:
    """compare_result の comparisons に strengths / cautions を付与（インプレース）。"""
    home_set_flags = home_set_flags or {}
    ranking_snapshot = {
        "cheapest_billing": compare_result.get("cheapest_billing"),
        "cheapest_effective": compare_result.get("cheapest_effective"),
        "cheapest_value_adjusted": compare_result.get("cheapest_value_adjusted"),
    }

    for entry in compare_result.get("comparisons") or []:
        strengths, cautions = build_carrier_explanations(
            entry,
            source_lines,
            home_set_flags,
            compare_result,
        )
        entry["strengths"] = strengths
        entry["cautions"] = cautions

    for key, value in ranking_snapshot.items():
        if compare_result.get(key) != value:
            raise RuntimeError(f"explanation engine must not modify {key}")
