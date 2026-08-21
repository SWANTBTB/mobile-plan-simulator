"""本番 WSGI エントリポイント（waitress / gunicorn 等）。"""

from app import app

__all__ = ["app"]
