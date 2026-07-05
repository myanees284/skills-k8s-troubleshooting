"""Shared CLI helpers for troubleshooting scripts."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def setup_path() -> None:
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def emit_json(payload: Any) -> None:
    if hasattr(payload, "model_dump"):
        data = payload.model_dump()
    else:
        data = payload
    print(json.dumps(data, indent=2))


def emit_error(message: str, error_type: str, *, exit_code: int = 1) -> None:
    print(
        json.dumps({"status": "error", "error_type": error_type, "message": message}, indent=2),
        file=sys.stderr,
    )
    raise SystemExit(exit_code)


def handle_skill_error(exc: Exception) -> None:
    error_type = getattr(exc, "error_type", exc.__class__.__name__)
    message = getattr(exc, "message", str(exc))
    emit_error(message, error_type)
