#!/usr/bin/env python3
"""Scan namespace health and detect anomalies."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skill_lib.cli import emit_json, handle_skill_error
from skill_lib.health_scanner import scan_namespace_health


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan namespace health")
    parser.add_argument("--context", required=True, help="Kubeconfig context name")
    parser.add_argument("--namespace", required=True, help="Namespace to scan")
    args = parser.parse_args()

    try:
        result = scan_namespace_health(args.context, args.namespace)
        emit_json({"status": "success", **result.model_dump()})
    except Exception as exc:
        handle_skill_error(exc)


if __name__ == "__main__":
    main()
