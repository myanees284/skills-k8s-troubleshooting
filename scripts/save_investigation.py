#!/usr/bin/env python3
"""Save an investigation result to local JSON history."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skill_lib.cli import emit_json, handle_skill_error
from skill_lib.history import load_investigation_payload, save_investigation


def _read_payload(args: argparse.Namespace) -> dict:
    if args.file:
        with Path(args.file).open("r", encoding="utf-8") as handle:
            return json.load(handle)

    if not sys.stdin.isatty():
        return json.load(sys.stdin)

    raise ValueError(
        "Provide investigation JSON via --file or pipe from investigate_pod.py / investigate_namespace.py."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Save investigation JSON to local history")
    parser.add_argument("--file", help="Path to investigation JSON file")
    parser.add_argument("--executive-summary", help="Optional summary notes to store with the record")
    parser.add_argument("--root-cause", help="Optional root cause notes")
    parser.add_argument("--suggested-actions", help="Optional remediation notes")
    parser.add_argument(
        "--risk-level",
        help="Optional risk level label (default: Unknown)",
    )
    args = parser.parse_args()

    try:
        payload = _read_payload(args)
        investigation = load_investigation_payload(payload)
        saved = save_investigation(
            investigation,
            executive_summary=args.executive_summary,
            root_cause=args.root_cause,
            suggested_actions=args.suggested_actions,
            risk_level=args.risk_level,
        )
        emit_json({"status": "success", "saved_to_history": saved})
    except Exception as exc:
        if isinstance(exc, ValueError) and not getattr(exc, "error_type", None):
            from skill_lib.cli import emit_error

            emit_error(str(exc), "invalid_input")
        handle_skill_error(exc)


if __name__ == "__main__":
    main()
