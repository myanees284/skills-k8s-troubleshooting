"""Namespace health scanning (read-only)."""

from __future__ import annotations

from skill_lib import kube_client
from skill_lib.formatters import (
    NamespaceHealthResponse,
    build_namespace_health,
    sort_events,
    summarize_deployment,
    summarize_event,
    summarize_pod,
)


def scan_namespace_health(context_name: str, namespace: str) -> NamespaceHealthResponse:
    kube_client.validate_context_exists(context_name)
    kube_client.validate_namespace_exists(context_name, namespace)

    raw_pods = kube_client.list_pods_for_namespace(context_name, namespace)
    pods = [summarize_pod(pod) for pod in raw_pods]
    deployments = [
        summarize_deployment(item)
        for item in kube_client.list_deployments_for_namespace(context_name, namespace)
    ]
    events = sort_events(
        [
            summarize_event(item)
            for item in kube_client.list_events_for_namespace(context_name, namespace)
        ]
    )

    return build_namespace_health(context_name, namespace, pods, deployments, events)
