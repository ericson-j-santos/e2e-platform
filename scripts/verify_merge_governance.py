#!/usr/bin/env python3
"""Fail-closed verifier for GitHub merge governance.

Validates that the default branch is protected and that every expected status
check is required by classic branch protection or an active repository ruleset.
Uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


class GovernanceError(RuntimeError):
    """Raised when governance cannot be proven."""


def _contexts_from_branch(branch: dict[str, Any]) -> set[str]:
    protection = branch.get("protection") or {}
    required = protection.get("required_status_checks") or {}
    contexts = set(required.get("contexts") or [])
    for check in required.get("checks") or []:
        context = check.get("context")
        if context:
            contexts.add(context)
    return contexts


def _contexts_from_rulesets(rulesets: list[dict[str, Any]]) -> set[str]:
    contexts: set[str] = set()
    for ruleset in rulesets:
        if ruleset.get("target") != "branch":
            continue
        if ruleset.get("enforcement") not in {"active", "evaluate"}:
            continue
        for rule in ruleset.get("rules") or []:
            if rule.get("type") != "required_status_checks":
                continue
            parameters = rule.get("parameters") or {}
            for check in parameters.get("required_status_checks") or []:
                context = check.get("context")
                if context:
                    contexts.add(context)
    return contexts


def evaluate_governance(
    branch: dict[str, Any],
    rulesets: list[dict[str, Any]],
    expected_checks: list[str],
) -> dict[str, Any]:
    if not branch.get("protected"):
        raise GovernanceError("default branch is not protected")

    observed = _contexts_from_branch(branch) | _contexts_from_rulesets(rulesets)
    missing = sorted(set(expected_checks) - observed)
    if missing:
        raise GovernanceError(
            "missing required status checks: " + ", ".join(missing)
        )

    return {
        "protected": True,
        "expected_checks": sorted(expected_checks),
        "observed_required_checks": sorted(observed),
        "status": "GOVERNANCE_VALID",
    }


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
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise GovernanceError(f"GitHub API HTTP {exc.code}: {url}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GovernanceError(f"GitHub API unavailable or invalid: {url}") from exc


def fetch_governance(repo: str, branch_name: str, token: str | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    api = "https://api.github.com"
    branch = _github_json(f"{api}/repos/{repo}/branches/{branch_name}", token)
    summaries = _github_json(f"{api}/repos/{repo}/rulesets", token)

    details: list[dict[str, Any]] = []
    for summary in summaries:
        ruleset_id = summary.get("id")
        if ruleset_id is None:
            continue
        details.append(
            _github_json(f"{api}/repos/{repo}/rulesets/{ruleset_id}", token)
        )
    return branch, details


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, help="owner/repository")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--expected-check", action="append", required=True)
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    try:
        branch, rulesets = fetch_governance(args.repo, args.branch, token)
        result = evaluate_governance(branch, rulesets, args.expected_check)
    except GovernanceError as exc:
        print(f"GOVERNANCE_INVALID: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
