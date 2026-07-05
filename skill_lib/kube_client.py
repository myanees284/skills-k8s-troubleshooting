"""Kubernetes client utilities for reading kubeconfig and calling the API (read-only)."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from kubernetes.config import KUBE_CONFIG_DEFAULT_LOCATION, list_kube_config_contexts

logger = logging.getLogger(__name__)


class SkillError(Exception):
    def __init__(self, message: str, error_type: str | None = None):
        super().__init__(message)
        self.message = message
        self.error_type = error_type or self.__class__.__name__


class KubeconfigNotFoundError(SkillError):
    pass


class InvalidContextError(SkillError):
    pass


class SessionExpiredError(SkillError):
    pass


class ClusterUnreachableError(SkillError):
    pass


class InvalidNamespaceError(SkillError):
    pass


class PermissionDeniedError(SkillError):
    pass


class PodNotFoundError(SkillError):
    pass


class ContainerNotFoundError(SkillError):
    pass


def get_kubeconfig_path() -> str:
    return os.environ.get("KUBECONFIG", KUBE_CONFIG_DEFAULT_LOCATION)


def _ensure_kubeconfig_exists() -> str:
    kubeconfig_path = get_kubeconfig_path()
    if not Path(kubeconfig_path).expanduser().exists():
        raise KubeconfigNotFoundError(
            f"Kubeconfig not found at {kubeconfig_path}. "
            "Ensure ~/.kube/config exists and cluster credentials are valid.",
            error_type="kubeconfig_not_found",
        )
    return str(Path(kubeconfig_path).expanduser())


def extract_cluster_display_name(cluster_ref: str) -> str:
    if "/" in cluster_ref:
        return cluster_ref.rsplit("/", 1)[-1]
    return cluster_ref


def list_available_contexts() -> tuple[list[dict[str, str]], str | None]:
    kubeconfig_path = _ensure_kubeconfig_exists()
    try:
        contexts, active_context = list_kube_config_contexts(config_file=kubeconfig_path)
    except Exception as exc:
        logger.error("Failed to read kubeconfig contexts: %s", exc)
        raise KubeconfigNotFoundError(
            f"Unable to read kubeconfig at {kubeconfig_path}: {exc}",
            error_type="kubeconfig_read_error",
        ) from exc

    result: list[dict[str, str]] = []
    active_name = active_context["name"] if active_context else None

    for ctx in contexts:
        cluster_ref = ctx["context"].get("cluster", ctx["name"])
        result.append(
            {
                "name": extract_cluster_display_name(cluster_ref),
                "context": ctx["name"],
            }
        )

    return result, active_name


def validate_context_exists(context_name: str) -> None:
    contexts, _ = list_available_contexts()
    known = {item["context"] for item in contexts}
    if context_name not in known:
        raise InvalidContextError(
            f"Context '{context_name}' not found in kubeconfig. "
            f"Available contexts: {', '.join(sorted(known)) or 'none'}",
            error_type="invalid_context",
        )


def get_kubeconfig_current_context() -> str:
    _, active_context = list_available_contexts()
    if not active_context:
        raise InvalidContextError(
            "No current context is set in kubeconfig.",
            error_type="no_current_context",
        )
    return active_context


def _translate_api_exception(exc: ApiException) -> SkillError:
    status = exc.status or 0
    body = exc.body or ""

    if status == 401:
        return SessionExpiredError(
            "Cluster credentials appear expired or invalid. Re-authenticate and refresh kubeconfig.",
            error_type="session_expired",
        )

    if status == 403:
        return PermissionDeniedError(
            "Permission denied accessing Kubernetes resources. Check cluster RBAC permissions.",
            error_type="permission_denied",
        )

    if status == 404:
        return ClusterUnreachableError(
            "Kubernetes API endpoint not found. The cluster may be unreachable or misconfigured.",
            error_type="cluster_unreachable",
        )

    return ClusterUnreachableError(
        f"Kubernetes API error (HTTP {status}): {body}",
        error_type="kubernetes_api_error",
    )


def _build_api_client(context_name: str):
    kubeconfig_path = _ensure_kubeconfig_exists()
    validate_context_exists(context_name)

    try:
        config.load_kube_config(config_file=kubeconfig_path, context=context_name)
        configuration = client.Configuration.get_default_copy()
        return client.ApiClient(configuration=configuration)
    except config.ConfigException as exc:
        logger.error("Failed to load kubeconfig for context '%s': %s", context_name, exc)
        raise InvalidContextError(
            f"Failed to load context '{context_name}': {exc}",
            error_type="invalid_context",
        ) from exc
    except OSError as exc:
        logger.error("Network error connecting to cluster '%s': %s", context_name, exc)
        raise ClusterUnreachableError(
            f"Cluster unreachable for context '{context_name}': {exc}",
            error_type="cluster_unreachable",
        ) from exc


def get_core_v1_api(context_name: str) -> client.CoreV1Api:
    return client.CoreV1Api(_build_api_client(context_name))


def get_apps_v1_api(context_name: str) -> client.AppsV1Api:
    return client.AppsV1Api(_build_api_client(context_name))


def _call_namespaced_api(context_name: str, namespace: str, operation, resource_label: str):
    try:
        return operation()
    except ApiException as exc:
        if exc.status == 404:
            raise InvalidNamespaceError(
                f"Namespace '{namespace}' not found in cluster.",
                error_type="invalid_namespace",
            ) from exc
        logger.error(
            "Kubernetes API error fetching %s for namespace '%s' in context '%s': %s",
            resource_label,
            namespace,
            context_name,
            exc,
        )
        raise _translate_api_exception(exc) from exc
    except Exception as exc:
        logger.error(
            "Unexpected error fetching %s for namespace '%s' in context '%s': %s",
            resource_label,
            namespace,
            context_name,
            exc,
        )
        raise ClusterUnreachableError(
            f"Failed to fetch {resource_label} for namespace '{namespace}': {exc}",
            error_type="cluster_unreachable",
        ) from exc


def validate_namespace_exists(context_name: str, namespace_name: str) -> None:
    core_v1 = get_core_v1_api(context_name)
    try:
        core_v1.read_namespace(name=namespace_name, _request_timeout=30)
    except ApiException as exc:
        if exc.status == 404:
            raise InvalidNamespaceError(
                f"Namespace '{namespace_name}' not found in cluster.",
                error_type="invalid_namespace",
            ) from exc
        logger.error(
            "Kubernetes API error validating namespace '%s': %s",
            namespace_name,
            exc,
        )
        raise _translate_api_exception(exc) from exc


def list_pods_for_namespace(context_name: str, namespace: str) -> list:
    core_v1 = get_core_v1_api(context_name)

    def operation():
        return core_v1.list_namespaced_pod(namespace=namespace, _request_timeout=30).items

    return _call_namespaced_api(context_name, namespace, operation, "pods")


def list_deployments_for_namespace(context_name: str, namespace: str) -> list:
    apps_v1 = get_apps_v1_api(context_name)

    def operation():
        return apps_v1.list_namespaced_deployment(namespace=namespace, _request_timeout=30).items

    return _call_namespaced_api(context_name, namespace, operation, "deployments")


def list_events_for_namespace(context_name: str, namespace: str) -> list:
    core_v1 = get_core_v1_api(context_name)

    def operation():
        return core_v1.list_namespaced_event(namespace=namespace, _request_timeout=30).items

    return _call_namespaced_api(context_name, namespace, operation, "events")


def _call_pod_api(context_name: str, namespace: str, pod_name: str, operation, resource_label: str):
    try:
        return operation()
    except ApiException as exc:
        if exc.status == 404:
            raise PodNotFoundError(
                f"Pod '{pod_name}' not found in namespace '{namespace}'.",
                error_type="pod_not_found",
            ) from exc
        logger.error(
            "Kubernetes API error fetching %s for pod '%s' in namespace '%s': %s",
            resource_label,
            pod_name,
            namespace,
            exc,
        )
        raise _translate_api_exception(exc) from exc
    except Exception as exc:
        logger.error(
            "Unexpected error fetching %s for pod '%s' in namespace '%s': %s",
            resource_label,
            pod_name,
            namespace,
            exc,
        )
        raise ClusterUnreachableError(
            f"Failed to fetch {resource_label} for pod '{pod_name}': {exc}",
            error_type="cluster_unreachable",
        ) from exc


def read_pod_for_namespace(context_name: str, namespace: str, pod_name: str):
    core_v1 = get_core_v1_api(context_name)

    def operation():
        return core_v1.read_namespaced_pod(
            name=pod_name,
            namespace=namespace,
            _request_timeout=30,
        )

    return _call_pod_api(context_name, namespace, pod_name, operation, "pod details")


def _decode_log_response(log_data) -> str:
    if log_data is None:
        return ""
    if isinstance(log_data, bytes):
        return log_data.decode("utf-8", errors="replace")
    return str(log_data)


def get_pod_logs(
    context_name: str,
    namespace: str,
    pod_name: str,
    container: str,
    tail_lines: int = 100,
    previous: bool = False,
) -> str:
    core_v1 = get_core_v1_api(context_name)

    def operation():
        return core_v1.read_namespaced_pod_log(
            name=pod_name,
            namespace=namespace,
            container=container,
            tail_lines=tail_lines,
            previous=previous,
            _request_timeout=30,
        )

    try:
        return _decode_log_response(operation())
    except ApiException as exc:
        if exc.status == 404:
            if previous:
                return ""
            raise ContainerNotFoundError(
                f"Container '{container}' not found for pod '{pod_name}' in namespace '{namespace}'.",
                error_type="container_not_found",
            ) from exc
        if exc.status == 400:
            logger.info(
                "No logs available for pod '%s' container '%s': %s",
                pod_name,
                container,
                exc.body or exc.reason,
            )
            return ""
        logger.error(
            "Kubernetes API error fetching logs for pod '%s' container '%s': %s",
            pod_name,
            container,
            exc,
        )
        raise _translate_api_exception(exc) from exc
    except Exception as exc:
        logger.error(
            "Unexpected error fetching logs for pod '%s' container '%s': %s",
            pod_name,
            container,
            exc,
        )
        raise ClusterUnreachableError(
            f"Failed to fetch logs for pod '{pod_name}' container '{container}': {exc}",
            error_type="cluster_unreachable",
        ) from exc


def read_node_for_context(context_name: str, node_name: str):
    core_v1 = get_core_v1_api(context_name)

    try:
        return core_v1.read_node(name=node_name, _request_timeout=30)
    except ApiException as exc:
        logger.error("Kubernetes API error reading node '%s': %s", node_name, exc)
        raise _translate_api_exception(exc) from exc
    except Exception as exc:
        logger.error("Unexpected error reading node '%s': %s", node_name, exc)
        raise ClusterUnreachableError(
            f"Failed to read node '{node_name}': {exc}",
            error_type="cluster_unreachable",
        ) from exc


def list_nodes_for_context(context_name: str) -> list:
    core_v1 = get_core_v1_api(context_name)

    try:
        return core_v1.list_node(_request_timeout=30).items
    except ApiException as exc:
        logger.error("Kubernetes API error listing nodes: %s", exc)
        raise _translate_api_exception(exc) from exc
    except Exception as exc:
        logger.error("Unexpected error listing nodes: %s", exc)
        raise ClusterUnreachableError(
            f"Failed to list nodes: {exc}",
            error_type="cluster_unreachable",
        ) from exc


def list_namespaces_for_context(context_name: str) -> list[str]:
    core_v1 = get_core_v1_api(context_name)

    try:
        response = core_v1.list_namespace(_request_timeout=30)
        return sorted(ns.metadata.name for ns in response.items if ns.metadata and ns.metadata.name)
    except ApiException as exc:
        logger.error(
            "Kubernetes API error listing namespaces for context '%s': %s",
            context_name,
            exc,
        )
        raise _translate_api_exception(exc) from exc
    except Exception as exc:
        logger.error(
            "Unexpected error listing namespaces for context '%s': %s",
            context_name,
            exc,
        )
        raise ClusterUnreachableError(
            f"Failed to list namespaces for context '{context_name}': {exc}",
            error_type="cluster_unreachable",
        ) from exc
