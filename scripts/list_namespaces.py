#!/usr/bin/env python3
"""List namespaces for a Kubernetes context."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skill_lib.cli import emit_json, handle_skill_error
from skill_lib import kube_client


def main() -> None:
    parser = argparse.ArgumentParser(description="List namespaces in a cluster context")
    parser.add_argument("--context", required=True, help="Kubeconfig context name")
    args = parser.parse_args()

    try:
        kube_client.validate_context_exists(args.context)
        namespaces = kube_client.list_namespaces_for_context(args.context)
        emit_json(
            {
                "status": "success",
                "context": args.context,
                "cluster": kube_client.extract_cluster_display_name(args.context),
                "namespaces": namespaces,
            }
        )
    except Exception as exc:
        handle_skill_error(exc)


if __name__ == "__main__":
    main()
