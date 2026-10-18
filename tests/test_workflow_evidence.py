from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from e2e_platform import EvidenceValidationError
from scripts.validate_workflow_evidence import (
    confined_evidence_path, fetch_attempt, trusted_identity, validate_attempt,
)


class WorkflowEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "GITHUB_ACTIONS": "true", "GITHUB_SERVER_URL": "https://github.com",
            "GITHUB_API_URL": "https://api.github.com",
            "GITHUB_REPOSITORY": "ericson-j-santos/e2e-platform",
            "GITHUB_RUN_ID": "12345", "GITHUB_RUN_ATTEMPT": "2",
            "E2E_EXPECTED_SHA": "a" * 40, "E2E_PLATFORM_REF": "b" * 40,
            "E2E_WORKFLOW_SHA": "b" * 40,
            "E2E_WORKFLOW_REPOSITORY": "ericson-j-santos/e2e-platform",
            "E2E_CORRELATION_PREFIX": "self-test",
            "E2E_EXPECTED_ENVIRONMENT": "ci",
        }
        self.identity = trusted_identity(self.env)
        self.attempt = {
            "id": 12345, "run_attempt": 2, "head_sha": "a" * 40,
            "repository": {"full_name": "ericson-j-santos/e2e-platform"},
            "run_started_at": "2026-09-23T15:00:00Z",
        }

    def test_context_is_bound_to_provider_identity(self):
        self.assertEqual(self.identity["correlation_id"], "self-test-12345-2")
        self.assertEqual(validate_attempt(self.identity, self.attempt),
                         "2026-09-23T15:00:00Z")

    def test_invalid_or_incomplete_context_is_rejected(self):
        for key, wrong in (
            ("GITHUB_ACTIONS", "false"),
            ("GITHUB_API_URL", "https://untrusted.invalid"),
            ("GITHUB_SERVER_URL", "http://github.com"),
            ("GITHUB_RUN_ID", "0"), ("GITHUB_RUN_ATTEMPT", "-1"),
            ("E2E_EXPECTED_SHA", "main"), ("E2E_PLATFORM_REF", "c" * 40),
            ("E2E_WORKFLOW_REPOSITORY", "another/repo"),
            ("E2E_EXPECTED_ENVIRONMENT", ""), ("E2E_CORRELATION_PREFIX", "../"),
        ):
            with self.subTest(key=key):
                with self.assertRaises(EvidenceValidationError):
                    trusted_identity({**self.env, key: wrong})
        with self.assertRaises(EvidenceValidationError):
            trusted_identity({})

    def test_different_provider_attempt_repository_or_sha_is_rejected(self):
        for key, wrong in (
            ("id", 12346), ("run_attempt", 1), ("id", True),
            ("head_sha", "c" * 40), ("head_sha", None),
            ("repository", {"full_name": "another/repo"}),
            ("repository", {"full_name": 7}), ("repository", None),
            ("run_started_at", None),
        ):
            with self.subTest(key=key, wrong=wrong):
                with self.assertRaises(EvidenceValidationError):
                    validate_attempt(self.identity, {**self.attempt, key: wrong})

    def test_confines_filename_and_blocks_symlink_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "artifact"
            root.mkdir()
            evidence = root / "evidence.json"
            evidence.write_text("{}", encoding="utf-8")
            self.assertEqual(confined_evidence_path(root, "evidence.json"), evidence)
            outside = Path(directory) / "outside.json"
            outside.write_text("{}", encoding="utf-8")
            (root / "escape.json").symlink_to(outside)
            for name in (
                "../outside.json", "/tmp/outside.json", "a/../../outside.json",
                "./evidence.json", "a//evidence.json", r"..\outside.json",
                "escape.json", "missing.json", ".",
            ):
                with self.subTest(name=name):
                    with self.assertRaises(EvidenceValidationError):
                        confined_evidence_path(root, name)

    def test_api_credential_absence_does_not_make_a_request(self):
        with patch("urllib.request.build_opener") as opener:
            with self.assertRaises(EvidenceValidationError):
                fetch_attempt(self.identity, None)
            opener.assert_not_called()

    def test_api_failure_is_structured_and_does_not_leak_credential(self):
        for error in (
            TimeoutError(),
            urllib.error.HTTPError("https://api.github.com", 403, "denied", {}, None),
        ):
            with self.subTest(error=type(error).__name__):
                with patch("urllib.request.build_opener") as opener:
                    opener.return_value.open.side_effect = error
                    with self.assertRaises(EvidenceValidationError) as raised:
                        fetch_attempt(self.identity, "synthetic-private-marker")
                    self.assertNotIn("synthetic-private-marker", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
