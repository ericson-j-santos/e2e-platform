#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from e2e_platform import EvidenceValidationError, validate_evidence


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_evidence.py <evidence.json>", file=sys.stderr)
        return 64

    path = Path(sys.argv[1])
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        result = validate_evidence(payload)
    except (OSError, json.JSONDecodeError, EvidenceValidationError) as exc:
        print(
            json.dumps(
                {"result": "E2E_EVIDENCE_INVALID", "error": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
