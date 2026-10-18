"""Exercise the real CLI boundary using real subprocesses and file readback."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/validate_evidence.py"


class EvidenceCLITests(unittest.TestCase):
    def invoke(self, path, *args, cwd=None):
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        return subprocess.run(
            [sys.executable, "-I", str(SCRIPT), str(path), *args],
            cwd=cwd, env=env, text=True, encoding="utf-8",
            capture_output=True, timeout=10, check=False,
        )

    def assert_invalid(self, result):
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stdout, "")
        message = json.loads(result.stderr)
        self.assertEqual(message["result"], "E2E_EVIDENCE_INVALID")
        self.assertNotIn("Traceback", result.stderr)
        return message

    def test_positive_from_outside_source_tree_and_replay_preserve_input(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.json"
            raw = (ROOT / "tests/fixtures/valid-evidence.json").read_bytes()
            path.write_bytes(raw)
            args = (
                "--expected-repository", "ericson-j-santos/e2e-platform",
                "--expected-sha", "a" * 40,
                "--expected-environment", "ci",
                "--expected-correlation-id", "self-test-valid-001",
                "--not-before", "2026-09-23T14:59:59Z",
            )
            first = self.invoke(path, *args, cwd=folder)
            second = self.invoke(path, *args, cwd=folder)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(first.stdout, second.stdout)
            self.assertEqual(json.loads(first.stdout)["validation_scope"], "execution-bound")
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_negative_fixture_must_report_validation_error_not_any_failure(self):
        result = self.invoke(ROOT / "tests/fixtures/invalid-evidence.json")
        message = self.assert_invalid(result)
        self.assertIn("negative_control.passed", message["error"])

    def test_identity_mismatch_and_partial_context_are_explicit_errors(self):
        path = ROOT / "tests/fixtures/valid-evidence.json"
        self.assert_invalid(self.invoke(path, "--expected-sha", "b" * 40))
        self.assert_invalid(self.invoke(
            path,
            "--expected-repository", "ericson-j-santos/e2e-platform",
            "--expected-sha", "b" * 40, "--expected-environment", "ci",
            "--expected-correlation-id", "self-test-valid-001",
            "--not-before", "2026-09-23T14:59:59Z",
        ))

    def test_invalid_json_unicode_duplicate_keys_and_root_types(self):
        values = (
            b"{", b"\xff", b'{"status":"failed","status":"passed"}',
            b'{"value":NaN}', b"null", b"[]", b"false",
            b'{"unused":' + b"1" * 5000 + b"}", b'{"value":1e1000}',
        )
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "invalid.json"
            for raw in values:
                with self.subTest(raw=raw):
                    path.write_bytes(raw)
                    self.assert_invalid(self.invoke(path))

    def test_missing_file_and_excessive_size_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "missing.json"
            self.assert_invalid(self.invoke(path))
            path.write_bytes(b" " * 1_048_577)
            self.assert_invalid(self.invoke(path))

    def test_malformed_timestamp_and_status_never_escape_as_tracebacks(self):
        original = json.loads((ROOT / "tests/fixtures/valid-evidence.json").read_text())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "invalid.json"
            for key, value in (
                ("status", ["passed"]), ("project", "\ud800"),
                ("started_at", "2026-09-23T15:00:00"),
                ("completed_at", "2999-01-01T00:00:00Z"),
            ):
                with self.subTest(key=key):
                    path.write_text(json.dumps({**original, key: value}), encoding="utf-8")
                    self.assert_invalid(self.invoke(path))


if __name__ == "__main__":
    unittest.main()
