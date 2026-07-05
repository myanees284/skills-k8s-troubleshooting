#!/usr/bin/env python3
"""Find similar past investigations in local JSON history."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skill_lib.cli import emit_json, handle_skill_error
from skill_lib.history import find_similar_investigations, get_history_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Find similar saved investigations")
    parser.add_argument("--issue-type", help="Issue type to match")
    parser.add_argument("--service-name", help="Service/deployment name to match")
    parser.add_argument("--namespace", help="Namespace to match")
    parser.add_argument("--exclude-id", type=int, help="Investigation ID to exclude")
    args = parser.parse_args()

    try:
        result = find_similar_investigations(
            issue_type=args.issue_type,
            service_name=args.service_name,
            namespace=args.namespace,
            exclude_id=args.exclude_id,
        )
        emit_json(
            {
                "status": "success",
                "history_path": str(get_history_path()),
                **result.model_dump(),
            }
        )
    except Exception as exc:
        handle_skill_error(exc)


if __name__ == "__main__":
    main()
