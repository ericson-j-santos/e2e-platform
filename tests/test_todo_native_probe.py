"""Safety controls run without a database or third-party dependencies."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "scripts/todo_native_postgres_probe.py"
spec = importlib.util.spec_from_file_location("todo_native_probe", path)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class ProbeSafetyTests(unittest.TestCase):
    def env(self, dsn="postgresql://todo_ci:fixture@127.0.0.1:5432/todo_native_ci"):
        return {"TODO_NATIVE_E2E_DISPOSABLE": "1", "TODO_NATIVE_E2E_DSN": dsn}

    def test_only_explicit_disposable_loopback_allowed(self):
        self.assertEqual(probe.guarded_dsn(self.env()), self.env()["TODO_NATIVE_E2E_DSN"])

    def test_opt_in_required(self):
        env = self.env()
        env.pop("TODO_NATIVE_E2E_DISPOSABLE")
        with self.assertRaises(ValueError):
            probe.guarded_dsn(env)

    def test_remote_targets_and_real_databases_rejected(self):
        for dsn in ("postgresql://todo_ci:fixture@production.invalid:5432/todo_native_ci",
                    "postgresql://todo_ci:fixture@127.0.0.1:5432/production",
                    "postgresql://admin:fixture@127.0.0.1:5432/todo_native_ci",
                    "postgresql://todo_ci:fixture@127.0.0.1:5432/todo_native_ci?host=remote",
                    "postgresql://todo_ci:fixture@127.0.0.1:9999/todo_native_ci"):
            with self.subTest(case=dsn):
                with self.assertRaises(ValueError):
                    probe.guarded_dsn(self.env(dsn))

    def test_error_does_not_echo_connection_string(self):
        with self.assertRaises(ValueError) as caught:
            probe.guarded_dsn(self.env("postgresql://secret@malformed"))
        self.assertNotIn("secret", str(caught.exception))

    def test_negative_validator_detects_changed_persisted_state(self):
        expected = [["evt-fixture", "a"*64, "PENDENTE", "PENDING", 0]]
        probe.check_rows({"rows": expected}, expected)
        with self.assertRaises(ValueError):
            probe.check_rows({"rows": []}, expected)

    def test_guard_not_dependent_on_assertions(self):
        with self.assertRaises(ValueError):
            probe.require(False, "negative control")
        probe.require(True, "positive control")


if __name__ == "__main__":
    unittest.main(verbosity=2)
