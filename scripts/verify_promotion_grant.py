#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.promotion_authority import verify_bound_grant


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify an OpenClaw promotion grant")
    parser.add_argument("--grant", default="machine/promotion_authority.json")
    parser.add_argument("--proof", default="machine/proof_receipt.json")
    args = parser.parse_args()

    state = json.loads(Path(args.grant).read_text())
    grant = state.get("active_grant") if isinstance(state, dict) and "active_grant" in state else state
    if not grant:
        print(json.dumps({"ok": False, "error": "NO_ACTIVE_GRANT", "status": state.get("status")}, indent=2, sort_keys=True))
        return 1

    ok, error = verify_bound_grant(grant, args.proof)
    print(json.dumps({"ok": ok, "error": error, "status": state.get("status", "ACTIVE")}, indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
