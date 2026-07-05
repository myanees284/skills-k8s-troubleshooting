#!/usr/bin/env python3
"""List Kubernetes contexts from local kubeconfig."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skill_lib.cli import emit_json, handle_skill_error
from skill_lib import kube_client


def main() -> None:
    parser = argparse.ArgumentParser(description="List kubeconfig contexts")
    args = parser.parse_args()

    try:
        contexts, active_context = kube_client.list_available_contexts()
        emit_json(
            {
                "status": "success",
                "kubeconfig_path": kube_client.get_kubeconfig_path(),
                "current_context": active_context,
                "contexts": contexts,
            }
        )
    except Exception as exc:
        handle_skill_error(exc)


if __name__ == "__main__":
    main()
