from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "carriers"

# ファイルの更新時刻をキーにキャッシュする。JSON を編集すれば再起動なしで反映される。
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _load_file(path: Path) -> dict[str, Any]:
    mtime = path.stat().st_mtime
    cached = _cache.get(path.name)
    if cached and cached[0] == mtime:
        return cached[1]

    with path.open(encoding="utf-8") as f:
        carrier = json.load(f)

    _cache[path.name] = (mtime, carrier)
    return carrier


def load_carrier(carrier_id: str) -> dict[str, Any]:
    return _load_file(DATA_DIR / f"{carrier_id}.json")


def load_all_carriers() -> list[dict[str, Any]]:
    carriers = [_load_file(path) for path in DATA_DIR.glob("*.json")]
    return sorted(carriers, key=lambda carrier: carrier.get("display_order", 99))


def get_carrier_map() -> dict[str, dict[str, Any]]:
    return {carrier["id"]: carrier for carrier in load_all_carriers()}
