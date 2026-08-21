import logging
import re
import sys

from flask import Flask, jsonify, render_template, request

from config import load_config
from services.calculator import (
    HOME_SET_GROUPS,
    InvalidUsageError,
    build_account_ui_visibility,
    build_home_set_discount_groups,
    build_simulator_ui_config,
    calculate_multi_carrier_lines,
    compare_all_carriers_for_lines,
    infer_home_set_flags,
    is_checked_flag,
    normalize_paypay_card_tier,
    resolve_current_plan,
)
from services.current_savings import attach_current_savings_to_compare_result
from services.data_loader import get_carrier_map, load_all_carriers

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.update(load_config())


def _configure_logging() -> None:
    level = logging.DEBUG if app.config.get("DEBUG") else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _is_api_request() -> bool:
    return request.path.startswith("/api/")


def _register_error_handlers(application: Flask) -> None:
    @application.errorhandler(404)
    def not_found(_error):
        if _is_api_request():
            return jsonify(
                {"error": "not_found", "message": "リソースが見つかりません"}
            ), 404
        return render_template("errors/404.html"), 404

    @application.errorhandler(500)
    def internal_server_error(_error):
        logger.exception("Unhandled server error")
        if _is_api_request():
            return jsonify(
                {
                    "error": "internal_error",
                    "message": "比較結果を取得できませんでした",
                }
            ), 500
        return render_template("errors/500.html"), 500


def _register_security_headers(application: Flask) -> None:
    @application.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        return response


def _register_context_processors(application: Flask) -> None:
    @application.context_processor
    def inject_site_context():
        from services.calculator import build_pricing_as_of_label

        carriers = load_all_carriers()
        official_links = [
            {
                "id": carrier["id"],
                "name": carrier["name"],
                "url": carrier["official_url"],
            }
            for carrier in sorted(
                carriers,
                key=lambda item: item.get("display_order", 99),
            )
            if carrier.get("official_url")
        ]
        return {
            "site_pricing_label": build_pricing_as_of_label(carriers),
            "carrier_official_links": official_links,
            "robots_noindex": application.config.get("ROBOTS_NOINDEX", False),
        }


_configure_logging()
_register_error_handlers(app)
_register_security_headers(app)
_register_context_processors(app)

DEFAULT_DATA_USAGE = "10gb"
DEFAULT_CARRIER = "softbank"
MAX_LINES = 10
LINE_FIELD_PATTERN = re.compile(r"^lines\[(\d+)\]\[(.+)\]$")


def _parse_line_indices() -> list[int]:
    indices: set[int] = set()
    for key in request.values:
        match = LINE_FIELD_PATTERN.match(key)
        if match:
            indices.add(int(match.group(1)))
    return sorted(indices)


def _resolve_carrier(raw: str | None, available_ids: list[str], fallback: str) -> str:
    if raw in available_ids:
        return raw
    if fallback in available_ids:
        return fallback
    return available_ids[0] if available_ids else DEFAULT_CARRIER


def _parse_line(index: int, available_ids: list[str], fallback_carrier: str) -> dict:
    prefix = f"lines[{index}]"
    data_unlimited = is_checked_flag(request.values.get(f"{prefix}[data_unlimited]"))
    raw_usage = request.values.get(f"{prefix}[data_usage]", DEFAULT_DATA_USAGE)
    data_usage = "unlimited" if data_unlimited else raw_usage

    return {
        "carrier": _resolve_carrier(
            request.values.get(f"{prefix}[carrier]"),
            available_ids,
            fallback_carrier,
        ),
        "age": request.values.get(f"{prefix}[age]"),
        "data_usage": data_usage,
        "plan": request.values.get(f"{prefix}[plan]"),
        "discounts": request.values.getlist(f"{prefix}[discounts]"),
        "qr_paypay": request.values.get(f"{prefix}[qr_paypay]"),
        "qr_dbarai": request.values.get(f"{prefix}[qr_dbarai]"),
        "qr_aupay": request.values.get(f"{prefix}[qr_aupay]"),
        "paypay_card_tier": normalize_paypay_card_tier(
            request.values.get(f"{prefix}[paypay_card_tier]"),
            request.values.get(f"{prefix}[paypay_gold]"),
        )
        or None,
        "paypay_gold_linked": request.values.get(f"{prefix}[paypay_gold_linked]"),
        "aupay_gold": request.values.get(f"{prefix}[aupay_gold]"),
        "dcard_tier": request.values.get(f"{prefix}[dcard_tier]"),
        "au_pay_card_bill": request.values.get(f"{prefix}[au_pay_card_bill]"),
        "au_jibun_bank": request.values.get(f"{prefix}[au_jibun_bank]"),
        "au_bill_payment_mode": request.values.get(f"{prefix}[au_bill_payment_mode]"),
        "au_pay_card_bank_is_jibun": request.values.get(f"{prefix}[au_pay_card_bank_is_jibun]"),
        "docomo_bill_dcard": request.values.get(f"{prefix}[docomo_bill_dcard]"),
        "au_jibun_bank_balance": request.values.get(f"{prefix}[au_jibun_bank_balance]"),
    }


def _default_line(carrier: str = DEFAULT_CARRIER) -> dict:
    return {
        "carrier": carrier,
        "age": None,
        "data_usage": DEFAULT_DATA_USAGE,
        "plan": None,
        "discounts": [],
        "qr_paypay": None,
        "qr_dbarai": None,
        "qr_aupay": None,
        "paypay_card_tier": None,
        "paypay_gold_linked": None,
        "aupay_gold": None,
        "dcard_tier": "standard",
        "au_pay_card_bill": None,
        "au_jibun_bank": None,
        "au_bill_payment_mode": "other",
        "au_pay_card_bank_is_jibun": None,
        "docomo_bill_dcard": None,
        "au_jibun_bank_balance": None,
    }


def _parse_request_params() -> dict:
    available_ids = [carrier["id"] for carrier in load_all_carriers()]
    legacy_carrier = _resolve_carrier(
        request.values.get("carrier"),
        available_ids,
        DEFAULT_CARRIER,
    )

    indices = _parse_line_indices()
    if len(indices) > MAX_LINES:
        raise InvalidUsageError(f"at most {MAX_LINES} lines are supported")

    lines = (
        [_parse_line(index, available_ids, legacy_carrier) for index in indices]
        if indices
        else [_default_line(legacy_carrier)]
    )

    carrier_ids = list({line["carrier"] for line in lines})

    home_set_flags = {
        group_id: is_checked_flag(request.values.get(f"home_set_{group_id}"))
        for group_id in HOME_SET_GROUPS
    }
    if not any(f"home_set_{group_id}" in request.values for group_id in HOME_SET_GROUPS):
        discounts_by_carrier: dict[str, list[str]] = {}
        for line in lines:
            carrier_id = line["carrier"]
            discounts_by_carrier.setdefault(carrier_id, []).extend(line.get("discounts") or [])
        home_set_flags = infer_home_set_flags(discounts_by_carrier, carrier_ids)

    return {
        "lines": lines,
        "carrier_ids": carrier_ids,
        "default_carrier": legacy_carrier,
        "tenure_years": request.values.get("tenure_years"),
        "home_set_flags": home_set_flags,
        "active_line_index": min(
            max(parse_int_or(request.values.get("active_line"), 0), 0),
            len(lines) - 1,
        ),
        "current_carrier": request.values.get("current_carrier") or None,
        "current_plan": request.values.get("current_plan") or None,
        "current_price": request.values.get("current_price"),
    }


def parse_int_or(raw: str | None, default: int) -> int:
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        return default


def _compare(params: dict) -> dict:
    current = resolve_current_plan(
        params.get("current_carrier"),
        params.get("current_plan"),
        params.get("current_price"),
    )
    return calculate_multi_carrier_lines(
        params["lines"],
        tenure_years=params.get("tenure_years"),
        home_set_flags=params["home_set_flags"],
        default_carrier=params["default_carrier"],
        current=current,
    )


@app.route("/")
def simulator():
    try:
        params = _parse_request_params()
    except InvalidUsageError as error:
        params = {
            "lines": [_default_line()],
            "carrier_ids": [DEFAULT_CARRIER],
            "default_carrier": DEFAULT_CARRIER,
            "tenure_years": None,
            "home_set_flags": {group_id: False for group_id in HOME_SET_GROUPS},
            "active_line_index": 0,
            "current_carrier": request.values.get("current_carrier") or None,
            "current_plan": request.values.get("current_plan") or None,
            "current_price": request.values.get("current_price"),
        }
        validation_error = str(error)
        comparison = _compare(params)
        simulator_config = build_simulator_ui_config()
        account_ui = build_account_ui_visibility(params["carrier_ids"], simulator_config["carrier_ui"])
        return render_template(
            "simulator.html",
            carriers=load_all_carriers(),
            carrier_map=get_carrier_map(),
            comparison=comparison,
            validation_error=validation_error,
            lines=params["lines"],
            carrier_ids=params["carrier_ids"],
            account_ui=account_ui,
            active_line_index=0,
            active_result=comparison["lines"][0] if comparison["lines"] else None,
            tenure_years=None,
            selected_home_set_softbank=False,
            selected_home_set_au=False,
            selected_home_set_docomo=False,
            selected_home_set_docomo_denki=False,
            carrier_ui=simulator_config["carrier_ui"],
            home_set_discount_groups=build_home_set_discount_groups(),
            family_discount_ids=simulator_config["family_discount_ids"],
            family_discount_primary_blocked=simulator_config["family_discount_primary_blocked"],
            eligibility={},
            discount_amounts={},
            simulator_config=simulator_config,
            initial_comparison={**comparison, "active_line_index": 0},
            selected_current_carrier=params.get("current_carrier"),
            selected_current_plan=params.get("current_plan"),
            selected_current_price=params.get("current_price"),
        )

    simulator_config = build_simulator_ui_config()
    account_ui = build_account_ui_visibility(
        params["carrier_ids"],
        simulator_config["carrier_ui"],
    )

    try:
        comparison = _compare(params)
        validation_error = None
    except InvalidUsageError as error:
        validation_error = str(error)
        safe_params = {
            **params,
            "lines": [_default_line(params["default_carrier"])],
            "tenure_years": None,
        }
        comparison = _compare(safe_params)

    active_line = params["active_line_index"]
    active_result = comparison["lines"][active_line] if comparison["lines"] else None

    return render_template(
        "simulator.html",
        carriers=load_all_carriers(),
        carrier_map=get_carrier_map(),
        comparison=comparison,
        validation_error=validation_error,
        lines=params["lines"],
        carrier_ids=params["carrier_ids"],
        account_ui=account_ui,
        active_line_index=active_line,
        active_result=active_result,
        tenure_years=params.get("tenure_years"),
        selected_home_set_softbank=params["home_set_flags"]["softbank"],
        selected_home_set_au=params["home_set_flags"]["au"],
        selected_home_set_docomo=params["home_set_flags"]["docomo"],
        selected_home_set_docomo_denki=params["home_set_flags"]["docomo_denki"],
        carrier_ui=simulator_config["carrier_ui"],
        home_set_discount_groups=build_home_set_discount_groups(),
        family_discount_ids=simulator_config["family_discount_ids"],
        family_discount_primary_blocked=simulator_config["family_discount_primary_blocked"],
        eligibility={
            result["carrier_id"]: result["discount_eligibility"]
            for result in comparison["lines"]
        },
        discount_amounts={
            result["line_index"]: result.get("resolved_discount_amounts", {})
            for result in comparison["lines"]
        },
        simulator_config=simulator_config,
        initial_comparison={
            **comparison,
            "active_line_index": active_line,
        },
        selected_current_carrier=params.get("current_carrier"),
        selected_current_plan=params.get("current_plan"),
        selected_current_price=params.get("current_price"),
    )


@app.route("/api/calculate", methods=["GET", "POST"])
def api_calculate():
    try:
        params = _parse_request_params()
        comparison = _compare(params)
    except InvalidUsageError as error:
        return jsonify({"error": "invalid_request", "message": str(error)}), 400
    except Exception:
        logger.exception("api_calculate failed")
        return jsonify(
            {
                "error": "internal_error",
                "message": "比較結果を取得できませんでした",
            }
        ), 500

    comparison["active_line_index"] = params["active_line_index"]
    return jsonify(comparison)


@app.route("/api/compare", methods=["GET", "POST"])
def api_compare():
    try:
        params = _parse_request_params()
        current = resolve_current_plan(
            params.get("current_carrier"),
            params.get("current_plan"),
            params.get("current_price"),
        )
        result = compare_all_carriers_for_lines(
            params["lines"],
            tenure_years=params.get("tenure_years"),
            home_set_flags=params["home_set_flags"],
        )
        attach_current_savings_to_compare_result(result, current)
    except InvalidUsageError as error:
        return jsonify({"error": "invalid_request", "message": str(error)}), 400
    except Exception:
        logger.exception("api_compare failed")
        return jsonify(
            {
                "error": "internal_error",
                "message": "比較結果を取得できませんでした",
            }
        ), 500

    return jsonify(result)


@app.route("/compare")
def compare_page():
    simulator_config = build_simulator_ui_config()
    return render_template(
        "compare.html",
        simulator_config=simulator_config,
    )


@app.route("/api/carriers")
def api_carriers():
    carriers = load_all_carriers()
    return jsonify({"carriers": carriers, **build_simulator_ui_config(carriers)})


if __name__ == "__main__":
    host = str(app.config.get("HOST", "127.0.0.1"))
    port = int(app.config.get("PORT", 5000))
    debug = bool(app.config.get("DEBUG"))
    if debug:
        print("\n========================================")
        print("  料金シミュレーター 起動中...")
        print(f"  ブラウザで http://{host}:{port} を開いてください")
        print("  終了する場合は Ctrl+C を押してください")
        print("========================================\n")
    else:
        logger.info("Starting development server host=%s port=%s debug=%s", host, port, debug)
    app.run(debug=debug, host=host, port=port)
