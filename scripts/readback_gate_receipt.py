#!/usr/bin/env python3
"""Independent readback of the two artifacts downloaded into a fresh CI job."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    evidence_bytes = args.evidence.read_bytes()
    document = json.loads(evidence_bytes)
    receipt = json.loads(args.receipt.read_bytes())
    expected = {
        "repository": os.environ["GITHUB_REPOSITORY"],
        "sha": os.environ["E2E_EXPECTED_SHA"].lower(),
        "correlation_id": (
            f"e2e-platform-selftest-{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}"
        ),
        "environment": "ci",
    }
    if receipt.get("result") != "E2E_EVIDENCE_VALID":
        raise RuntimeError("gate did not approve the artifact")
    if receipt.get("validation_scope") != "execution-bound":
        raise RuntimeError("receipt is only structural validation")
    for key, value in expected.items():
        if receipt.get(key) != value or document.get(key) != value:
            raise RuntimeError(f"independent identity mismatch: {key}")
    if receipt.get("evidence_sha256") != hashlib.sha256(evidence_bytes).hexdigest():
        raise RuntimeError("downloaded evidence differs from the approved bytes")
    if receipt.get("platform_sha") != os.environ["E2E_WORKFLOW_SHA"].lower():
        raise RuntimeError("platform workflow version mismatch")
    for field, env in (("run_id", "GITHUB_RUN_ID"), ("run_attempt", "GITHUB_RUN_ATTEMPT")):
        if receipt.get(field) != int(os.environ[env]):
            raise RuntimeError(f"independent execution mismatch: {field}")
    print(json.dumps({
        "result": "GATE_ARTIFACT_READBACK_VALID", **expected,
        "platform_sha": receipt["platform_sha"], "run_id": receipt["run_id"],
        "run_attempt": receipt["run_attempt"], "evidence_sha256": receipt["evidence_sha256"],
        "attempt_started_at": receipt["attempt_started_at"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
