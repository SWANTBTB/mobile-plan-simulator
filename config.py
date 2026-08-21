"""環境変数ベースの最小設定（development / production）。"""

from __future__ import annotations

import os


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_config() -> dict[str, object]:
    """Flask app.config へ適用する設定辞書。"""
    env = os.environ.get("FLASK_ENV", "development").strip().lower()
    is_production = env == "production"
    secret_key = os.environ.get("SECRET_KEY")
    if is_production and not secret_key:
        raise RuntimeError("SECRET_KEY environment variable is required when FLASK_ENV=production")

    return {
        "ENV": env,
        "DEBUG": (not is_production) and _env_bool("FLASK_DEBUG", True),
        "TESTING": _env_bool("TESTING", False),
        "SECRET_KEY": secret_key or "dev-insecure-key-change-me",
        "HOST": os.environ.get("HOST", "0.0.0.0" if is_production else "127.0.0.1"),
        "PORT": int(os.environ.get("PORT", "5000")),
        "ROBOTS_NOINDEX": _env_bool("ROBOTS_NOINDEX", default=not is_production),
    }
