"""Regression coverage for required-check configuration, not merge authorization."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from scripts.verify_merge_governance import (
    GovernanceError, evaluate_governance, fetch_governance,
)


def branch_rule(*contexts):
    return {
        "type": "required_status_checks",
        "ruleset_id": 7,
        "ruleset_source_type": "Repository",
        "ruleset_source": "fixture/project",
        "parameters": {
            "required_status_checks": [{"context": value} for value in contexts],
            "strict_required_status_checks_policy": True,
        },
    }


class GovernanceVerifierTests(unittest.TestCase):
    def setUp(self):
        self.branch = {"name": "main", "protected": True, "protection": {}}

    def test_rejects_unprotected_or_non_boolean_protection(self):
        for value in (False, "true", 1, None):
            with self.subTest(value=value), self.assertRaisesRegex(GovernanceError, "not protected"):
                evaluate_governance({"protected": value}, [], ["contract-self-test"])

    def test_accepts_classic_protection_with_required_check(self):
        self.branch["protection"] = {
            "required_status_checks": {
                "enforcement_level": "everyone",
                "contexts": ["contract-self-test"],
                "checks": [{"context": "workflow-cli-e2e"}],
            }
        }
        result = evaluate_governance(
            self.branch, [], ["contract-self-test", "workflow-cli-e2e"]
        )
        self.assertEqual(result["status"], "GOVERNANCE_VALID")
        self.assertEqual(result["validation_scope"], "required_status_checks_configuration")
        self.assertIs(result["is_merge_authorization"], False)

    def test_ignores_unenforced_classic_checks(self):
        for level in ("off", "non_admins", "unexpected", None):
            with self.subTest(level=level):
                protection = {
                    "required_status_checks": {
                        "contexts": ["stale-classic-check"],
                        "checks": [],
                    }
                }
                if level is not None:
                    protection["required_status_checks"]["enforcement_level"] = level
                branch = {**self.branch, "protection": protection}
                with self.assertRaisesRegex(GovernanceError, "missing required status checks"):
                    evaluate_governance(branch, [], ["stale-classic-check"])

    def test_active_branch_rule_does_not_revive_disabled_classic_check(self):
        branch = {
            **self.branch,
            "protection": {
                "required_status_checks": {
                    "enforcement_level": "off",
                    "contexts": ["stale-classic-check"],
                    "checks": [],
                }
            },
        }
        rules = [branch_rule("real-enforced-check")]
        self.assertEqual(
            evaluate_governance(branch, rules, ["real-enforced-check"])["status"],
            "GOVERNANCE_VALID",
        )
        with self.assertRaisesRegex(GovernanceError, "stale-classic-check"):
            evaluate_governance(branch, rules, ["stale-classic-check"])

    def test_accepts_branch_scoped_active_rules_without_mutation_and_replays(self):
        rules = [branch_rule("test", "Evidence Gate / validate-evidence")]
        original = copy.deepcopy((self.branch, rules))
        expected = ["test", "Evidence Gate / validate-evidence"]
        first = evaluate_governance(self.branch, rules, expected)
        self.assertEqual(first, evaluate_governance(self.branch, rules, expected))
        self.assertEqual((self.branch, rules), original)
        self.assertEqual(first["status"], "GOVERNANCE_VALID")

    def test_rejects_unscoped_or_evaluation_ruleset_envelopes(self):
        for enforcement, include in (
            ("evaluate", ["refs/heads/main"]),
            ("disabled", ["refs/heads/main"]),
            ("active", ["refs/heads/release"]),
            ("active", ["refs/heads/main"]),
        ):
            with self.subTest(enforcement=enforcement, include=include):
                ruleset = {
                    "target": "branch", "enforcement": enforcement,
                    "conditions": {"ref_name": {"include": include, "exclude": []}},
                    "rules": [branch_rule("contract-self-test")],
                }
                with self.assertRaises(GovernanceError):
                    evaluate_governance(self.branch, [ruleset], ["contract-self-test"])

    def test_rejects_missing_required_check(self):
        with self.assertRaisesRegex(GovernanceError, "Evidence Gate"):
            evaluate_governance(
                self.branch, [branch_rule("test")],
                ["test", "Evidence Gate / validate-evidence"],
            )

    def test_requires_nonempty_explicit_expected_checks(self):
        for expected in ([], None, [" "], ["test", 1], [" test"]):
            with self.subTest(expected=expected), self.assertRaises(GovernanceError):
                evaluate_governance(self.branch, [branch_rule("test")], expected)

    def test_malformed_api_snapshots_fail_closed(self):
        for rules in (
            {}, [None], [{}],
            [{"type": "required_status_checks"}],
            [{"type": "required_status_checks", "parameters": {"required_status_checks": ["test"]}}],
            [{"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": 1}]}}],
        ):
            with self.subTest(rules=rules), self.assertRaises(GovernanceError):
                evaluate_governance(self.branch, rules, ["test"])
        for protection in (
            [], {"required_status_checks": []},
            {"required_status_checks": {"contexts": "test"}},
            {"required_status_checks": {"checks": [None]}},
        ):
            with self.subTest(protection=protection), self.assertRaises(GovernanceError):
                evaluate_governance(
                    {**self.branch, "protection": protection}, [], ["test"]
                )

    def test_fetches_branch_scoped_rules_and_all_needed_pages(self):
        branch = {**self.branch, "name": "release/one"}
        first_page = [{"type": "deletion"} for _ in range(100)]
        second_page = [branch_rule("test")]
        with patch(
            "scripts.verify_merge_governance._github_json",
            side_effect=[branch, first_page, second_page],
        ) as api:
            observed, rules = fetch_governance("fixture/project", "release/one", None)
        self.assertEqual(observed, branch)
        self.assertEqual(rules, first_page + second_page)
        self.assertEqual(
            [call.args[0] for call in api.call_args_list],
            [
                "https://api.github.com/repos/fixture/project/branches/release%2Fone",
                "https://api.github.com/repos/fixture/project/rules/branches/release%2Fone?per_page=100&page=1",
                "https://api.github.com/repos/fixture/project/rules/branches/release%2Fone?per_page=100&page=2",
            ],
        )
        self.assertEqual(evaluate_governance(observed, rules, ["test"])["status"], "GOVERNANCE_VALID")

    def test_truncated_rules_pagination_cannot_approve(self):
        full_page = [{"type": "deletion"} for _ in range(100)]
        with patch(
            "scripts.verify_merge_governance._github_json",
            side_effect=[self.branch] + [full_page] * 10,
        ), self.assertRaisesRegex(GovernanceError, "pagination limit"):
            fetch_governance("fixture/project", "main", None)

    def test_fetch_rejects_invalid_target_or_provider_identity(self):
        for repo, branch in (
            ("fixture/project?query=1", "main"),
            ("../project", "main"),
            ("fixture/project", " "),
        ):
            with self.subTest(repo=repo, branch=branch), patch(
                "scripts.verify_merge_governance._github_json"
            ) as api, self.assertRaises(GovernanceError):
                fetch_governance(repo, branch, None)
            api.assert_not_called()
        with patch(
            "scripts.verify_merge_governance._github_json",
            return_value={**self.branch, "name": "other"},
        ), self.assertRaisesRegex(GovernanceError, "identity mismatch"):
            fetch_governance("fixture/project", "main", None)
        with patch(
            "scripts.verify_merge_governance._github_json",
            side_effect=[self.branch, {"message": "wrong shape"}],
        ), self.assertRaisesRegex(GovernanceError, "invalid branch rules"):
            fetch_governance("fixture/project", "main", None)


if __name__ == "__main__":
    unittest.main()
