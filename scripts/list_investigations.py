#!/usr/bin/env python3
"""List saved investigations from local JSON history."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skill_lib.cli import emit_json, handle_skill_error
from skill_lib.history import get_history_path, list_investigations


def main() -> None:
    parser = argparse.ArgumentParser(description="List saved investigations")
    args = parser.parse_args()

    try:
        summaries = list_investigations()
        emit_json(
            {
                "status": "success",
                "history_path": str(get_history_path()),
                "count": len(summaries),
                "investigations": [item.model_dump() for item in summaries],
            }
        )
    except Exception as exc:
        handle_skill_error(exc)


if __name__ == "__main__":
    main()
