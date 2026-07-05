#!/usr/bin/env python3
"""Investigate unhealthy resources across a namespace."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skill_lib.cli import emit_error, emit_json, handle_skill_error
from skill_lib.history import save_investigation
from skill_lib.investigator import NoUnhealthyResourcesError, investigate_namespace


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Investigate unhealthy pods/deployments in a namespace"
    )
    parser.add_argument("--context", required=True, help="Kubeconfig context name")
    parser.add_argument("--namespace", required=True, help="Namespace to investigate")
    parser.add_argument(
        "--tail-lines",
        type=int,
        default=100,
        help="Number of log lines to collect per container (default: 100)",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save investigation result to local JSON history",
    )
    parser.add_argument("--executive-summary", help="Notes to store when using --save")
    parser.add_argument("--root-cause", help="Root cause notes to store when using --save")
    parser.add_argument("--suggested-actions", help="Remediation notes to store when using --save")
    parser.add_argument("--risk-level", help="Risk level label to store when using --save")
    args = parser.parse_args()

    try:
        result = investigate_namespace(
            args.context,
            args.namespace,
            tail_lines=args.tail_lines,
        )
        output = result.model_dump()
        if args.save:
            output["saved_to_history"] = save_investigation(
                result,
                executive_summary=args.executive_summary,
                root_cause=args.root_cause,
                suggested_actions=args.suggested_actions,
                risk_level=args.risk_level,
            )
        emit_json(output)
    except NoUnhealthyResourcesError as exc:
        emit_error(exc.message, exc.error_type)
    except Exception as exc:
        handle_skill_error(exc)


if __name__ == "__main__":
    main()
