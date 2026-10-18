from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
TIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$"
)
STATUS_ALLOWED = {"passed", "blocked", "failed"}
ROOT_FIELDS = {
    "schema_version", "project", "repository", "sha", "environment",
    "correlation_id", "objective", "status", "started_at", "completed_at",
    "positive_control", "negative_control", "independent_read",
    "idempotency", "test_of_test",
}


class EvidenceValidationError(ValueError):
    """Raised when E2E evidence does not satisfy the fail-closed contract."""


def _exact_object(value: Any, fields: set[str], field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceValidationError(f"{field}: expected object")
    missing = fields - value.keys()
    if missing:
        raise EvidenceValidationError(f"{field}: missing fields: {', '.join(sorted(missing))}")
    if value.keys() - fields:
        raise EvidenceValidationError(f"{field}: unexpected fields")
    for item in value.values():
        if isinstance(item, str):
            try:
                item.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise EvidenceValidationError(f"{field}: invalid Unicode text") from exc
    return value


def _require_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise EvidenceValidationError(f"{field}: required non-empty string")
    return value.strip()


def _parse_time(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not TIME_RE.fullmatch(value) or value.endswith("-00:00"):
        raise EvidenceValidationError(f"{field}: expected RFC3339 timestamp with explicit timezone")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timezone required")
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise EvidenceValidationError(f"{field}: invalid RFC3339 timestamp") from exc


def _require_check(payload: dict[str, Any], field: str, *, optional: bool) -> None:
    fields = {"applicable", "passed", "evidence"} if optional else {"passed", "evidence"}
    value = _exact_object(payload.get(field), fields, field)
    if not isinstance(value["evidence"], str):
        raise EvidenceValidationError(f"{field}.evidence: required string")
    if optional:
        if not isinstance(value["applicable"], bool):
            raise EvidenceValidationError(f"{field}.applicable: required boolean")
        if value["passed"] is not None and not isinstance(value["passed"], bool):
            raise EvidenceValidationError(f"{field}.passed: expected boolean or null")
        if not value["applicable"]:
            return
    if value["passed"] is not True:
        raise EvidenceValidationError(f"{field}.passed: must be true")
    if not value["evidence"].strip():
        raise EvidenceValidationError(f"{field}.evidence: required when applicable")


def validate_evidence(
    payload: Any,
    *,
    expected_repository: str | None = None,
    expected_sha: str | None = None,
    expected_environment: str | None = None,
    expected_correlation_id: str | None = None,
    not_before: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate the contract, optionally binding it to a complete trusted context.

    Context must come from the execution provider/caller, never from the evidence
    being approved. Contract-only validation does not attest a workflow execution
    or independently establish that the claimed business effect happened.
    """
    payload = _exact_object(payload, ROOT_FIELDS, "root")
    if payload["schema_version"] != "1.0.0":
        raise EvidenceValidationError("schema_version: expected 1.0.0")

    project = _require_text(payload, "project")
    repository = _require_text(payload, "repository")
    sha = _require_text(payload, "sha")
    environment = _require_text(payload, "environment")
    correlation_id = _require_text(payload, "correlation_id")
    objective = _require_text(payload, "objective")

    if not REPOSITORY_RE.fullmatch(repository) or repository != payload["repository"]:
        raise EvidenceValidationError("repository: expected owner/name")
    if not SHA_RE.fullmatch(sha) or sha != payload["sha"]:
        raise EvidenceValidationError("sha: expected full 40-character commit SHA")
    if len(correlation_id) < 8:
        raise EvidenceValidationError("correlation_id: too short")

    status = payload["status"]
    if not isinstance(status, str) or status not in STATUS_ALLOWED:
        raise EvidenceValidationError("status: invalid value")
    if status != "passed":
        raise EvidenceValidationError(f"status: evidence is not approved ({status})")

    started_at = _parse_time(payload["started_at"], "started_at")
    completed_at = _parse_time(payload["completed_at"], "completed_at")
    clock = datetime.now(timezone.utc) if now is None else now
    if not isinstance(clock, datetime) or clock.tzinfo is None or clock.utcoffset() is None:
        raise EvidenceValidationError("now: expected timezone-aware datetime")
    if completed_at < started_at:
        raise EvidenceValidationError("completed_at: precedes started_at")
    if completed_at > clock:
        raise EvidenceValidationError("completed_at: future evidence is not allowed")

    _require_check(payload, "positive_control", optional=False)
    _require_check(payload, "negative_control", optional=True)
    _require_check(payload, "idempotency", optional=True)
    _require_check(payload, "test_of_test", optional=True)

    independent = _exact_object(
        payload["independent_read"], {"passed", "source", "evidence"}, "independent_read"
    )
    if independent["passed"] is not True:
        raise EvidenceValidationError("independent_read.passed: must be true")
    for field in ("source", "evidence"):
        if not isinstance(independent[field], str) or not independent[field].strip():
            raise EvidenceValidationError(f"independent_read.{field}: required")

    context = {
        "repository": expected_repository,
        "sha": expected_sha,
        "environment": expected_environment,
        "correlation_id": expected_correlation_id,
        "not_before": not_before,
    }
    context_bound = any(value is not None for value in context.values())
    if context_bound:
        for field, value in context.items():
            if not isinstance(value, str) or not value.strip() or value != value.strip():
                raise EvidenceValidationError(f"context.{field}: complete explicit context required")
        if not REPOSITORY_RE.fullmatch(expected_repository):
            raise EvidenceValidationError("context.repository: expected owner/name")
        if not SHA_RE.fullmatch(expected_sha):
            raise EvidenceValidationError("context.sha: expected full SHA")
        if len(expected_correlation_id) < 8:
            raise EvidenceValidationError("context.correlation_id: too short")
        for field in ("repository", "sha", "environment", "correlation_id"):
            observed = payload[field]
            expected = context[field]
            if field in {"sha", "repository"}:
                observed, expected = observed.lower(), expected.lower()
            if observed != expected:
                raise EvidenceValidationError(f"context.{field}: evidence does not match execution")
        earliest = _parse_time(not_before, "context.not_before")
        if earliest > clock:
            raise EvidenceValidationError("context.not_before: future execution is not allowed")
        if started_at < earliest:
            raise EvidenceValidationError("started_at: evidence predates this execution attempt")

    return {
        "result": "E2E_EVIDENCE_VALID",
        "schema_version": "1.0.0",
        "validation_scope": "execution-bound" if context_bound else "contract-only",
        "project": project,
        "repository": repository,
        "sha": sha.lower(),
        "environment": environment,
        "correlation_id": correlation_id,
        "objective": objective,
    }
