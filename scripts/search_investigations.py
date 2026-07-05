#!/usr/bin/env python3
"""Search saved investigations in local JSON history."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skill_lib.cli import emit_json, handle_skill_error
from skill_lib.history import get_history_path, search_investigations


def main() -> None:
    parser = argparse.ArgumentParser(description="Search saved investigations")
    parser.add_argument("--q", help="Keyword search across stored fields and evidence")
    parser.add_argument("--issue-type", help="Filter by issue type")
    parser.add_argument("--service-name", help="Filter by service/deployment name substring")
    parser.add_argument("--namespace", help="Filter by namespace")
    parser.add_argument("--risk-level", help="Filter by risk level")
    args = parser.parse_args()

    try:
        results = search_investigations(
            q=args.q,
            issue_type=args.issue_type,
            service_name=args.service_name,
            namespace=args.namespace,
            risk_level=args.risk_level,
        )
        emit_json(
            {
                "status": "success",
                "history_path": str(get_history_path()),
                "count": len(results),
                "investigations": [item.model_dump() for item in results],
            }
        )
    except Exception as exc:
        handle_skill_error(exc)


if __name__ == "__main__":
    main()
