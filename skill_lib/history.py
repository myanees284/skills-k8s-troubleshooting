"""Local JSON file persistence for investigation history."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from skill_lib.formatters import InvestigationResponse


DEFAULT_HISTORY_PATH = Path.home() / ".eks-k8s-troubleshooting" / "history.json"


class InvestigationNotFoundError(Exception):
    def __init__(self, investigation_id: int) -> None:
        super().__init__(f"Investigation {investigation_id} not found.")
        self.message = f"Investigation {investigation_id} not found."
        self.error_type = "investigation_not_found"


class InvestigationSummary(BaseModel):
    id: int
    created_at: str
    cluster: str
    namespace: str
    service_name: str
    issue_type: str
    status: str
    risk_level: str


class InvestigationDetail(BaseModel):
    id: int
    created_at: str
    cluster: str
    namespace: str
    service_name: str
    issue_type: str
    status: str
    risk_level: str
    executive_summary: str | None = None
    root_cause: str | None = None
    suggested_actions: str | None = None
    investigation: InvestigationResponse


class SimilarInvestigationsResult(BaseModel):
    count: int
    similar_investigations: list[InvestigationSummary]


def get_history_path() -> Path:
    override = os.environ.get("K8S_TROUBLESHOOTING_HISTORY_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return DEFAULT_HISTORY_PATH


def _ensure_store(path: Path) -> dict[str, Any]:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        store = {"next_id": 1, "investigations": []}
        _write_store(path, store)
        return store

    with path.open("r", encoding="utf-8") as handle:
        store = json.load(handle)

    store.setdefault("next_id", 1)
    store.setdefault("investigations", [])
    return store


def _write_store(path: Path, store: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as handle:
        json.dump(store, handle, indent=2)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def _extract_cluster_name(cluster_context: str) -> str:
    if "/cluster/" in cluster_context:
        return cluster_context.split("/cluster/")[-1]
    return cluster_context


def _extract_service_name(investigation: InvestigationResponse) -> str:
    evidence = investigation.evidence

    for deployment in evidence.deployments:
        if deployment.issues:
            return deployment.name

    for issue in evidence.namespace_health.issues:
        if issue.resource_kind == "Deployment":
            return issue.resource_name

    if evidence.pods:
        pod_name = evidence.pods[0].pod_name
        parts = pod_name.rsplit("-", 2)
        if len(parts) == 3:
            return parts[0]

    return investigation.namespace


def _extract_issue_type(investigation: InvestigationResponse) -> str:
    summary = investigation.ai_reasoning_context.evidence_summary

    pod_types = summary.get("pod_issue_types") or []
    if pod_types:
        return str(pod_types[0])

    log_types = summary.get("log_pattern_types") or []
    if log_types:
        return str(log_types[0])

    deployment_types = summary.get("deployment_issue_types") or []
    if deployment_types:
        return str(deployment_types[0])

    if investigation.evidence.namespace_health.issues:
        return investigation.evidence.namespace_health.issues[0].type

    return "Unknown"


def _record_to_summary(record: dict[str, Any]) -> InvestigationSummary:
    return InvestigationSummary(
        id=record["id"],
        created_at=record["created_at"],
        cluster=record["cluster"],
        namespace=record["namespace"],
        service_name=record["service_name"],
        issue_type=record["issue_type"],
        status=record["status"],
        risk_level=record.get("risk_level") or "Unknown",
    )


def _record_to_detail(record: dict[str, Any]) -> InvestigationDetail:
    return InvestigationDetail(
        id=record["id"],
        created_at=record["created_at"],
        cluster=record["cluster"],
        namespace=record["namespace"],
        service_name=record["service_name"],
        issue_type=record["issue_type"],
        status=record["status"],
        risk_level=record.get("risk_level") or "Unknown",
        executive_summary=record.get("executive_summary"),
        root_cause=record.get("root_cause"),
        suggested_actions=record.get("suggested_actions"),
        investigation=InvestigationResponse.model_validate(record["investigation"]),
    )


def save_investigation(
    investigation: InvestigationResponse,
    *,
    executive_summary: str | None = None,
    root_cause: str | None = None,
    suggested_actions: str | None = None,
    risk_level: str | None = None,
    history_path: Path | None = None,
) -> dict[str, Any]:
    path = history_path or get_history_path()
    store = _ensure_store(path)

    investigation_id = store["next_id"]
    record = {
        "id": investigation_id,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "cluster": _extract_cluster_name(investigation.cluster_context),
        "namespace": investigation.namespace,
        "service_name": _extract_service_name(investigation),
        "issue_type": _extract_issue_type(investigation),
        "status": investigation.investigation_status,
        "risk_level": risk_level or "Unknown",
        "executive_summary": executive_summary,
        "root_cause": root_cause,
        "suggested_actions": suggested_actions,
        "investigation": investigation.model_dump(),
    }

    store["investigations"].append(record)
    store["next_id"] = investigation_id + 1
    _write_store(path, store)

    return {
        "id": investigation_id,
        "path": str(path),
        "summary": _record_to_summary(record).model_dump(),
    }


def list_investigations(history_path: Path | None = None) -> list[InvestigationSummary]:
    path = history_path or get_history_path()
    if not path.exists():
        return []

    store = _ensure_store(path)
    records = sorted(
        store["investigations"],
        key=lambda item: (item.get("created_at", ""), item.get("id", 0)),
        reverse=True,
    )
    return [_record_to_summary(record) for record in records]


def get_investigation(
    investigation_id: int,
    history_path: Path | None = None,
) -> InvestigationDetail:
    path = history_path or get_history_path()
    store = _ensure_store(path)

    for record in store["investigations"]:
        if record.get("id") == investigation_id:
            return _record_to_detail(record)

    raise InvestigationNotFoundError(investigation_id)


def search_investigations(
    *,
    q: str | None = None,
    issue_type: str | None = None,
    service_name: str | None = None,
    namespace: str | None = None,
    risk_level: str | None = None,
    history_path: Path | None = None,
) -> list[InvestigationSummary]:
    path = history_path or get_history_path()
    if not path.exists():
        return []

    store = _ensure_store(path)
    records = sorted(
        store["investigations"],
        key=lambda item: (item.get("created_at", ""), item.get("id", 0)),
        reverse=True,
    )

    results: list[dict[str, Any]] = []
    for record in records:
        if issue_type and record.get("issue_type", "").lower() != issue_type.lower():
            continue
        if service_name and service_name.lower() not in record.get("service_name", "").lower():
            continue
        if namespace and record.get("namespace", "").lower() != namespace.lower():
            continue
        if risk_level and record.get("risk_level", "").lower() != risk_level.lower():
            continue

        if q:
            keyword = q.lower()
            searchable = " ".join(
                [
                    str(record.get("issue_type", "")),
                    str(record.get("service_name", "")),
                    str(record.get("namespace", "")),
                    str(record.get("cluster", "")),
                    str(record.get("executive_summary", "") or ""),
                    str(record.get("root_cause", "") or ""),
                    str(record.get("suggested_actions", "") or ""),
                    json.dumps(record.get("investigation", {})),
                ]
            ).lower()
            if keyword not in searchable:
                continue

        results.append(record)

    return [_record_to_summary(record) for record in results]


def find_similar_investigations(
    *,
    issue_type: str | None = None,
    service_name: str | None = None,
    namespace: str | None = None,
    exclude_id: int | None = None,
    history_path: Path | None = None,
) -> SimilarInvestigationsResult:
    path = history_path or get_history_path()
    if not path.exists():
        return SimilarInvestigationsResult(count=0, similar_investigations=[])

    store = _ensure_store(path)
    records = sorted(
        store["investigations"],
        key=lambda item: (item.get("created_at", ""), item.get("id", 0)),
        reverse=True,
    )

    scored: list[tuple[int, dict[str, Any]]] = []
    for record in records:
        if exclude_id is not None and record.get("id") == exclude_id:
            continue

        score = 0
        if (
            service_name
            and issue_type
            and record.get("service_name", "").lower() == service_name.lower()
            and record.get("issue_type", "").lower() == issue_type.lower()
        ):
            score = 3
        elif issue_type and record.get("issue_type", "").lower() == issue_type.lower():
            score = 2
        elif namespace and record.get("namespace", "").lower() == namespace.lower():
            score = 1

        if score > 0:
            scored.append((score, record))

    scored.sort(
        key=lambda item: (
            -item[0],
            item[1].get("created_at", ""),
            -item[1].get("id", 0),
        )
    )

    summaries = [_record_to_summary(record) for _, record in scored]
    return SimilarInvestigationsResult(count=len(summaries), similar_investigations=summaries)


def load_investigation_payload(data: dict[str, Any]) -> InvestigationResponse:
    if "evidence" in data:
        return InvestigationResponse.model_validate(data)
    if "investigation" in data:
        return InvestigationResponse.model_validate(data["investigation"])
    raise ValueError(
        "Input JSON must be an investigation result (from investigate_pod.py or investigate_namespace.py)."
    )
