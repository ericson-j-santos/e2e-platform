from __future__ import annotations

import json
from pathlib import Path
import unittest

from e2e_platform import EvidenceValidationError, validate_evidence

ROOT = Path(__file__).resolve().parents[1]


class EvidenceValidationTests(unittest.TestCase):
    def load(self, name: str) -> dict:
        return json.loads(
            (ROOT / "tests" / "fixtures" / name).read_text(encoding="utf-8")
        )

    def test_valid_evidence_passes(self) -> None:
        result = validate_evidence(self.load("valid-evidence.json"))
        self.assertEqual(result["result"], "E2E_EVIDENCE_VALID")
        self.assertEqual(result["correlation_id"], "self-test-valid-001")

    def test_failed_negative_control_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            EvidenceValidationError,
            r"negative_control\.passed",
        ):
            validate_evidence(self.load("invalid-evidence.json"))

    def test_non_full_sha_is_rejected(self) -> None:
        payload = self.load("valid-evidence.json")
        payload["sha"] = "abc123"
        with self.assertRaisesRegex(EvidenceValidationError, r"sha:"):
            validate_evidence(payload)

    def test_non_passed_status_is_rejected(self) -> None:
        payload = self.load("valid-evidence.json")
        payload["status"] = "blocked"
        with self.assertRaisesRegex(EvidenceValidationError, r"not approved"):
            validate_evidence(payload)

    def test_independent_read_is_mandatory(self) -> None:
        payload = self.load("valid-evidence.json")
        payload["independent_read"]["passed"] = False
        with self.assertRaisesRegex(
            EvidenceValidationError,
            r"independent_read\.passed",
        ):
            validate_evidence(payload)


if __name__ == "__main__":
    unittest.main()
