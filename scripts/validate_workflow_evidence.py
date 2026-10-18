#!/usr/bin/env python3
"""Bind an evidence artifact to the current GitHub Actions attempt, read-only."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from e2e_platform import EvidenceValidationError, validate_evidence
from e2e_platform.evidence import REPOSITORY_RE, SHA_RE
from scripts.validate_evidence import read_evidence

PLATFORM_REPOSITORY = "ericson-j-santos/e2e-platform"
PREFIX_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
FILE_RE = re.compile(r"^[A-Za-z0-9_.\-/]{1,240}$")


def _required(env, key):
    value = env.get(key)
    if not isinstance(value, str) or not value or value != value.strip():
        raise EvidenceValidationError(f"workflow.{key}: required explicit value")
    return value


def trusted_identity(env):
    if env.get("GITHUB_ACTIONS") != "true":
        raise EvidenceValidationError("workflow: GitHub Actions context required")
    if env.get("GITHUB_SERVER_URL") != "https://github.com":
        raise EvidenceValidationError("workflow: unsupported GitHub server")
    if env.get("GITHUB_API_URL") != "https://api.github.com":
        raise EvidenceValidationError("workflow: unsupported API origin")
    repository = _required(env, "GITHUB_REPOSITORY")
    sha = _required(env, "E2E_EXPECTED_SHA")
    platform_ref = _required(env, "E2E_PLATFORM_REF")
    workflow_sha = _required(env, "E2E_WORKFLOW_SHA")
    if not REPOSITORY_RE.fullmatch(repository):
        raise EvidenceValidationError("workflow.repository: expected owner/name")
    if not all(SHA_RE.fullmatch(value) for value in (sha, platform_ref, workflow_sha)):
        raise EvidenceValidationError("workflow: full immutable SHAs required")
    if platform_ref.lower() != workflow_sha.lower():
        raise EvidenceValidationError("workflow.platform_ref: differs from actual workflow SHA")
    if env.get("E2E_WORKFLOW_REPOSITORY") != PLATFORM_REPOSITORY:
        raise EvidenceValidationError("workflow: unexpected platform repository")
    run_id = _required(env, "GITHUB_RUN_ID")
    attempt = _required(env, "GITHUB_RUN_ATTEMPT")
    if not re.fullmatch(r"[1-9][0-9]{0,19}", run_id) or not re.fullmatch(r"[1-9][0-9]{0,5}", attempt):
        raise EvidenceValidationError("workflow: positive run ID and attempt required")
    prefix = _required(env, "E2E_CORRELATION_PREFIX")
    if not PREFIX_RE.fullmatch(prefix):
        raise EvidenceValidationError("workflow: invalid correlation prefix")
    environment = _required(env, "E2E_EXPECTED_ENVIRONMENT")
    return {
        "repository": repository,
        "sha": sha.lower(),
        "platform_sha": workflow_sha.lower(),
        "run_id": int(run_id),
        "run_attempt": int(attempt),
        "environment": environment,
        "correlation_id": f"{prefix}-{run_id}-{attempt}",
    }


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise EvidenceValidationError("workflow API: redirect refused")


def fetch_attempt(identity, token):
    if not isinstance(token, str) or not token:
        raise EvidenceValidationError("workflow API: read credential unavailable")
    url = (
        f"https://api.github.com/repos/{identity['repository']}/actions/runs/"
        f"{identity['run_id']}/attempts/{identity['run_attempt']}"
    )
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "e2e-platform-evidence-gate",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=15) as response:
            raw = response.read(2_097_153)
        if len(raw) > 2_097_152:
            raise EvidenceValidationError("workflow API: response exceeds limit")
        data = json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise EvidenceValidationError(f"workflow API: HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, EvidenceValidationError):
            raise
        raise EvidenceValidationError("workflow API: unavailable or invalid response") from exc
    if not isinstance(data, dict):
        raise EvidenceValidationError("workflow API: expected attempt object")
    return data


def validate_attempt(identity, attempt):
    if not isinstance(attempt, dict):
        raise EvidenceValidationError("workflow API: expected object")
    repository = attempt.get("repository")
    full_name = repository.get("full_name") if isinstance(repository, dict) else None
    if not isinstance(full_name, str) or full_name.lower() != identity["repository"].lower():
        raise EvidenceValidationError("workflow API: repository mismatch")
    for field in ("run_attempt", "id"):
        expected = identity["run_attempt" if field == "run_attempt" else "run_id"]
        if type(attempt.get(field)) is not int or attempt[field] != expected:
            raise EvidenceValidationError(f"workflow API: {field} mismatch")
    head = attempt.get("head_sha")
    if not isinstance(head, str) or head.lower() != identity["sha"]:
        raise EvidenceValidationError("workflow API: head SHA mismatch")
    started_at = attempt.get("run_started_at")
    if not isinstance(started_at, str) or not started_at:
        raise EvidenceValidationError("workflow API: attempt start time unavailable")
    return started_at


def confined_evidence_path(root, name):
    if not isinstance(name, str) or not FILE_RE.fullmatch(name):
        raise EvidenceValidationError("file: invalid artifact-relative path")
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts or str(relative) != name:
        raise EvidenceValidationError("file: must stay inside the evidence artifact")
    try:
        directory = Path(root).resolve(strict=True)
        path = (directory / name).resolve(strict=True)
        if not directory.is_dir() or not path.is_relative_to(directory) or not path.is_file():
            raise EvidenceValidationError("file: evidence must be a regular file inside artifact")
    except (OSError, RuntimeError) as exc:
        raise EvidenceValidationError("file: evidence artifact is missing") from exc
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, default=Path(".e2e-evidence"))
    args = parser.parse_args()
    try:
        identity = trusted_identity(os.environ)
        path = confined_evidence_path(args.evidence_root, _required(os.environ, "E2E_EVIDENCE_FILE"))
        payload, before = read_evidence(path)
        attempt = fetch_attempt(identity, os.environ.get("GITHUB_TOKEN"))
        started_at = validate_attempt(identity, attempt)
        result = validate_evidence(
            payload,
            expected_repository=identity["repository"], expected_sha=identity["sha"],
            expected_environment=identity["environment"],
            expected_correlation_id=identity["correlation_id"],
            not_before=started_at,
        )
        if read_evidence(path)[1] != before:
            raise EvidenceValidationError("file: evidence changed during validation")
        result.update({
            "run_id": identity["run_id"], "run_attempt": identity["run_attempt"],
            "platform_sha": identity["platform_sha"], "evidence_sha256": before,
            "attempt_started_at": started_at,
        })
    except (EvidenceValidationError, OSError) as exc:
        message = str(exc) if isinstance(exc, EvidenceValidationError) else "file: unavailable during validation"
        print(json.dumps({"result": "E2E_EVIDENCE_INVALID", "error": message}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
