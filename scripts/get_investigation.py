#!/usr/bin/env python3
"""Retrieve a saved investigation by ID."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skill_lib.cli import emit_json, handle_skill_error
from skill_lib.history import InvestigationNotFoundError, get_history_path, get_investigation


def main() -> None:
    parser = argparse.ArgumentParser(description="Get a saved investigation by ID")
    parser.add_argument("--id", type=int, required=True, help="Investigation ID")
    args = parser.parse_args()

    try:
        detail = get_investigation(args.id)
        emit_json(
            {
                "status": "success",
                "history_path": str(get_history_path()),
                **detail.model_dump(),
            }
        )
    except InvestigationNotFoundError as exc:
        from skill_lib.cli import emit_error

        emit_error(exc.message, exc.error_type)
    except Exception as exc:
        handle_skill_error(exc)


if __name__ == "__main__":
    main()
