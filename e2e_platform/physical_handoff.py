from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


class PhysicalHandoffValidationError(ValueError):
    """Raised when physical multi-host evidence is incomplete or untrusted."""


SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
TASK_ID = re.compile(r"^[A-Za-z0-9_.:-]{8,128}$")
HOST_ID = re.compile(r"^host-[a-z0-9-]{8,80}$")
RUNNER_ID = re.compile(r"^[A-Za-z0-9_.:-]{8,128}$")
AUTHORITY = "e2e-platform-physical-handoff-authority-v1"

ROOT_FIELDS = {
    "schema_version", "authority", "issued_at", "expires_at", "repository",
    "pr_number", "head_sha", "environment", "workflow_run_id", "job_id",
    "run_attempt", "task_id", "status", "artifact_synthetic", "cost",
    "hosts", "checkpoint", "interruption", "resumption", "external_readback",
    "replay_negative",
}
HOST_FIELDS = {
    "role", "physical_host_id", "runner_instance_id", "session_launcher_authenticated",
    "command_gateway_authenticated", "runner_online", "runner_busy", "lease_id",
    "lease_exclusive", "worktree_id", "worktree_exclusive", "receipt_sha256",
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _fail(condition: bool, code: str) -> None:
    if not condition:
        raise PhysicalHandoffValidationError(code)


def _time(value: Any, code: str) -> datetime:
    _fail(isinstance(value, str), code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise PhysicalHandoffValidationError(code) from None
    _fail(parsed.tzinfo is not None and parsed.utcoffset() is not None, code)
    return parsed.astimezone(timezone.utc)


def _digest(value: Any, code: str) -> None:
    _fail(isinstance(value, str) and SHA64.fullmatch(value) is not None, code)


def validate_physical_handoff(
    envelope: Any, *, public_key: bytes, expected_repository: str,
    expected_pr_number: int, expected_head_sha: str, expected_environment: str,
    expected_run_id: int, expected_job_id: int, expected_run_attempt: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate a signed, current, execution-bound physical handoff receipt.

    The function only validates evidence. It never dispatches work and its result
    deliberately contains no merge/deploy/dispatch authorization.
    """
    _fail(isinstance(envelope, dict) and set(envelope) == {"payload", "signature"},
          "envelope_invalid")
    payload = envelope["payload"]
    signature = envelope["signature"]
    _fail(isinstance(payload, dict) and set(payload) == ROOT_FIELDS,
          "payload_fields_invalid")
    _fail(isinstance(public_key, bytes) and len(public_key) == 32,
          "public_key_invalid")
    _fail(isinstance(signature, str) and re.fullmatch(r"[0-9a-f]{128}", signature) is not None,
          "signature_format_invalid")
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            bytes.fromhex(signature), canonical_bytes(payload))
    except (InvalidSignature, ValueError, TypeError):
        raise PhysicalHandoffValidationError("signature_invalid") from None

    _fail(payload["schema_version"] == "1.0.0" and payload["authority"] == AUTHORITY,
          "authority_invalid")
    issued = _time(payload["issued_at"], "issued_at_invalid")
    expires = _time(payload["expires_at"], "expires_at_invalid")
    clock = now or datetime.now(timezone.utc)
    _fail(clock.tzinfo is not None and issued <= clock <= expires and expires > issued,
          "receipt_stale_or_future")
    _fail((expires - issued).total_seconds() <= 900, "receipt_ttl_too_large")

    _fail(isinstance(expected_repository, str) and REPOSITORY.fullmatch(expected_repository),
          "expected_repository_invalid")
    _fail(isinstance(expected_head_sha, str) and SHA40.fullmatch(expected_head_sha),
          "expected_sha_invalid")
    expected = (
        expected_repository, expected_pr_number, expected_head_sha, expected_environment,
        expected_run_id, expected_job_id, expected_run_attempt,
    )
    observed = (
        payload["repository"], payload["pr_number"], payload["head_sha"],
        payload["environment"], payload["workflow_run_id"], payload["job_id"],
        payload["run_attempt"],
    )
    _fail(observed == expected, "execution_context_mismatch")
    _fail(all(type(x) is int and x > 0 for x in observed[1:2] + observed[4:]),
          "execution_ids_invalid")
    _fail(payload["status"] == "passed" and payload["artifact_synthetic"] is False,
          "physical_result_not_passed")
    _fail(isinstance(payload["task_id"], str) and TASK_ID.fullmatch(payload["task_id"]),
          "task_id_invalid")

    cost = payload["cost"]
    _fail(isinstance(cost, dict) and set(cost) == {"status", "evidence_sha256"}
          and cost["status"] == "COST_ZERO_CONFIRMED", "cost_not_confirmed")
    _digest(cost.get("evidence_sha256"), "cost_evidence_invalid")

    hosts = payload["hosts"]
    _fail(isinstance(hosts, list) and len(hosts) == 2, "two_hosts_required")
    roles: set[str] = set()
    physical: set[str] = set()
    leases: set[str] = set()
    worktrees: set[str] = set()
    for host in hosts:
        _fail(isinstance(host, dict) and set(host) == HOST_FIELDS, "host_fields_invalid")
        _fail(host["role"] in {"builder", "validator"}, "host_role_invalid")
        _fail(isinstance(host["physical_host_id"], str) and HOST_ID.fullmatch(host["physical_host_id"]),
              "physical_host_id_invalid")
        _fail(isinstance(host["runner_instance_id"], str) and RUNNER_ID.fullmatch(host["runner_instance_id"]),
              "runner_instance_id_invalid")
        _fail(all(host[k] is True for k in (
            "session_launcher_authenticated", "command_gateway_authenticated", "runner_online",
            "lease_exclusive", "worktree_exclusive")), "host_gate_not_proven")
        _fail(host["runner_busy"] is False, "runner_busy")
        _fail(all(isinstance(host[k], str) and len(host[k]) >= 12
                  for k in ("lease_id", "worktree_id")), "host_ownership_invalid")
        _digest(host["receipt_sha256"], "host_receipt_invalid")
        roles.add(host["role"]); physical.add(host["physical_host_id"])
        leases.add(host["lease_id"]); worktrees.add(host["worktree_id"])
    _fail(roles == {"builder", "validator"} and len(physical) == 2,
          "distinct_hosts_and_roles_required")
    _fail(len(leases) == 2 and len(worktrees) == 2, "exclusive_ownership_not_distinct")

    checkpoint = payload["checkpoint"]
    _fail(isinstance(checkpoint, dict) and set(checkpoint) == {
        "task_id", "checkpoint_id", "cas_sha256", "readback_sha256", "immutable",
    }, "checkpoint_fields_invalid")
    _fail(checkpoint["task_id"] == payload["task_id"] and checkpoint["immutable"] is True,
          "checkpoint_identity_invalid")
    _fail(isinstance(checkpoint["checkpoint_id"], str) and len(checkpoint["checkpoint_id"]) >= 8,
          "checkpoint_id_invalid")
    _digest(checkpoint["cas_sha256"], "checkpoint_digest_invalid")
    _fail(checkpoint["readback_sha256"] == checkpoint["cas_sha256"],
          "checkpoint_readback_mismatch")

    interruption = payload["interruption"]
    _fail(isinstance(interruption, dict) and set(interruption) == {
        "host_role", "controlled", "lease_released", "observed_sha256",
    } and interruption["host_role"] == "builder" and
          interruption["controlled"] is True and interruption["lease_released"] is True,
          "interruption_not_proven")
    _digest(interruption["observed_sha256"], "interruption_evidence_invalid")

    resumption = payload["resumption"]
    _fail(isinstance(resumption, dict) and set(resumption) == {
        "host_role", "task_id", "checkpoint_id", "fencing_exclusive", "completed",
    } and resumption["host_role"] == "validator" and
          resumption["task_id"] == payload["task_id"] and
          resumption["checkpoint_id"] == checkpoint["checkpoint_id"] and
          resumption["fencing_exclusive"] is True and resumption["completed"] is True,
          "resumption_not_proven")

    for field in ("external_readback", "replay_negative"):
        item = payload[field]
        _fail(isinstance(item, dict) and set(item) == {"passed", "evidence_sha256"}
              and item["passed"] is True, f"{field}_not_proven")
        _digest(item["evidence_sha256"], f"{field}_evidence_invalid")

    return {
        "result": "PHYSICAL_HANDOFF_EVIDENCE_VALID",
        "schema_version": "1.0.0",
        "repository": expected_repository,
        "pr_number": expected_pr_number,
        "head_sha": expected_head_sha,
        "workflow_run_id": expected_run_id,
        "job_id": expected_job_id,
        "run_attempt": expected_run_attempt,
        "task_id": payload["task_id"],
        "physical_hosts": sorted(physical),
        "dispatch_allowed": False,
        "merge_authorized": False,
        "deployment_authorized": False,
    }
