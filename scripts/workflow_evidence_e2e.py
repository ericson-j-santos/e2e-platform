#!/usr/bin/env python3
"""Exercise the actual workflow CLI against this attempt's real GitHub API."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/validate_workflow_evidence.py"


def main():
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    expected = {
        "repository": env["GITHUB_REPOSITORY"], "sha": env["E2E_EXPECTED_SHA"].lower(),
        "run_id": int(env["GITHUB_RUN_ID"]), "run_attempt": int(env["GITHUB_RUN_ATTEMPT"]),
        "correlation_id": (
            f"{env['E2E_CORRELATION_PREFIX']}-{env['GITHUB_RUN_ID']}-{env['GITHUB_RUN_ATTEMPT']}"
        ),
    }
    stamp = datetime.now(timezone.utc).isoformat()
    payload = json.loads((ROOT / "tests/fixtures/valid-evidence.json").read_text())
    payload.update({
        "project": "e2e-platform-workflow-self-test", **{
            key: value for key, value in expected.items() if key not in {"run_id", "run_attempt"}
        },
        "environment": env["E2E_EXPECTED_ENVIRONMENT"],
        "objective": "Validate a synthetic current-run artifact through the actual GitHub-bound gate.",
        "started_at": stamp, "completed_at": stamp,
    })
    controls = []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = root / "evidence.json"
        env["E2E_EVIDENCE_FILE"] = "evidence.json"

        def invoke(document, changes=None):
            path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
            before = path.read_bytes()
            result = subprocess.run(
                [sys.executable, "-I", str(SCRIPT), "--evidence-root", str(root)],
                env={**env, **(changes or {})}, cwd=directory,
                text=True, encoding="utf-8", capture_output=True, timeout=30, check=False,
            )
            if path.read_bytes() != before:
                raise RuntimeError("independent readback: input artifact was modified")
            return result, hashlib.sha256(before).hexdigest()

        first, digest = invoke(payload)
        if first.returncode != 0 or first.stderr:
            raise RuntimeError(f"positive workflow gate failed: {first.stderr}")
        receipt = json.loads(first.stdout)
        if receipt.get("result") != "E2E_EVIDENCE_VALID" or receipt.get("validation_scope") != "execution-bound":
            raise RuntimeError("positive workflow gate did not issue an execution-bound approval")
        for field, value in expected.items():
            if receipt.get(field) != value:
                raise RuntimeError(f"independent receipt identity mismatch: {field}")
        if receipt.get("evidence_sha256") != digest:
            raise RuntimeError("independent receipt digest mismatch")
        controls.append("positive_actual_workflow_cli_and_github_api")

        cases = []
        for field, value in (
            ("repository", "another/project"), ("sha", "c" * 40),
            ("environment", "other-environment"), ("correlation_id", "previous-attempt-001"),
        ):
            document = copy.deepcopy(payload)
            document[field] = value
            cases.append((field, document, {}, f"context.{field}"))
        stale = copy.deepcopy(payload)
        stale["started_at"] = "2020-01-01T00:00:00Z"
        stale["completed_at"] = "2020-01-01T00:00:01Z"
        cases.append(("stale_attempt", stale, {}, "predates"))
        broken = copy.deepcopy(payload)
        broken["negative_control"]["passed"] = False
        cases.append(("test_of_test", broken, {}, "negative_control.passed"))
        cases.extend([
            ("path_escape", payload, {"E2E_EVIDENCE_FILE": "../outside.json"}, "file:"),
            ("platform_ref_mismatch", payload, {"E2E_PLATFORM_REF": "c" * 40}, "platform_ref"),
            ("missing_api_credential", payload, {"GITHUB_TOKEN": ""}, "credential"),
        ])
        for name, document, changes, expected_error in cases:
            result, _ = invoke(document, changes)
            if result.returncode != 2 or result.stdout:
                raise RuntimeError(f"negative {name}: expected structured rejection, got {result.returncode}")
            error = json.loads(result.stderr)
            if error.get("result") != "E2E_EVIDENCE_INVALID" or expected_error not in error.get("error", ""):
                raise RuntimeError(f"negative {name}: wrong rejection reason")
            controls.append(name)

        replay, replay_digest = invoke(payload)
        if replay.returncode != 0 or replay.stdout != first.stdout or replay_digest != digest:
            raise RuntimeError("idempotent replay differs from original approval")
        controls.append("replay_identical_with_independent_file_readback")

    payload["positive_control"]["evidence"] = "Actual CLI accepted this run identity using the real GitHub attempt API."
    payload["negative_control"]["evidence"] = "Nine independent invalid-input controls returned exit 2 and the expected structured error."
    payload["independent_read"] = {
        "passed": True, "source": "separate CLI process and independent SHA-256/file reader",
        "evidence": f"Receipt repository/SHA/run/attempt/correlation and input digest {digest} matched; input bytes unchanged.",
    }
    payload["idempotency"]["evidence"] = "Restored input replay returned byte-identical approval without modifying the input."
    payload["test_of_test"]["evidence"] = "Changing negative_control.passed to false was rejected by the real workflow CLI."
    payload["completed_at"] = datetime.now(timezone.utc).isoformat()
    output = ROOT / "artifacts" / "workflow-gate"
    output.mkdir(parents=True, exist_ok=True)
    (output / "evidence.json").write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    summary = {"status": "PASS", **expected, "controls": controls, "platform_sha": env["E2E_WORKFLOW_SHA"]}
    (output / "self-test.json").write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
