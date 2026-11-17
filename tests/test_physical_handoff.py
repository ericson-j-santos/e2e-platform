from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from e2e_platform.physical_handoff import (
    AUTHORITY, PhysicalHandoffValidationError, canonical_bytes,
    validate_physical_handoff,
)

NOW = datetime(2026, 11, 17, 20, 0, tzinfo=timezone.utc)
SHA = "a" * 40
DIGEST = "b" * 64
TASK = "reqsys-task-0001"


def payload():
    return {
        "schema_version": "1.0.0", "authority": AUTHORITY,
        "issued_at": NOW.isoformat(), "expires_at": (NOW + timedelta(minutes=5)).isoformat(),
        "repository": "ericson-j-santos/reqsys-v2-enterprise-real", "pr_number": 3141,
        "head_sha": SHA, "environment": "dev", "workflow_run_id": 4001,
        "job_id": 5001, "run_attempt": 2, "task_id": TASK, "status": "passed",
        "artifact_synthetic": False,
        "cost": {"status": "COST_ZERO_CONFIRMED", "evidence_sha256": DIGEST},
        "hosts": [
            {"role": "builder", "physical_host_id": "host-desktop-pdqk954",
             "runner_instance_id": "runner-desktop-01", "session_launcher_authenticated": True,
             "command_gateway_authenticated": True, "runner_online": True, "runner_busy": False,
             "lease_id": "lease-builder-0001", "lease_exclusive": True,
             "worktree_id": "worktree-builder-0001", "worktree_exclusive": True,
             "receipt_sha256": DIGEST},
            {"role": "validator", "physical_host_id": "host-desktop-rp23ogs",
             "runner_instance_id": "runner-validator-01", "session_launcher_authenticated": True,
             "command_gateway_authenticated": True, "runner_online": True, "runner_busy": False,
             "lease_id": "lease-validator-0001", "lease_exclusive": True,
             "worktree_id": "worktree-validator-0001", "worktree_exclusive": True,
             "receipt_sha256": "c" * 64},
        ],
        "checkpoint": {"task_id": TASK, "checkpoint_id": "checkpoint-0001",
                       "cas_sha256": DIGEST, "readback_sha256": DIGEST, "immutable": True},
        "interruption": {"host_role": "builder", "controlled": True,
                         "lease_released": True, "observed_sha256": DIGEST},
        "resumption": {"host_role": "validator", "task_id": TASK,
                       "checkpoint_id": "checkpoint-0001", "fencing_exclusive": True,
                       "completed": True},
        "external_readback": {"passed": True, "evidence_sha256": DIGEST},
        "replay_negative": {"passed": True, "evidence_sha256": "d" * 64},
    }


def envelope(value=None):
    private = Ed25519PrivateKey.generate()
    value = value or payload()
    return {"payload": value, "signature": private.sign(canonical_bytes(value)).hex()}, private.public_key().public_bytes_raw()


def verify(value=None, **overrides):
    receipt, public = envelope(value)
    args = dict(public_key=public, expected_repository="ericson-j-santos/reqsys-v2-enterprise-real",
                expected_pr_number=3141, expected_head_sha=SHA, expected_environment="dev",
                expected_run_id=4001, expected_job_id=5001, expected_run_attempt=2, now=NOW)
    args.update(overrides)
    return validate_physical_handoff(receipt, **args)


MUTATIONS = [
    lambda p: p.update(head_sha="f" * 40),
    lambda p: p.update(run_attempt=1),
    lambda p: p.update(artifact_synthetic=True),
    lambda p: p["cost"].update(status="COST_UNKNOWN_BLOCKED"),
    lambda p: p["hosts"].__setitem__(1, deepcopy(p["hosts"][0])),
    lambda p: p["checkpoint"].update(readback_sha256="c" * 64),
    lambda p: p["interruption"].update(lease_released=False),
    lambda p: p["resumption"].update(fencing_exclusive=False),
    lambda p: p["replay_negative"].update(passed=False),
]


class PhysicalHandoffTests(unittest.TestCase):
    def test_valid_physical_handoff_is_execution_bound_but_not_authorization(self):
        result = verify()
        self.assertEqual(result["result"], "PHYSICAL_HANDOFF_EVIDENCE_VALID")
        self.assertEqual(result["physical_hosts"],
                         ["host-desktop-pdqk954", "host-desktop-rp23ogs"])
        self.assertFalse(result["dispatch_allowed"])
        self.assertFalse(result["merge_authorized"])
        self.assertFalse(result["deployment_authorized"])

    def test_required_physical_controls_fail_closed(self):
        for mutation in MUTATIONS:
            with self.subTest(mutation=mutation):
                value = payload(); mutation(value)
                with self.assertRaises(PhysicalHandoffValidationError):
                    verify(value)

    def test_signature_and_expiration_fail_closed(self):
        receipt, public = envelope()
        receipt["payload"]["task_id"] = "other-task"
        with self.assertRaisesRegex(PhysicalHandoffValidationError, "signature_invalid"):
            validate_physical_handoff(receipt, public_key=public,
                expected_repository="ericson-j-santos/reqsys-v2-enterprise-real",
                expected_pr_number=3141, expected_head_sha=SHA, expected_environment="dev",
                expected_run_id=4001, expected_job_id=5001, expected_run_attempt=2, now=NOW)
        with self.assertRaisesRegex(PhysicalHandoffValidationError,
                                    "receipt_stale_or_future"):
            verify(now=NOW + timedelta(minutes=6))

    def test_replay_is_deterministic(self):
        self.assertEqual(verify(), verify())


if __name__ == "__main__":
    unittest.main()
