#!/usr/bin/env python3
"""Verify required-check configuration using branch-scoped active GitHub rules.

This read-only check is not merge authorization. It does not evaluate reviews,
bypass actors, current HEAD check results, conflicts, or base freshness.
Uses only the Python standard library.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import quote
from typing import Any


class GovernanceError(RuntimeError):
    """Raised when required-check configuration cannot be proven."""


def _check_names(values: Any, label: str, *, objects: bool) -> set[str]:
    if not isinstance(values, list):
        raise GovernanceError(f"{label}: expected list")
    contexts: set[str] = set()
    for value in values:
        context = value.get("context") if objects and isinstance(value, dict) else value
        if not isinstance(context, str) or not context.strip() or context != context.strip():
            raise GovernanceError(f"{label}: invalid context")
        if objects and not isinstance(value, dict):
            raise GovernanceError(f"{label}: expected check object")
        contexts.add(context)
    return contexts


def _contexts_from_branch(branch: dict[str, Any]) -> set[str]:
    protection = branch.get("protection")
    if protection is None:
        return set()
    if not isinstance(protection, dict):
        raise GovernanceError("branch protection: expected object")
    required = protection.get("required_status_checks")
    if required is None:
        return set()
    if not isinstance(required, dict):
        raise GovernanceError("required status checks: expected object")
    # Branch protection can be active for another reason while checks are off;
    # non_admins permits an administrator bypass. Only everyone proves enforcement.
    if required.get("enforcement_level") != "everyone":
        return set()
    return _check_names(required.get("contexts", []), "contexts", objects=False) | _check_names(
        required.get("checks", []), "checks", objects=True
    )


def _contexts_from_rulesets(rulesets: list[dict[str, Any]]) -> set[str]:
    """Read individual active rules from GET /rules/branches/{branch}.

    The parameter name is retained for call compatibility. Raw ruleset envelopes
    do not demonstrate applicability to the target branch and are rejected.
    """
    if not isinstance(rulesets, list):
        raise GovernanceError("branch rules: expected list")
    contexts: set[str] = set()
    for rule in rulesets:
        if not isinstance(rule, dict):
            raise GovernanceError("branch rules: expected rule object")
        if any(key in rule for key in ("enforcement", "target", "conditions", "rules")):
            raise GovernanceError("unscoped ruleset object: use active rules for the target branch")
        rule_type = rule.get("type")
        if not isinstance(rule_type, str) or not rule_type:
            raise GovernanceError("branch rules: missing rule type")
        if rule_type != "required_status_checks":
            continue
        parameters = rule.get("parameters")
        if not isinstance(parameters, dict):
            raise GovernanceError("required status checks: missing parameters")
        contexts |= _check_names(
            parameters.get("required_status_checks"),
            "required status checks", objects=True,
        )
    return contexts


def evaluate_governance(
    branch: dict[str, Any],
    rulesets: list[dict[str, Any]],
    expected_checks: list[str],
) -> dict[str, Any]:
    """Evaluate trusted API snapshots; rulesets must be branch-scoped rules."""
    if not isinstance(branch, dict) or branch.get("protected") is not True:
        raise GovernanceError("default branch is not protected")
    expected = _check_names(expected_checks, "expected checks", objects=False)
    if not expected:
        raise GovernanceError("expected checks: non-empty explicit list required")

    observed = _contexts_from_branch(branch) | _contexts_from_rulesets(rulesets)
    missing = sorted(expected - observed)
    if missing:
        raise GovernanceError("missing required status checks: " + ", ".join(missing))

    return {
        "protected": True,
        "expected_checks": sorted(expected),
        "observed_required_checks": sorted(observed),
        "status": "GOVERNANCE_VALID",
        "validation_scope": "required_status_checks_configuration",
        "is_merge_authorization": False,
    }


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise GovernanceError("GitHub API: redirect refused")


def _github_json(url: str, token: str | None) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "e2e-platform-governance-verifier",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=15) as response:
            raw = response.read(2_097_153)
        if len(raw) > 2_097_152:
            raise GovernanceError("GitHub API: response exceeds limit")
        return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise GovernanceError(f"GitHub API HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise GovernanceError("GitHub API unavailable or invalid") from exc


def fetch_governance(
    repo: str, branch_name: str, token: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if (
        not isinstance(repo, str)
        or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo)
        or any(part in {".", ".."} for part in repo.split("/"))
    ):
        raise GovernanceError("repository: expected owner/name")
    if (
        not isinstance(branch_name, str)
        or not branch_name.strip()
        or branch_name != branch_name.strip()
    ):
        raise GovernanceError("branch: expected explicit name")

    base = f"https://api.github.com/repos/{repo}"
    encoded_branch = quote(branch_name, safe="")
    branch = _github_json(f"{base}/branches/{encoded_branch}", token)
    if not isinstance(branch, dict) or branch.get("name") != branch_name:
        raise GovernanceError("GitHub API: branch identity mismatch")

    applicable_rules: list[dict[str, Any]] = []
    for page in range(1, 11):
        batch = _github_json(
            f"{base}/rules/branches/{encoded_branch}?per_page=100&page={page}", token
        )
        if not isinstance(batch, list) or len(batch) > 100:
            raise GovernanceError("GitHub API: invalid branch rules page")
        applicable_rules.extend(batch)
        if len(batch) < 100:
            return branch, applicable_rules
    raise GovernanceError("GitHub API: branch rules pagination limit reached")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="owner/repository")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--expected-check", action="append", required=True)
    args = parser.parse_args()
    try:
        branch, rulesets = fetch_governance(
            args.repo, args.branch, os.environ.get("GITHUB_TOKEN")
        )
        result = evaluate_governance(branch, rulesets, args.expected_check)
    except GovernanceError as exc:
        print(f"GOVERNANCE_INVALID: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
