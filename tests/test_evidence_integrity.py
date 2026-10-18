"""Regression tests for evidence that must never produce a false approval."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

from e2e_platform import EvidenceValidationError, validate_evidence

ROOT = Path(__file__).resolve().parents[1]


class EvidenceIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(
            (ROOT / "tests/fixtures/valid-evidence.json").read_text(encoding="utf-8")
        )
        self.context = {
            "expected_repository": self.payload["repository"],
            "expected_sha": self.payload["sha"],
            "expected_environment": self.payload["environment"],
            "expected_correlation_id": self.payload["correlation_id"],
            "not_before": "2026-09-23T14:59:59Z",
            "now": datetime(2026, 9, 23, 15, 1, tzinfo=timezone.utc),
        }

    def test_timezone_is_required(self):
        for field in ("started_at", "completed_at"):
            with self.subTest(field=field):
                payload = copy.deepcopy(self.payload)
                payload[field] = payload[field].removesuffix("Z")
                with self.assertRaises(EvidenceValidationError):
                    validate_evidence(payload)

    def test_invalid_timezone_offset_is_rejected(self):
        for offset in ("+00:60", "-00:99", "+24:00", "-00:00"):
            with self.subTest(offset=offset):
                payload = copy.deepcopy(self.payload)
                for field in ("started_at", "completed_at"):
                    payload[field] = payload[field].replace("Z", offset)
                with self.assertRaises(EvidenceValidationError):
                    validate_evidence(payload)

    def test_future_evidence_is_rejected(self):
        payload = copy.deepcopy(self.payload)
        payload["started_at"] = "2999-01-01T00:00:00Z"
        payload["completed_at"] = "2999-01-01T00:00:01Z"
        with self.assertRaises(EvidenceValidationError):
            validate_evidence(payload)

    def test_unknown_root_and_nested_fields_are_rejected(self):
        for container in (None, "positive_control", "negative_control", "independent_read"):
            with self.subTest(container=container):
                payload = copy.deepcopy(self.payload)
                target = payload if container is None else payload[container]
                target["unrecognized_field"] = True
                with self.assertRaises(EvidenceValidationError):
                    validate_evidence(payload)

    def test_optional_check_requires_complete_explicit_contract(self):
        for field in ("negative_control", "idempotency", "test_of_test"):
            for value in ({"applicable": False}, {"passed": True, "evidence": "ok"}):
                with self.subTest(field=field, value=value):
                    payload = copy.deepcopy(self.payload)
                    payload[field] = value
                    with self.assertRaises(EvidenceValidationError):
                        validate_evidence(payload)

    def test_positive_control_cannot_be_disabled(self):
        payload = copy.deepcopy(self.payload)
        payload["positive_control"]["applicable"] = False
        with self.assertRaises(EvidenceValidationError):
            validate_evidence(payload)

    def test_unhashable_status_is_a_validation_error(self):
        payload = copy.deepcopy(self.payload)
        payload["status"] = ["passed"]
        with self.assertRaises(EvidenceValidationError):
            validate_evidence(payload)

    def test_exact_context_is_accepted_without_mutation_and_replays(self):
        original = copy.deepcopy(self.payload)
        first = validate_evidence(self.payload, **self.context)
        second = validate_evidence(self.payload, **self.context)
        self.assertEqual(first, second)
        self.assertEqual(self.payload, original)
        self.assertEqual(first["validation_scope"], "execution-bound")

    def test_structural_validation_is_identified(self):
        result = validate_evidence(self.payload)
        self.assertEqual(result["validation_scope"], "contract-only")

    def test_mismatched_execution_identity_is_rejected(self):
        for field, wrong in (
            ("expected_repository", "another/project"),
            ("expected_sha", "b" * 40),
            ("expected_environment", "production"),
            ("expected_correlation_id", "another-run-002"),
        ):
            with self.subTest(field=field):
                context = dict(self.context)
                context[field] = wrong
                with self.assertRaises(EvidenceValidationError):
                    validate_evidence(self.payload, **context)

    def test_previous_attempt_evidence_is_rejected(self):
        context = dict(self.context)
        context["not_before"] = "2026-09-23T15:00:02Z"
        with self.assertRaises(EvidenceValidationError):
            validate_evidence(self.payload, **context)

    def test_partial_or_empty_execution_context_is_rejected(self):
        for context in (
            {"expected_sha": self.payload["sha"]},
            {**self.context, "expected_environment": ""},
            {**self.context, "not_before": "2026-09-23T15:02:00Z"},
        ):
            with self.subTest(context=context):
                with self.assertRaises(EvidenceValidationError):
                    validate_evidence(self.payload, **context)


if __name__ == "__main__":
    unittest.main()
