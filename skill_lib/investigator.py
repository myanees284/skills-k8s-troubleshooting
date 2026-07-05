"""Kubernetes investigation engine — structured read-only evidence collection."""

from __future__ import annotations

import logging

from skill_lib import kube_client
from skill_lib.formatters import (
    RESTART_THRESHOLD,
    AIReasoningContext,
    EventSummary,
    InvestigationEvidence,
    InvestigationResponse,
    InvestigationResultSummary,
    PodDescribeResponse,
    PodLogsResponse,
    build_ai_evidence_summary,
    build_oom_investigations,
    build_pod_scoped_health,
    describe_pod,
    detect_log_patterns,
    extract_affected_deployment_names,
    extract_affected_pod_names,
    filter_events_for_pod,
    find_deployment_for_pod,
    inspect_deployment,
    sort_events,
    summarize_event,
    summarize_node,
)
from skill_lib.health_scanner import scan_namespace_health
from skill_lib.kube_client import ContainerNotFoundError as KubeContainerNotFoundError

logger = logging.getLogger(__name__)

DEFAULT_TAIL_LINES = 100


class NoUnhealthyResourcesError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message
        self.error_type = "no_unhealthy_resources"


def _describe_pod(context_name: str, namespace: str, pod_name: str) -> PodDescribeResponse:
    raw_pod = kube_client.read_pod_for_namespace(context_name, namespace, pod_name)
    return describe_pod(raw_pod)


def _collect_pod_logs(
    context_name: str,
    namespace: str,
    pod_name: str,
    *,
    container: str | None = None,
    tail_lines: int = DEFAULT_TAIL_LINES,
) -> PodLogsResponse:
    raw_pod = kube_client.read_pod_for_namespace(context_name, namespace, pod_name)

    container_names = [
        item.name for item in (raw_pod.spec.containers if raw_pod.spec else []) or []
    ]
    if not container_names:
        raise KubeContainerNotFoundError(
            f"Pod '{pod_name}' has no containers.",
            error_type="container_not_found",
        )

    selected_container = container or container_names[0]
    if selected_container not in container_names:
        raise KubeContainerNotFoundError(
            f"Container '{selected_container}' not found in pod '{pod_name}'. "
            f"Available containers: {', '.join(container_names)}",
            error_type="container_not_found",
        )

    logs = kube_client.get_pod_logs(
        context_name,
        namespace,
        pod_name,
        selected_container,
        tail_lines=tail_lines,
    )

    previous_logs = ""
    container_statuses = (raw_pod.status.container_statuses if raw_pod.status else None) or []
    should_try_previous = any(
        status.name == selected_container
        and (
            (
                status.state
                and status.state.waiting
                and status.state.waiting.reason
                in {"CrashLoopBackOff", "Error", "ContainerCannotRun"}
            )
            or (status.last_state and status.last_state.terminated)
            or (status.restart_count or 0) >= RESTART_THRESHOLD
        )
        for status in container_statuses
    )
    if should_try_previous:
        previous_logs = kube_client.get_pod_logs(
            context_name,
            namespace,
            pod_name,
            selected_container,
            tail_lines=tail_lines,
            previous=True,
        )

    combined_logs = logs
    if previous_logs:
        combined_logs = f"{logs}\n--- previous container logs ---\n{previous_logs}"

    return PodLogsResponse(
        pod_name=pod_name,
        namespace=namespace,
        container=selected_container,
        tail_lines=tail_lines,
        logs=combined_logs,
        detected_patterns=detect_log_patterns(combined_logs),
        previous_container=bool(previous_logs),
    )


def _collect_logs_for_pod(
    context_name: str,
    namespace: str,
    pod_name: str,
    tail_lines: int = DEFAULT_TAIL_LINES,
) -> list[PodLogsResponse]:
    raw_pod = kube_client.read_pod_for_namespace(context_name, namespace, pod_name)
    container_names = [
        item.name for item in (raw_pod.spec.containers if raw_pod.spec else []) or []
    ]

    collected: list[PodLogsResponse] = []
    for container_name in container_names:
        try:
            collected.append(
                _collect_pod_logs(
                    context_name,
                    namespace,
                    pod_name,
                    container=container_name,
                    tail_lines=tail_lines,
                )
            )
        except KubeContainerNotFoundError:
            logger.warning(
                "Skipping logs for missing container '%s' in pod '%s'",
                container_name,
                pod_name,
            )
    return collected


def _collect_namespace_events(
    context_name: str,
    namespace: str,
    pod_name: str | None = None,
) -> list[EventSummary]:
    raw_events = kube_client.list_events_for_namespace(context_name, namespace)
    events = sort_events([summarize_event(item) for item in raw_events])
    if pod_name:
        return filter_events_for_pod(events, pod_name)
    return events


def _inspect_deployment_for_pod(
    context_name: str,
    namespace: str,
    pod_name: str,
    *,
    targeted: bool = False,
) -> list:
    raw_pod = kube_client.read_pod_for_namespace(context_name, namespace, pod_name)
    raw_deployments = kube_client.list_deployments_for_namespace(context_name, namespace)

    deployment = find_deployment_for_pod(raw_pod, raw_deployments)
    if not deployment:
        return []

    if targeted:
        related_pods = [pod_name]
    else:
        raw_pods = kube_client.list_pods_for_namespace(context_name, namespace)
        related_pods = [
            item.metadata.name
            for item in raw_pods
            if find_deployment_for_pod(item, [deployment]) is not None
        ]

    return [inspect_deployment(deployment, related_pods=related_pods)]


def _inspect_deployments_for_pods(
    context_name: str,
    namespace: str,
    pod_names: list[str],
    *,
    targeted: bool = False,
) -> list:
    inspected = []
    seen_deployments: set[str] = set()

    for pod_name in pod_names:
        for deployment in _inspect_deployment_for_pod(
            context_name,
            namespace,
            pod_name,
            targeted=targeted,
        ):
            if deployment.name in seen_deployments:
                continue
            inspected.append(deployment)
            seen_deployments.add(deployment.name)

    return inspected


def _nodes_for_pods(
    context_name: str,
    pod_descriptions: list[PodDescribeResponse],
) -> list:
    nodes = []
    for pod in pod_descriptions:
        if not pod.node_name:
            continue
        raw_node = kube_client.read_node_for_context(context_name, pod.node_name)
        nodes.append(summarize_node(raw_node))
    return nodes


def _build_investigation_response(
    *,
    context_name: str,
    namespace: str,
    namespace_health,
    target_pods: list[str],
    pod_descriptions,
    logs,
    events,
    deployments,
    nodes,
    warning_events: int,
    investigation_status: str,
    summary_message: str,
) -> InvestigationResponse:
    oom_investigations = build_oom_investigations(pod_descriptions, events, logs)
    evidence = InvestigationEvidence(
        namespace_health=namespace_health,
        pods=pod_descriptions,
        logs=logs,
        events=events,
        deployments=deployments,
        nodes=nodes,
        oom_investigations=oom_investigations,
    )

    evidence_summary = build_ai_evidence_summary(
        namespace_health,
        pod_descriptions,
        logs,
        events,
        deployments,
        nodes,
    )

    return InvestigationResponse(
        cluster_context=kube_client.extract_cluster_display_name(context_name),
        namespace=namespace,
        status="success",
        investigation_status=investigation_status,
        summary=InvestigationResultSummary(
            message=summary_message,
            affected_pods=len(target_pods),
            affected_deployments=len(deployments),
            warning_events=warning_events,
        ),
        evidence=evidence,
        ai_reasoning_context=AIReasoningContext(
            instruction=(
                "Use this structured Kubernetes evidence to reason about the likely root cause. "
                "Do not invent missing facts."
            ),
            evidence_summary=evidence_summary,
        ),
    )


def investigate_pod(
    context_name: str,
    namespace: str,
    pod_name: str,
    *,
    tail_lines: int = DEFAULT_TAIL_LINES,
) -> InvestigationResponse:
    kube_client.validate_context_exists(context_name)
    kube_client.validate_namespace_exists(context_name, namespace)

    pod_descriptions = [_describe_pod(context_name, namespace, pod_name)]
    namespace_health = build_pod_scoped_health(context_name, namespace, pod_descriptions[0])
    has_pod_issues = bool(pod_descriptions[0].issues)
    investigation_status = "anomaly_detected" if has_pod_issues else "targeted_investigation"
    summary_message = (
        "Anomaly detected and evidence collected for requested pod"
        if has_pod_issues
        else "Evidence collected for requested pod"
    )

    target_pods = [pod_name]
    logs: list[PodLogsResponse] = []
    for name in target_pods:
        logs.extend(_collect_logs_for_pod(context_name, namespace, name, tail_lines=tail_lines))

    events: list[EventSummary] = []
    for name in target_pods:
        events.extend(_collect_namespace_events(context_name, namespace, pod_name=name))
    events = sort_events(events)

    deployments = _inspect_deployments_for_pods(
        context_name,
        namespace,
        target_pods,
        targeted=True,
    )
    nodes = _nodes_for_pods(context_name, pod_descriptions)
    warning_events = sum(1 for event in events if event.type == "Warning")

    return _build_investigation_response(
        context_name=context_name,
        namespace=namespace,
        namespace_health=namespace_health,
        target_pods=target_pods,
        pod_descriptions=pod_descriptions,
        logs=logs,
        events=events,
        deployments=deployments,
        nodes=nodes,
        warning_events=warning_events,
        investigation_status=investigation_status,
        summary_message=summary_message,
    )


def investigate_namespace(
    context_name: str,
    namespace: str,
    *,
    tail_lines: int = DEFAULT_TAIL_LINES,
) -> InvestigationResponse:
    kube_client.validate_context_exists(context_name)
    kube_client.validate_namespace_exists(context_name, namespace)

    namespace_health = scan_namespace_health(context_name, namespace)
    target_pods = extract_affected_pod_names(namespace_health)
    if not target_pods:
        raise NoUnhealthyResourcesError(
            "No unhealthy resources found in the selected namespace."
        )

    pod_descriptions = [_describe_pod(context_name, namespace, name) for name in target_pods]

    logs: list[PodLogsResponse] = []
    for name in target_pods:
        logs.extend(_collect_logs_for_pod(context_name, namespace, name, tail_lines=tail_lines))

    events: list[EventSummary] = []
    for name in target_pods:
        events.extend(_collect_namespace_events(context_name, namespace, pod_name=name))
    events = sort_events(events)

    deployments = _inspect_deployments_for_pods(
        context_name,
        namespace,
        target_pods,
        targeted=False,
    )

    affected_deployment_names = extract_affected_deployment_names(namespace_health)
    if affected_deployment_names:
        raw_deployments = kube_client.list_deployments_for_namespace(context_name, namespace)
        existing = {item.name for item in deployments}
        for deployment in raw_deployments:
            if (
                deployment.metadata.name in affected_deployment_names
                and deployment.metadata.name not in existing
            ):
                deployments.append(inspect_deployment(deployment))

    nodes = _nodes_for_pods(context_name, pod_descriptions)
    warning_events = sum(1 for event in events if event.type == "Warning")

    return _build_investigation_response(
        context_name=context_name,
        namespace=namespace,
        namespace_health=namespace_health,
        target_pods=target_pods,
        pod_descriptions=pod_descriptions,
        logs=logs,
        events=events,
        deployments=deployments,
        nodes=nodes,
        warning_events=warning_events,
        investigation_status="anomaly_detected",
        summary_message="Anomaly detected and evidence collected",
    )
