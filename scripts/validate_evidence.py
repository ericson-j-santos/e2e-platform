#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from e2e_platform import EvidenceValidationError, validate_evidence

MAX_EVIDENCE_BYTES = 1_048_576


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceValidationError("JSON: duplicate object key")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise EvidenceValidationError("JSON: numeric constants are outside the evidence contract")


def read_evidence(path: Path):
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_EVIDENCE_BYTES + 1)
        if len(raw) > MAX_EVIDENCE_BYTES:
            raise EvidenceValidationError("file: exceeds 1 MiB evidence limit")
        payload = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant, parse_int=_invalid_constant,
            parse_float=_invalid_constant,
        )
        return payload, hashlib.sha256(raw).hexdigest()
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise EvidenceValidationError("file: unreadable or invalid UTF-8 JSON") from exc


def load_evidence(path: Path):
    return read_evidence(path)[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate E2E evidence fail-closed.")
    parser.add_argument("evidence", type=Path)
    for name in ("repository", "sha", "environment", "correlation-id"):
        parser.add_argument(f"--expected-{name}")
    parser.add_argument("--not-before")
    args = parser.parse_args()
    try:
        result = validate_evidence(
            load_evidence(args.evidence),
            expected_repository=args.expected_repository,
            expected_sha=args.expected_sha,
            expected_environment=args.expected_environment,
            expected_correlation_id=args.expected_correlation_id,
            not_before=args.not_before,
        )
    except EvidenceValidationError as exc:
        print(json.dumps({"result": "E2E_EVIDENCE_INVALID", "error": str(exc)},
                         ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
