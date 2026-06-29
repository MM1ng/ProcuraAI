from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import DATA_DIR


POLICIES_FILE = DATA_DIR / "procurement_policies.json"
SUPPLIERS_FILE = DATA_DIR / "suppliers.json"


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def load_procurement_policies(path: Path = POLICIES_FILE) -> list[dict[str, Any]]:
    return _load_json_list(path)


def load_supplier_profiles(path: Path = SUPPLIERS_FILE) -> list[dict[str, Any]]:
    return _load_json_list(path)
