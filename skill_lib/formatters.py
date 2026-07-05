"""Helpers for parsing Kubernetes resources, detecting anomalies, and building JSON models."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from skill_lib.kube_client import extract_cluster_display_name


class ContainerSummary(BaseModel):
    name: str
    ready: bool
    restart_count: int
    state: str
    waiting_reason: str | None = None
    terminated_reason: str | None = None


class PodSummary(BaseModel):
    name: str
    namespace: str
    phase: str
    node: str | None = None
    restart_count: int
    containers: list[ContainerSummary]


class DeploymentSummary(BaseModel):
    name: str
    namespace: str
    desired_replicas: int
    available_replicas: int
    ready_replicas: int
    unavailable_replicas: int
    healthy: bool


class EventSummary(BaseModel):
    type: str
    reason: str
    message: str
    object_kind: str
    object_name: str
    count: int | None = None
    last_timestamp: str | None = None


class HealthIssue(BaseModel):
    severity: str
    type: str
    resource_kind: str
    resource_name: str
    message: str


class HealthSummary(BaseModel):
    total_pods: int
    running_pods: int
    failed_pods: int
    pending_pods: int
    total_deployments: int
    healthy_deployments: int
    warning_events: int
    issues_count: int


class NamespaceHealthResponse(BaseModel):
    cluster_context: str
    namespace: str
    status: str = Field(description="healthy or anomaly")
    message: str
    summary: HealthSummary
    issues: list[HealthIssue]


class PodDescribeIssue(BaseModel):
    severity: str
    type: str
    message: str


class PodConditionDetail(BaseModel):
    type: str
    status: str
    reason: str | None = None
    message: str | None = None
    last_transition_time: str | None = None


class PodContainerDetail(BaseModel):
    name: str
    ready: bool
    restart_count: int
    state: str
    waiting_reason: str | None = None
    terminated_reason: str | None = None
    last_terminated_reason: str | None = None
    last_terminated_exit_code: int | None = None
    last_terminated_finished_at: str | None = None
    init_container: bool = False
    memory_limit: str | None = None
    memory_request: str | None = None
    cpu_limit: str | None = None
    cpu_request: str | None = None


class PodDescribeResponse(BaseModel):
    pod_name: str
    namespace: str
    phase: str
    node_name: str | None = None
    pod_ip: str | None = None
    start_time: str | None = None
    containers: list[PodContainerDetail]
    conditions: list[PodConditionDetail]
    issues: list[PodDescribeIssue]


class LogPatternMatch(BaseModel):
    type: str
    matched_text: str
    severity: str


class PodLogsResponse(BaseModel):
    pod_name: str
    namespace: str
    container: str
    tail_lines: int
    logs: str
    detected_patterns: list[LogPatternMatch]
    previous_container: bool = False


class DeploymentConditionDetail(BaseModel):
    type: str
    status: str
    reason: str | None = None
    message: str | None = None
    last_transition_time: str | None = None


class DeploymentInspectIssue(BaseModel):
    severity: str
    type: str
    message: str


class DeploymentInspection(BaseModel):
    name: str
    namespace: str
    desired_replicas: int
    available_replicas: int
    ready_replicas: int
    unavailable_replicas: int
    healthy: bool
    conditions: list[DeploymentConditionDetail]
    related_pods: list[str] = Field(default_factory=list)
    issues: list[DeploymentInspectIssue]


class NodeConditionDetail(BaseModel):
    type: str
    status: str
    reason: str | None = None
    message: str | None = None


class NodeSummary(BaseModel):
    name: str
    ready: bool
    kubernetes_version: str | None = None
    os_image: str | None = None
    instance_type: str | None = None
    capacity_cpu: str | None = None
    capacity_memory: str | None = None
    allocatable_cpu: str | None = None
    allocatable_memory: str | None = None
    conditions: list[NodeConditionDetail]


class OomContainerInvestigation(BaseModel):
    container: str
    init_container: bool = False
    last_oom_at: str | None = None
    exit_code: int | None = None
    restart_count: int
    state: str
    memory_limit: str | None = None
    memory_request: str | None = None
    cpu_limit: str | None = None
    cpu_request: str | None = None
    has_memory_limit: bool = True


class OomEventDetail(BaseModel):
    reason: str
    message: str
    last_timestamp: str | None = None


class OomInvestigation(BaseModel):
    pod_name: str
    namespace: str
    containers: list[OomContainerInvestigation]
    related_events: list[OomEventDetail] = Field(default_factory=list)


class InvestigationEvidence(BaseModel):
    namespace_health: NamespaceHealthResponse
    pods: list[PodDescribeResponse]
    logs: list[PodLogsResponse]
    events: list[EventSummary]
    deployments: list[DeploymentInspection]
    nodes: list[NodeSummary]
    oom_investigations: list[OomInvestigation] = Field(default_factory=list)


class InvestigationResultSummary(BaseModel):
    message: str
    affected_pods: int
    affected_deployments: int
    warning_events: int


class AIReasoningContext(BaseModel):
    instruction: str
    evidence_summary: dict


class InvestigationResponse(BaseModel):
    cluster_context: str
    namespace: str
    status: str
    investigation_status: str
    summary: InvestigationResultSummary
    evidence: InvestigationEvidence
    ai_reasoning_context: AIReasoningContext

RESTART_THRESHOLD = 3
OOM_EXIT_CODE = 137

CRITICAL_WAITING_REASONS = {
    "CrashLoopBackOff",
    "ImagePullBackOff",
    "ErrImagePull",
}

CRITICAL_TERMINATED_REASONS = {
    "OOMKilled",
}

IMPORTANT_WARNING_REASONS = {
    "BackOff",
    "Failed",
    "FailedScheduling",
    "FailedMount",
    "FailedPull",
    "ErrImagePull",
    "Unhealthy",
    "Killing",
    "OOMKilled",
    "Pulled",
    "Created",
    "Started",
}

LOG_PATTERN_DEFINITIONS: list[tuple[str, str, str]] = [
    ("OutOfMemory", "JavaScript heap out of memory", "critical"),
    ("OutOfMemory", "OutOfMemory", "critical"),
    ("Exception", "Exception", "warning"),
    ("Error", "Error", "warning"),
    ("FATAL", "FATAL", "critical"),
    ("ConnectionRefused", "Connection refused", "warning"),
    ("ConnectionTimeout", "Connection timeout", "warning"),
    ("ECONNRESET", "ECONNRESET", "warning"),
    ("ModuleNotFound", "Cannot find module", "warning"),
    ("ModuleNotFound", "Module not found", "warning"),
    ("PermissionDenied", "Permission denied", "warning"),
    ("MissingEnvVar", "Missing environment variable", "warning"),
]


def format_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _container_state_info(status) -> tuple[str, str | None, str | None]:
    state = status.state
    if state is None:
        return "unknown", None, None

    if state.running is not None:
        return "running", None, None

    if state.waiting is not None:
        return "waiting", state.waiting.reason, None

    if state.terminated is not None:
        return "terminated", None, state.terminated.reason

    return "unknown", None, None


def summarize_pod(pod) -> PodSummary:
    metadata = pod.metadata
    status = pod.status
    spec = pod.spec

    container_statuses = (status.container_statuses if status else None) or []
    containers: list[ContainerSummary] = []
    total_restarts = 0

    for container_status in container_statuses:
        state, waiting_reason, terminated_reason = _container_state_info(container_status)
        restart_count = container_status.restart_count or 0
        total_restarts += restart_count
        containers.append(
            ContainerSummary(
                name=container_status.name,
                ready=bool(container_status.ready),
                restart_count=restart_count,
                state=state,
                waiting_reason=waiting_reason,
                terminated_reason=terminated_reason,
            )
        )

    node_name = spec.node_name if spec else None
    host_ip = status.host_ip if status else None

    return PodSummary(
        name=metadata.name,
        namespace=metadata.namespace,
        phase=(status.phase if status else None) or "Unknown",
        node=node_name or host_ip,
        restart_count=total_restarts,
        containers=containers,
    )


def is_deployment_healthy(
    desired: int,
    available: int,
    ready: int,
    unavailable: int,
) -> bool:
    if desired == 0:
        return True
    return available >= desired and ready >= desired and unavailable == 0


def summarize_deployment(deployment) -> DeploymentSummary:
    metadata = deployment.metadata
    spec = deployment.spec
    status = deployment.status

    desired = spec.replicas if spec and spec.replicas is not None else 0
    available = status.available_replicas or 0 if status else 0
    ready = status.ready_replicas or 0 if status else 0
    unavailable = status.unavailable_replicas or 0 if status else 0

    return DeploymentSummary(
        name=metadata.name,
        namespace=metadata.namespace,
        desired_replicas=desired,
        available_replicas=available,
        ready_replicas=ready,
        unavailable_replicas=unavailable,
        healthy=is_deployment_healthy(desired, available, ready, unavailable),
    )


def summarize_event(event) -> EventSummary:
    involved_object = event.involved_object
    last_timestamp = event.last_timestamp or event.event_time or event.first_timestamp

    return EventSummary(
        type=event.type or "Unknown",
        reason=event.reason or "",
        message=event.message or "",
        object_kind=involved_object.kind if involved_object else "Unknown",
        object_name=involved_object.name if involved_object else "unknown",
        count=event.count,
        last_timestamp=format_timestamp(last_timestamp),
    )


def sort_events(events: list[EventSummary]) -> list[EventSummary]:
    def sort_key(item: EventSummary) -> str:
        return item.last_timestamp or ""

    return sorted(events, key=sort_key, reverse=True)


def detect_pod_issues(pod: PodSummary) -> list[HealthIssue]:
    issues: list[HealthIssue] = []

    if pod.phase == "Failed":
        issues.append(
            HealthIssue(
                severity="critical",
                type="FailedPod",
                resource_kind="Pod",
                resource_name=pod.name,
                message=f"Pod is in Failed phase",
            )
        )

    if pod.phase == "Pending":
        issues.append(
            HealthIssue(
                severity="warning",
                type="PendingPod",
                resource_kind="Pod",
                resource_name=pod.name,
                message="Pod is in Pending phase",
            )
        )

    for container in pod.containers:
        if container.waiting_reason in CRITICAL_WAITING_REASONS:
            issues.append(
                HealthIssue(
                    severity="critical",
                    type=container.waiting_reason,
                    resource_kind="Pod",
                    resource_name=pod.name,
                    message=f"Pod container '{container.name}' is in {container.waiting_reason}",
                )
            )

        if container.terminated_reason in CRITICAL_TERMINATED_REASONS:
            issues.append(
                HealthIssue(
                    severity="critical",
                    type=container.terminated_reason,
                    resource_kind="Pod",
                    resource_name=pod.name,
                    message=f"Pod container '{container.name}' was terminated with reason {container.terminated_reason}",
                )
            )

        if container.restart_count >= RESTART_THRESHOLD:
            issues.append(
                HealthIssue(
                    severity="warning",
                    type="HighRestartCount",
                    resource_kind="Pod",
                    resource_name=pod.name,
                    message=(
                        f"Container '{container.name}' has restart count "
                        f"{container.restart_count} (threshold {RESTART_THRESHOLD})"
                    ),
                )
            )

        if pod.phase == "Running" and not container.ready:
            issues.append(
                HealthIssue(
                    severity="warning",
                    type="ContainerNotReady",
                    resource_kind="Pod",
                    resource_name=pod.name,
                    message=f"Container '{container.name}' is not ready while pod is Running",
                )
            )

    return issues


def detect_deployment_issues(deployment: DeploymentSummary) -> list[HealthIssue]:
    if deployment.healthy:
        return []

    return [
        HealthIssue(
            severity="critical",
            type="DeploymentReplicaMismatch",
            resource_kind="Deployment",
            resource_name=deployment.name,
            message=(
                f"Deployment has {deployment.available_replicas} available replicas "
                f"out of {deployment.desired_replicas} desired replicas"
            ),
        )
    ]


def detect_event_issues(event: EventSummary) -> list[HealthIssue]:
    if event.type != "Warning":
        return []

    severity = "critical" if event.reason in IMPORTANT_WARNING_REASONS else "warning"
    return [
        HealthIssue(
            severity=severity,
            type=event.reason or "WarningEvent",
            resource_kind=event.object_kind,
            resource_name=event.object_name,
            message=event.message or f"Warning event: {event.reason}",
        )
    ]


def build_namespace_health(
    context_name: str,
    namespace: str,
    pods: list[PodSummary],
    deployments: list[DeploymentSummary],
    events: list[EventSummary],
) -> NamespaceHealthResponse:
    issues: list[HealthIssue] = []

    for pod in pods:
        issues.extend(detect_pod_issues(pod))

    for deployment in deployments:
        issues.extend(detect_deployment_issues(deployment))

    for event in events:
        issues.extend(detect_event_issues(event))

    running_pods = sum(1 for pod in pods if pod.phase == "Running")
    failed_pods = sum(1 for pod in pods if pod.phase == "Failed")
    pending_pods = sum(1 for pod in pods if pod.phase == "Pending")
    healthy_deployments = sum(1 for deployment in deployments if deployment.healthy)
    warning_events = sum(1 for event in events if event.type == "Warning")

    summary = HealthSummary(
        total_pods=len(pods),
        running_pods=running_pods,
        failed_pods=failed_pods,
        pending_pods=pending_pods,
        total_deployments=len(deployments),
        healthy_deployments=healthy_deployments,
        warning_events=warning_events,
        issues_count=len(issues),
    )

    status = "healthy" if not issues else "anomaly"
    message = "We are good here" if status == "healthy" else "Anomaly detected"

    return NamespaceHealthResponse(
        cluster_context=extract_cluster_display_name(context_name),
        namespace=namespace,
        status=status,
        message=message,
        summary=summary,
        issues=issues,
    )


def _last_terminated_details(container_status) -> tuple[str | None, int | None, str | None]:
    last_state = container_status.last_state
    if last_state and last_state.terminated:
        terminated = last_state.terminated
        exit_code = terminated.exit_code
        return (
            terminated.reason,
            exit_code if exit_code is not None else None,
            format_timestamp(terminated.finished_at),
        )
    return None, None, None


def _resource_fields_from_container_spec(container_spec) -> dict[str, str | None]:
    resources = container_spec.resources if container_spec else None
    limits = (resources.limits if resources else None) or {}
    requests = (resources.requests if resources else None) or {}
    return {
        "memory_limit": limits.get("memory"),
        "memory_request": requests.get("memory"),
        "cpu_limit": limits.get("cpu"),
        "cpu_request": requests.get("cpu"),
    }


def _resource_map_from_pod_spec(spec) -> dict[str, dict[str, str | None]]:
    mapping: dict[str, dict[str, str | None]] = {}
    if not spec:
        return mapping

    for container in (spec.containers or []):
        mapping[container.name] = _resource_fields_from_container_spec(container)
    for container in (spec.init_containers or []):
        mapping[container.name] = _resource_fields_from_container_spec(container)
    return mapping


def _build_pod_container_detail(
    container_status,
    resource_map: dict[str, dict[str, str | None]],
    *,
    init_container: bool = False,
) -> PodContainerDetail:
    state, waiting_reason, terminated_reason = _container_state_info(container_status)
    last_reason, last_exit_code, last_finished_at = _last_terminated_details(
        container_status
    )
    resources = resource_map.get(container_status.name, {})

    return PodContainerDetail(
        name=container_status.name,
        ready=bool(container_status.ready),
        restart_count=container_status.restart_count or 0,
        state=state,
        waiting_reason=waiting_reason,
        terminated_reason=terminated_reason,
        last_terminated_reason=last_reason,
        last_terminated_exit_code=last_exit_code,
        last_terminated_finished_at=last_finished_at,
        init_container=init_container,
        memory_limit=resources.get("memory_limit"),
        memory_request=resources.get("memory_request"),
        cpu_limit=resources.get("cpu_limit"),
        cpu_request=resources.get("cpu_request"),
    )


def describe_pod(pod) -> PodDescribeResponse:
    metadata = pod.metadata
    status = pod.status
    spec = pod.spec
    resource_map = _resource_map_from_pod_spec(spec)

    containers: list[PodContainerDetail] = []
    for container_status in (status.container_statuses if status else None) or []:
        containers.append(
            _build_pod_container_detail(
                container_status,
                resource_map,
                init_container=False,
            )
        )
    for container_status in (status.init_container_statuses if status else None) or []:
        containers.append(
            _build_pod_container_detail(
                container_status,
                resource_map,
                init_container=True,
            )
        )

    conditions: list[PodConditionDetail] = []
    for condition in (status.conditions if status else None) or []:
        conditions.append(
            PodConditionDetail(
                type=condition.type or "Unknown",
                status=condition.status or "Unknown",
                reason=condition.reason,
                message=condition.message,
                last_transition_time=format_timestamp(condition.last_transition_time),
            )
        )

    phase = (status.phase if status else None) or "Unknown"
    issues = _detect_describe_pod_issues(phase, containers)

    return PodDescribeResponse(
        pod_name=metadata.name,
        namespace=metadata.namespace,
        phase=phase,
        node_name=spec.node_name if spec else None,
        pod_ip=status.pod_ip if status else None,
        start_time=format_timestamp(status.start_time if status else None),
        containers=containers,
        conditions=conditions,
        issues=issues,
    )


def _detect_describe_pod_issues(
    phase: str,
    containers: list[PodContainerDetail],
) -> list[PodDescribeIssue]:
    issues: list[PodDescribeIssue] = []

    if phase == "Failed":
        issues.append(
            PodDescribeIssue(
                severity="critical",
                type="Failed",
                message="Pod is in Failed phase",
            )
        )

    if phase == "Pending":
        issues.append(
            PodDescribeIssue(
                severity="warning",
                type="Pending",
                message="Pod is in Pending phase",
            )
        )

    for container in containers:
        if container.waiting_reason in CRITICAL_WAITING_REASONS:
            issues.append(
                PodDescribeIssue(
                    severity="critical",
                    type=container.waiting_reason,
                    message=f"Container is waiting with reason {container.waiting_reason}",
                )
            )

        if container.terminated_reason in CRITICAL_TERMINATED_REASONS:
            issues.append(
                PodDescribeIssue(
                    severity="critical",
                    type=container.terminated_reason,
                    message=f"Container terminated with reason {container.terminated_reason}",
                )
            )

        if container.restart_count >= RESTART_THRESHOLD:
            issues.append(
                PodDescribeIssue(
                    severity="warning",
                    type="HighRestartCount",
                    message=(
                        f"Container '{container.name}' has restart count "
                        f"{container.restart_count} (threshold {RESTART_THRESHOLD})"
                    ),
                )
            )

        if phase == "Running" and not container.ready:
            issues.append(
                PodDescribeIssue(
                    severity="warning",
                    type="ContainerNotReady",
                    message=f"Container '{container.name}' is not ready while pod is Running",
                )
            )

    return issues


def _is_probable_oom_exit(container: PodContainerDetail) -> bool:
    if (
        container.last_terminated_reason == "OOMKilled"
        or container.terminated_reason == "OOMKilled"
    ):
        return True
    return container.last_terminated_exit_code == OOM_EXIT_CODE


def _container_has_oom_log_patterns(
    logs: list[PodLogsResponse] | None,
    pod_name: str,
    container_name: str,
) -> bool:
    if not logs:
        return False
    for entry in logs:
        if entry.pod_name != pod_name or entry.container != container_name:
            continue
        if any(pattern.type == "OutOfMemory" for pattern in entry.detected_patterns):
            return True
    return False


def _is_oom_container(
    container: PodContainerDetail,
    *,
    pod_name: str,
    logs: list[PodLogsResponse] | None = None,
) -> bool:
    if _is_probable_oom_exit(container):
        return True
    if container.restart_count >= RESTART_THRESHOLD and _container_has_oom_log_patterns(
        logs, pod_name, container.name
    ):
        return True
    return False


def _is_oom_related_event(event: EventSummary) -> bool:
    reason = (event.reason or "").lower()
    message = (event.message or "").lower()
    if "oom" in reason:
        return True
    oom_phrases = (
        "out of memory",
        "oomkilled",
        "memory cgroup",
        "killed process",
    )
    return any(phrase in message for phrase in oom_phrases)


def build_oom_investigations(
    pod_descriptions: list[PodDescribeResponse],
    events: list[EventSummary],
    logs: list[PodLogsResponse] | None = None,
) -> list[OomInvestigation]:
    investigations: list[OomInvestigation] = []

    for pod in pod_descriptions:
        oom_containers: list[OomContainerInvestigation] = []
        for container in pod.containers:
            if not _is_oom_container(container, pod_name=pod.pod_name, logs=logs):
                continue
            oom_containers.append(
                OomContainerInvestigation(
                    container=container.name,
                    init_container=container.init_container,
                    last_oom_at=container.last_terminated_finished_at,
                    exit_code=container.last_terminated_exit_code,
                    restart_count=container.restart_count,
                    state=container.state,
                    memory_limit=container.memory_limit,
                    memory_request=container.memory_request,
                    cpu_limit=container.cpu_limit,
                    cpu_request=container.cpu_request,
                    has_memory_limit=bool(container.memory_limit),
                )
            )

        related_events = [
            OomEventDetail(
                reason=event.reason,
                message=event.message,
                last_timestamp=event.last_timestamp,
            )
            for event in events
            if event.object_name == pod.pod_name and _is_oom_related_event(event)
        ]

        if not oom_containers and not related_events:
            continue

        investigations.append(
            OomInvestigation(
                pod_name=pod.pod_name,
                namespace=pod.namespace,
                containers=oom_containers,
                related_events=related_events,
            )
        )

    return investigations


def detect_log_patterns(logs: str) -> list[LogPatternMatch]:
    if not logs:
        return []

    matches: list[LogPatternMatch] = []
    seen: set[tuple[str, str]] = set()

    for line in logs.splitlines():
        for pattern_type, needle, severity in LOG_PATTERN_DEFINITIONS:
            if needle in line:
                key = (pattern_type, needle)
                if key not in seen:
                    seen.add(key)
                    matches.append(
                        LogPatternMatch(
                            type=pattern_type,
                            matched_text=needle,
                            severity=severity,
                        )
                    )

    return matches


def filter_events_for_pod(events: list[EventSummary], pod_name: str) -> list[EventSummary]:
    filtered = [
        event
        for event in events
        if event.object_name == pod_name
        or pod_name in event.message
    ]
    return sort_events(filtered)


def find_deployment_for_pod(pod, deployments: list) -> object | None:
    pod_labels = (pod.metadata.labels if pod.metadata else None) or {}

    for deployment in deployments:
        selector = deployment.spec.selector.match_labels if deployment.spec and deployment.spec.selector else {}
        if selector and all(pod_labels.get(key) == value for key, value in selector.items()):
            return deployment

    return None


def inspect_deployment(deployment, related_pods: list[str] | None = None) -> DeploymentInspection:
    summary = summarize_deployment(deployment)
    status = deployment.status

    conditions: list[DeploymentConditionDetail] = []
    for condition in (status.conditions if status else None) or []:
        conditions.append(
            DeploymentConditionDetail(
                type=condition.type or "Unknown",
                status=condition.status or "Unknown",
                reason=condition.reason,
                message=condition.message,
                last_transition_time=format_timestamp(condition.last_transition_time),
            )
        )

    issues: list[DeploymentInspectIssue] = []
    if not summary.healthy:
        issues.append(
            DeploymentInspectIssue(
                severity="critical",
                type="DeploymentReplicaMismatch",
                message=(
                    f"Deployment has {summary.available_replicas} available replicas "
                    f"out of {summary.desired_replicas} desired replicas"
                ),
            )
        )

    for condition in conditions:
        if condition.type == "Progressing" and condition.status == "False":
            issues.append(
                DeploymentInspectIssue(
                    severity="warning",
                    type="RolloutIssue",
                    message=condition.message or "Deployment rollout is not progressing",
                )
            )
        if condition.type == "Available" and condition.status == "False":
            issues.append(
                DeploymentInspectIssue(
                    severity="critical",
                    type="DeploymentUnavailable",
                    message=condition.message or "Deployment is not available",
                )
            )

    return DeploymentInspection(
        name=summary.name,
        namespace=summary.namespace,
        desired_replicas=summary.desired_replicas,
        available_replicas=summary.available_replicas,
        ready_replicas=summary.ready_replicas,
        unavailable_replicas=summary.unavailable_replicas,
        healthy=summary.healthy,
        conditions=conditions,
        related_pods=related_pods or [],
        issues=issues,
    )


def summarize_node(node) -> NodeSummary:
    metadata = node.metadata
    status = node.status
    labels = metadata.labels or {}
    capacity = status.capacity or {}
    allocatable = status.allocatable or {}

    conditions: list[NodeConditionDetail] = []
    ready = False
    for condition in status.conditions or []:
        if condition.type == "Ready":
            ready = condition.status == "True"
        conditions.append(
            NodeConditionDetail(
                type=condition.type or "Unknown",
                status=condition.status or "Unknown",
                reason=condition.reason,
                message=condition.message,
            )
        )

    return NodeSummary(
        name=metadata.name,
        ready=ready,
        kubernetes_version=status.node_info.kubelet_version if status.node_info else None,
        os_image=status.node_info.os_image if status.node_info else None,
        instance_type=labels.get("node.kubernetes.io/instance-type")
        or labels.get("beta.kubernetes.io/instance-type"),
        capacity_cpu=capacity.get("cpu"),
        capacity_memory=capacity.get("memory"),
        allocatable_cpu=allocatable.get("cpu"),
        allocatable_memory=allocatable.get("memory"),
        conditions=conditions,
    )


def build_pod_scoped_health(
    context_name: str,
    namespace: str,
    pod_description: PodDescribeResponse,
) -> NamespaceHealthResponse:
    """Build a health summary scoped to a single pod (no full namespace scan)."""
    issues = [
        HealthIssue(
            severity=issue.severity,
            type=issue.type,
            resource_kind="Pod",
            resource_name=pod_description.pod_name,
            message=issue.message,
        )
        for issue in pod_description.issues
    ]

    summary = HealthSummary(
        total_pods=1,
        running_pods=1 if pod_description.phase == "Running" else 0,
        failed_pods=1 if pod_description.phase == "Failed" else 0,
        pending_pods=1 if pod_description.phase == "Pending" else 0,
        total_deployments=0,
        healthy_deployments=0,
        warning_events=0,
        issues_count=len(issues),
    )

    status = "healthy" if not issues else "anomaly"
    message = "We are good here" if status == "healthy" else "Anomaly detected"

    return NamespaceHealthResponse(
        cluster_context=extract_cluster_display_name(context_name),
        namespace=namespace,
        status=status,
        message=message,
        summary=summary,
        issues=issues,
    )


def extract_affected_pod_names(namespace_health: NamespaceHealthResponse) -> list[str]:
    pod_names: list[str] = []
    for issue in namespace_health.issues:
        if issue.resource_kind == "Pod" and issue.resource_name not in pod_names:
            pod_names.append(issue.resource_name)
    return pod_names


def extract_affected_deployment_names(namespace_health: NamespaceHealthResponse) -> list[str]:
    deployment_names: list[str] = []
    for issue in namespace_health.issues:
        if issue.resource_kind == "Deployment" and issue.resource_name not in deployment_names:
            deployment_names.append(issue.resource_name)
    return deployment_names


def build_restart_investigation_context(
    pod_descriptions: list[PodDescribeResponse],
) -> dict:
    """Summarize restart-related facts and evidence gaps for AI reasoning guardrails."""
    high_restart_containers: list[dict] = []
    missing_last_termination: list[str] = []

    for pod in pod_descriptions:
        for container in pod.containers:
            if container.restart_count < RESTART_THRESHOLD:
                continue

            entry = {
                "pod": pod.pod_name,
                "container": container.name,
                "restart_count": container.restart_count,
                "state": container.state,
                "ready": container.ready,
                "last_terminated_reason": container.last_terminated_reason,
                "last_terminated_exit_code": container.last_terminated_exit_code,
                "last_terminated_finished_at": container.last_terminated_finished_at,
            }
            high_restart_containers.append(entry)

            if (
                container.last_terminated_reason is None
                and container.last_terminated_exit_code is None
            ):
                missing_last_termination.append(f"{pod.pod_name}/{container.name}")

    restart_cause_known = bool(high_restart_containers) and not missing_last_termination
    return {
        "high_restart_containers": high_restart_containers,
        "missing_last_termination_details": missing_last_termination,
        "restart_cause_known": restart_cause_known,
        "confidence_cap_when_restart_cause_unknown": 55,
        "missing_evidence": [
            *(
                [
                    "last container termination reason/exit code for restarted containers"
                ]
                if missing_last_termination
                else []
            ),
            "liveness/readiness probe configuration",
            "container resource requests/limits and live usage",
            "restart timestamps across deployment replicas",
        ],
    }


def build_ai_evidence_summary(
    namespace_health: NamespaceHealthResponse,
    pod_descriptions: list[PodDescribeResponse],
    logs: list,
    events: list[EventSummary],
    deployments: list[DeploymentInspection],
    nodes: list[NodeSummary],
) -> dict:
    restart_context = build_restart_investigation_context(pod_descriptions)
    oom_investigations = build_oom_investigations(pod_descriptions, events, logs)
    oom_context = {
        "has_oom": bool(oom_investigations),
        "affected_pods": [item.pod_name for item in oom_investigations],
        "investigations": [item.model_dump() for item in oom_investigations],
        "missing_evidence": [
            "historical memory utilization at time of OOM kill (requires metrics-server or observability platform)"
        ]
        if oom_investigations
        else [],
    }
    return {
        "namespace_status": namespace_health.status,
        "namespace_message": namespace_health.message,
        "issues_count": namespace_health.summary.issues_count,
        "affected_pods": [pod.pod_name for pod in pod_descriptions],
        "pod_issue_types": sorted({issue.type for pod in pod_descriptions for issue in pod.issues}),
        "log_pattern_types": sorted({pattern.type for entry in logs for pattern in entry.detected_patterns}),
        "warning_event_reasons": sorted(
            {event.reason for event in events if event.type == "Warning"}
        ),
        "deployment_issue_types": sorted(
            {issue.type for deployment in deployments for issue in deployment.issues}
        ),
        "oom_investigation": oom_context,
        "node_names": [node.name for node in nodes],
        "unready_nodes": [node.name for node in nodes if not node.ready],
        "restart_investigation": restart_context,
    }
