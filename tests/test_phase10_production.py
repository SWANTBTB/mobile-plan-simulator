"""Phase 10: production readiness (config, errors, security headers)."""

from __future__ import annotations

import os

import pytest

from app import app as flask_app


def test_security_headers_on_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"


def test_api_unknown_route_returns_json_404(client):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    payload = response.get_json()
    assert payload["error"] == "not_found"


def test_html_unknown_route_returns_404_page(client):
    response = client.get("/does-not-exist-page")
    assert response.status_code == 404
    assert "ページが見つかりません".encode("utf-8") in response.data


def test_api_invalid_current_carrier_returns_400_not_500(client):
    response = client.get(
        "/api/calculate",
        query_string={
            "current_carrier": "unknown_carrier",
            "current_price": "5000",
            "lines[0][data_usage]": "3",
        },
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_request"


def test_api_negative_qr_returns_400(client):
    response = client.get(
        "/api/calculate",
        query_string={"lines[0][carrier]": "softbank", "lines[0][qr_paypay]": "-100"},
    )
    assert response.status_code == 400


def test_api_invalid_age_returns_400(client):
    response = client.get(
        "/api/calculate",
        query_string={"lines[0][carrier]": "au", "lines[0][age]": "-5", "lines[0][data_usage]": "3"},
    )
    assert response.status_code == 400


def test_compare_page_includes_disclaimer_and_pricing_label(client):
    response = client.get("/compare")
    html = response.get_data(as_text=True)
    assert "2026年8月21日時点の料金" in html
    assert "サーバー側のデータベース等へ永続保存しません" in html
    assert "sessionStorage" in html
    assert "softbank.jp/mobile/price_plan/" in html


def test_simulator_footer_official_links(client):
    response = client.get("/")
    html = response.get_data(as_text=True)
    assert "ahamo.com/plan/index.html" in html
    assert "network.mobile.rakuten.co.jp/fee/" in html


def test_development_config_debug_enabled_by_default():
    assert flask_app.config["ENV"] == "development"
    assert flask_app.config["DEBUG"] is True


def test_production_config_requires_secret_key(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    from config import load_config

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        load_config()


def test_production_config_with_secret_key(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "test-production-secret")
    from importlib import reload

    import config as config_module

    reload(config_module)
    cfg = config_module.load_config()
    assert cfg["DEBUG"] is False
    assert cfg["SECRET_KEY"] == "test-production-secret"


def test_api_internal_error_returns_safe_json(client, monkeypatch):
    def boom(_params):
        raise RuntimeError("boom")

    monkeypatch.setattr("app._compare", boom)
    response = client.get(
        "/api/calculate",
        query_string={"lines[0][carrier]": "au", "lines[0][data_usage]": "3"},
    )
    assert response.status_code == 500
    payload = response.get_json()
    assert payload["error"] == "internal_error"
    assert "boom" not in payload["message"]
    assert "Traceback" not in response.get_data(as_text=True)
