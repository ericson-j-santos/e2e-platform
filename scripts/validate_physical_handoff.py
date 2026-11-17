#!/usr/bin/env python3
"""Validate signed physical handoff evidence without authorizing operations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from e2e_platform.physical_handoff import (  # noqa: E402
    PhysicalHandoffValidationError, validate_physical_handoff,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--public-key-hex", required=True)
    parser.add_argument("--expected-repository", required=True)
    parser.add_argument("--expected-pr-number", type=int, required=True)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--expected-environment", required=True)
    parser.add_argument("--expected-run-id", type=int, required=True)
    parser.add_argument("--expected-job-id", type=int, required=True)
    parser.add_argument("--expected-run-attempt", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        if (not args.evidence.is_absolute() or not args.evidence.is_file()
                or args.evidence.is_symlink() or args.evidence.stat().st_size > 1_048_576):
            raise PhysicalHandoffValidationError("evidence_file_invalid")
        try:
            public_key = bytes.fromhex(args.public_key_hex)
            envelope = json.loads(args.evidence.read_text(encoding="utf-8"))
        except (ValueError, OSError, UnicodeError):
            raise PhysicalHandoffValidationError("evidence_input_invalid") from None
        result = validate_physical_handoff(
            envelope, public_key=public_key,
            expected_repository=args.expected_repository,
            expected_pr_number=args.expected_pr_number,
            expected_head_sha=args.expected_head_sha,
            expected_environment=args.expected_environment,
            expected_run_id=args.expected_run_id,
            expected_job_id=args.expected_job_id,
            expected_run_attempt=args.expected_run_attempt,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except PhysicalHandoffValidationError as exc:
        print(json.dumps({
            "result": "PHYSICAL_HANDOFF_EVIDENCE_BLOCKED",
            "reason_code": str(exc),
            "dispatch_allowed": False,
            "merge_authorized": False,
            "deployment_authorized": False,
        }, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
