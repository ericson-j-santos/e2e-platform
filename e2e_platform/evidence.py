from __future__ import annotations

from datetime import datetime
import re
from typing import Any

REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
STATUS_ALLOWED = {"passed", "blocked", "failed"}


class EvidenceValidationError(ValueError):
    """Raised when E2E evidence does not satisfy the fail-closed contract."""


def _require_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise EvidenceValidationError(f"{field}: required non-empty string")
    return value.strip()


def _parse_time(value: str, field: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise EvidenceValidationError(f"{field}: invalid ISO-8601 timestamp") from exc


def _require_check(
    payload: dict[str, Any],
    field: str,
    *,
    optional_when_not_applicable: bool,
) -> None:
    value = payload.get(field)
    if not isinstance(value, dict):
        raise EvidenceValidationError(f"{field}: required object")

    applicable = value.get("applicable", True)
    if not isinstance(applicable, bool):
        raise EvidenceValidationError(f"{field}.applicable: required boolean")

    if not applicable and optional_when_not_applicable:
        return

    if value.get("passed") is not True:
        raise EvidenceValidationError(f"{field}.passed: must be true")

    evidence = value.get("evidence")
    if not isinstance(evidence, str) or not evidence.strip():
        raise EvidenceValidationError(f"{field}.evidence: required when applicable")


def validate_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise EvidenceValidationError("root: expected object")

    if payload.get("schema_version") != "1.0.0":
        raise EvidenceValidationError("schema_version: expected 1.0.0")

    project = _require_text(payload, "project")
    repository = _require_text(payload, "repository")
    sha = _require_text(payload, "sha")
    environment = _require_text(payload, "environment")
    correlation_id = _require_text(payload, "correlation_id")
    objective = _require_text(payload, "objective")

    if not REPOSITORY_RE.fullmatch(repository):
        raise EvidenceValidationError("repository: expected owner/name")
    if not SHA_RE.fullmatch(sha):
        raise EvidenceValidationError("sha: expected full 40-character commit SHA")
    if len(correlation_id) < 8:
        raise EvidenceValidationError("correlation_id: too short")

    status = payload.get("status")
    if status not in STATUS_ALLOWED:
        raise EvidenceValidationError("status: invalid value")
    if status != "passed":
        raise EvidenceValidationError(f"status: evidence is not approved ({status})")

    started_at = _parse_time(_require_text(payload, "started_at"), "started_at")
    completed_at = _parse_time(_require_text(payload, "completed_at"), "completed_at")
    if completed_at < started_at:
        raise EvidenceValidationError("completed_at: precedes started_at")

    _require_check(payload, "positive_control", optional_when_not_applicable=False)
    _require_check(payload, "negative_control", optional_when_not_applicable=True)
    _require_check(payload, "idempotency", optional_when_not_applicable=True)
    _require_check(payload, "test_of_test", optional_when_not_applicable=True)

    independent = payload.get("independent_read")
    if not isinstance(independent, dict):
        raise EvidenceValidationError("independent_read: required object")
    if independent.get("passed") is not True:
        raise EvidenceValidationError("independent_read.passed: must be true")
    source = independent.get("source")
    evidence = independent.get("evidence")
    if not isinstance(source, str) or not source.strip():
        raise EvidenceValidationError("independent_read.source: required")
    if not isinstance(evidence, str) or not evidence.strip():
        raise EvidenceValidationError("independent_read.evidence: required")

    return {
        "result": "E2E_EVIDENCE_VALID",
        "schema_version": "1.0.0",
        "project": project,
        "repository": repository,
        "sha": sha.lower(),
        "environment": environment,
        "correlation_id": correlation_id,
        "objective": objective,
    }
