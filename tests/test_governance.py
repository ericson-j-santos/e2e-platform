import unittest

from scripts.verify_merge_governance import GovernanceError, evaluate_governance


class GovernanceVerifierTests(unittest.TestCase):
    def test_rejects_unprotected_branch(self):
        branch = {"protected": False, "protection": {}}
        with self.assertRaisesRegex(GovernanceError, "not protected"):
            evaluate_governance(branch, [], ["contract-self-test"])

    def test_accepts_classic_protection_with_required_check(self):
        branch = {
            "protected": True,
            "protection": {
                "required_status_checks": {
                    "contexts": ["contract-self-test"],
                    "checks": [],
                }
            },
        }
        result = evaluate_governance(branch, [], ["contract-self-test"])
        self.assertEqual(result["status"], "GOVERNANCE_VALID")

    def test_accepts_active_ruleset_with_required_checks(self):
        branch = {"protected": True, "protection": {}}
        rulesets = [
            {
                "target": "branch",
                "enforcement": "active",
                "rules": [
                    {
                        "type": "required_status_checks",
                        "parameters": {
                            "required_status_checks": [
                                {"context": "test"},
                                {"context": "E2E Platform Evidence Gate / validate-evidence"},
                            ]
                        },
                    }
                ],
            }
        ]
        result = evaluate_governance(
            branch,
            rulesets,
            ["test", "E2E Platform Evidence Gate / validate-evidence"],
        )
        self.assertEqual(result["status"], "GOVERNANCE_VALID")

    def test_rejects_missing_required_check(self):
        branch = {
            "protected": True,
            "protection": {
                "required_status_checks": {
                    "contexts": ["test"],
                    "checks": [],
                }
            },
        }
        with self.assertRaisesRegex(GovernanceError, "Evidence Gate"):
            evaluate_governance(
                branch,
                [],
                ["test", "E2E Platform Evidence Gate / validate-evidence"],
            )


if __name__ == "__main__":
    unittest.main()
