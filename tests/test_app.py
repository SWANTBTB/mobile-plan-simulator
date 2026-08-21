import json
import re


def _result_by_carrier(payload, carrier_id):
    return next(item for item in payload["results"] if item["carrier_id"] == carrier_id)


def _line_query(line_index, **fields):
    query = {"carrier": "au"}
    prefix = f"lines[{line_index}]"
    for key, value in fields.items():
        if key == "discounts":
            return [(f"{prefix}[discounts]", value)]
        query[f"{prefix}[{key}]"] = value
    return query


def test_api_calculate_applies_home_set_flag(client):
    response = client.get(
        "/api/calculate",
        query_string={
            "carrier": "uqmobile",
            "lines[0][data_usage]": "3",
            "home_set_au": "1",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    result = payload["lines"][0]

    assert any(item["id"] == "home_set" for item in result["applied_discounts"])
    assert result["total"] == 1848


def test_api_calculate_manual_plan(client):
    response = client.get(
        "/api/calculate",
        query_string={
            "carrier": "au",
            "lines[0][data_usage]": "10",
            "lines[0][plan]": "unlimited_max_plus",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    au = payload["lines"][0]

    assert len(payload["lines"]) == 1
    assert au["plan_manual"] is True
    assert au["plan"]["id"] == "unlimited_max_plus"


def test_api_calculate_family_discount_on_second_line_only(client):
    response = client.get(
        "/api/calculate",
        query_string=[
            ("carrier", "au"),
            ("lines[0][data_usage]", "30"),
            ("lines[0][plan]", "unlimited_max_plus"),
            ("lines[1][data_usage]", "10"),
            ("lines[1][plan]", "unlimited_max_plus"),
            ("lines[1][discounts]", "family_plus"),
        ],
    )

    assert response.status_code == 200
    payload = response.get_json()
    main = payload["lines"][0]
    second = payload["lines"][1]

    assert main["total"] == 7788
    assert not any(item["id"] == "family_plus" for item in main["applied_discounts"])
    assert second["total"] == 7128
    assert payload["totals"]["value_adjusted_total"] == main["value_adjusted_total"] + second["value_adjusted_total"]


def test_api_calculate_main_line_applies_family_discount_when_checked(client):
    response = client.get(
        "/api/calculate",
        query_string=[
            ("carrier", "au"),
            ("lines[0][data_usage]", "30"),
            ("lines[0][plan]", "unlimited_max_plus"),
            ("lines[0][discounts]", "family_plus"),
            ("lines[1][data_usage]", "10"),
            ("lines[1][plan]", "unlimited_max_plus"),
        ],
    )

    assert response.status_code == 200
    main = response.get_json()["lines"][0]
    assert main["total"] == 7128
    assert any(item["id"] == "family_plus" for item in main["applied_discounts"])


def test_api_calculate_invalid_request_returns_400(client):
    response = client.get(
        "/api/calculate",
        query_string={
            "carrier": "au",
            "lines[0][data_usage]": "999999",
        },
    )

    assert response.status_code == 400


def test_api_carriers_returns_all_carriers(client):
    response = client.get("/api/carriers")

    assert response.status_code == 200
    payload = response.get_json()
    assert len(payload["carriers"]) >= 7
    assert "carrier_ui" in payload
    assert "family_discount_ids" in payload


def test_api_calculate_docomo_denki_set_flag(client):
    response = client.get(
        "/api/calculate",
        query_string={
            "carrier": "docomo",
            "lines[0][data_usage]": "3",
            "lines[0][plan]": "docomo_mini",
            "home_set_docomo_denki": "1",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["lines"][0]["total"] == 2640


def test_api_calculate_post_body(client):
    response = client.post(
        "/api/calculate",
        data={
            "carrier": "au",
            "lines[0][data_usage]": "10",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["selected_carrier"] == "au"
    assert len(payload["lines"]) == 1


def test_api_calculate_tenure_applies_docomo_long_term(client):
    response = client.get(
        "/api/calculate",
        query_string={
            "carrier": "docomo",
            "tenure_years": "12",
            "lines[0][data_usage]": "10",
            "lines[0][plan]": "docomo_max_3gb",
            "lines[0][discounts]": "long_term",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["lines"][0]["total"] == 6578


def test_api_calculate_tenure_auto_applies_docomo_long_term(client):
    response = client.get(
        "/api/calculate",
        query_string={
            "carrier": "docomo",
            "tenure_years": "12",
            "lines[0][carrier]": "docomo",
            "lines[0][data_usage]": "10",
            "lines[0][plan]": "docomo_max_3gb",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["lines"][0]["total"] == 6578
    assert any(item["id"] == "long_term" for item in payload["lines"][0]["applied_discounts"])


def test_api_calculate_mixed_carriers(client):
    response = client.get(
        "/api/calculate",
        query_string=[
            ("lines[0][carrier]", "au"),
            ("lines[0][data_usage]", "10"),
            ("lines[0][plan]", "unlimited_max_plus"),
            ("lines[1][carrier]", "docomo"),
            ("lines[1][data_usage]", "10"),
            ("lines[1][plan]", "docomo_max_3gb"),
        ],
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["lines"][0]["carrier_id"] == "au"
    assert payload["lines"][1]["carrier_id"] == "docomo"
    assert set(payload["carrier_ids"]) == {"au", "docomo"}


def test_api_calculate_rejects_too_many_lines(client):
    query = {f"lines[{index}][data_usage]": "10" for index in range(11)}
    response = client.get("/api/calculate", query_string=query)
    assert response.status_code == 400


def test_api_calculate_current_price_computes_best_saving(client):
    response = client.get(
        "/api/calculate",
        query_string={
            "lines[0][carrier]": "softbank",
            "lines[0][data_usage]": "30",
            "lines[0][plan]": "teigaku_unlimited",
            "current_carrier": "au",
            "current_price": "10000",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    current = payload["current"]
    totals = payload["totals"]

    assert current["monthly"] == 10000
    assert current["is_manual_price"] is True
    assert payload["best_saving"] == 10000 - totals["value_adjusted_total"]
    assert totals["diff"] == totals["value_adjusted_total"] - 10000


def test_simulator_page_renders_per_line_carrier(client):
    response = client.get(
        "/",
        query_string={
            "lines[0][carrier]": "au",
            "lines[1][carrier]": "docomo",
            "lines[1][data_usage]": "10",
        },
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'name="lines[0][carrier]"' in html
    assert 'name="lines[1][carrier]"' in html
    assert 'name="carrier"' not in html
    assert 'name="current_carrier"' in html


def test_simulator_page_renders_current_contract_fields(client):
    response = client.get(
        "/",
        query_string={
            "current_carrier": "au",
            "current_plan": "unlimited_max_plus",
            "current_price": "7500",
        },
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'name="current_carrier"' in html
    assert 'name="current_plan"' in html
    assert 'name="current_price"' in html
    assert 'value="7500"' in html
    assert "ワイモバイルのみ主回線は対象外" in html
    assert "2026年8月21日時点の料金" in html


def test_simulator_initial_comparison_embeds_best_saving(client):
    response = client.get(
        "/",
        query_string={
            "lines[0][carrier]": "softbank",
            "lines[0][data_usage]": "30",
            "lines[0][plan]": "teigaku_unlimited",
            "current_carrier": "au",
            "current_price": "10000",
        },
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    match = re.search(r'id="initial-comparison">(.+?)</script>', html, re.DOTALL)
    assert match is not None

    payload = json.loads(match.group(1))
    assert payload["current"]["monthly"] == 10000
    assert payload["best_saving"] == 10000 - payload["totals"]["value_adjusted_total"]


def test_api_calculate_ignores_legacy_global_line_count(client):
    response = client.get(
        "/api/calculate",
        query_string={
            "line_count": "99",
            "age": "40",
            "lines[0][carrier]": "softbank",
            "lines[0][data_usage]": "30",
            "lines[0][plan]": "teigaku_unlimited",
            "lines[0][discounts]": "family_discount",
        },
    )

    assert response.status_code == 200
    line = response.get_json()["lines"][0]
    assert not any(item["id"] == "family_discount" for item in line["applied_discounts"])


def test_simulator_page_renders_line_list(client):
    response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="lines-container"' in html
    assert 'id="campaign-panels"' in html
    assert 'data-line-card="0"' in html
    assert "主回線" in html
    assert 'name="lines[0][age]"' in html
    assert 'id="add-line-button"' in html
